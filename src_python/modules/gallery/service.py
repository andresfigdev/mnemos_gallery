"""
Service - Lógica de negocio para el módulo Gallery
Paso 4.1 - Service Básico - Listar Carpetas
Paso 4.3 - Service - Crear Carpeta Manual
Paso 4.5 - Service - Escanear Carpeta (Solo estructura)
Paso 4.6 - Service - Procesar Imagen Individual
Paso 4.7 - Service - Escanear Completo
Paso 5.3 - Thumbnails
"""

import asyncio
import hashlib
import logging
import math
import os
import shutil
import struct
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal, Tuple, TypedDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from hashlib import md5

from .models import Folder, Image, FolderNode, FolderTag, folder_node_tags
from .embedded_resources import extract_model_and_loras_from_json
from .dashboard_metrics import classify_folder_type_from_rel_path, is_root_image_path
from .sync_master import canonicalize_path, list_master_roots
from .naming_plan import (
    ImageRow,
    NamingPlanError,
    NamingPlanResult,
    build_missing_naming_plan,
    build_rename_plan,
)
from .metadata_service import MetadataService, ImageMetadata
from .guid_utils import generate_content_hash_guid
from ...shared.event_bus import event_bus, EventType, Event
from ...shared.models import Setting, SettingKeys

logger = logging.getLogger(__name__)

# Extensiones de imagen soportadas
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}

# Intentar importar PIL/Pillow para leer dimensiones
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PILImage = None

# Tamaño por defecto de thumbnails
THUMBNAIL_SIZE = 256


def sanitize_json_for_database(value: Any) -> Any:
    """Convierte metadatos a JSON válido para PostgreSQL (sin NaN ni infinitos)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: sanitize_json_for_database(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json_for_database(item) for item in value]
    return value


def build_location_guid(content_guid: str, folder_id: str, relative_path: str) -> str:
    """Genera un GUID estable cuando el mismo contenido existe en otra ubicación."""
    normalized_path = str(relative_path).replace("\\", "/").casefold()
    digest = hashlib.sha256(
        f"{content_guid}|{folder_id}|{normalized_path}".encode("utf-8")
    ).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


class NamedCount(TypedDict):
    name: str
    display_name: str
    count: int
    percent: float
    filter: Dict[str, str] | None


class FolderCount(TypedDict):
    folder_id: str
    folder_name: str
    display_name: str
    count: int
    percent: float
    filter: Dict[str, str] | None


class DashboardSummary(TypedDict):
    total_images: int
    total_folders: int
    total_subfolders: int
    total_active_tags: int


class DashboardAIUsage(TypedDict):
    top_checkpoints: List[NamedCount]
    top_loras: List[NamedCount]
    missing_checkpoint_count: int
    missing_lora_count: int


class DashboardRootVsSubfolder(TypedDict):
    root_images: int
    subfolder_images: int
    root_percent: float
    subfolder_percent: float


class DashboardDistribution(TypedDict):
    images_by_folder: List[FolderCount]
    images_by_folder_type: List[NamedCount]
    root_vs_subfolder: DashboardRootVsSubfolder


class DashboardMetrics(TypedDict):
    summary: DashboardSummary
    ai_usage: DashboardAIUsage
    distribution: DashboardDistribution


def _safe_percent(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count * 100.0) / total, 2)


def _friendly_resource_name(raw_name: str) -> str:
    normalized = (raw_name or "").replace("\\", "/").strip()
    if not normalized:
        return "—"
    last = normalized.split("/")[-1]
    base = last.rsplit(".", 1)[0]
    pretty = base.replace("_", " ").replace("-", " ").strip()
    if not pretty:
        return base or last
    return " ".join(token.capitalize() for token in pretty.split())


class SyncRootResult(TypedDict):
    folder_id: str
    folder_name: str
    folder_path: str
    existed: bool
    created_count: int
    updated_count: int
    image_count: int
    errors: int


class SyncMasterResult(TypedDict):
    master_path: str
    roots_detected: int
    roots_created: int
    roots_existing: int
    scanned_roots: List[SyncRootResult]
    errors: List[str]


class GalleryService:
    """Servicio para operaciones relacionadas con la galería de imágenes"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.metadata_service = MetadataService()

    async def list_folders(self) -> List[Folder]:
        """
        Lista todas las carpetas registradas en la base de datos
        
        Returns:
            List[Folder]: Lista de todas las carpetas
        """
        result = await self.db.execute(select(Folder))
        folders = result.scalars().all()
        return folders

    async def get_dashboard_metrics(self) -> DashboardMetrics:
        total_images_result = await self.db.execute(select(func.count(Image.id)))
        total_images = int(total_images_result.scalar() or 0)

        total_folders_result = await self.db.execute(select(func.count(Folder.id)))
        total_folders = int(total_folders_result.scalar() or 0)

        total_subfolders_result = await self.db.execute(
            select(func.count(FolderNode.id)).where(FolderNode.depth > 0)
        )
        total_subfolders = int(total_subfolders_result.scalar() or 0)

        total_active_tags_result = await self.db.execute(select(func.count(FolderTag.id)))
        total_active_tags = int(total_active_tags_result.scalar() or 0)

        folder_counts_result = await self.db.execute(
            select(Folder.id, Folder.name, func.count(Image.id))
            .select_from(Folder)
            .outerjoin(Image, Image.folder_id == Folder.id)
            .group_by(Folder.id, Folder.name)
            .order_by(func.count(Image.id).desc(), Folder.name.asc())
        )
        images_by_folder: List[FolderCount] = [
            {
                "folder_id": str(fid),
                "folder_name": str(name),
                "display_name": str(name),
                "count": int(count or 0),
                "percent": _safe_percent(int(count or 0), total_images),
                "filter": {"mode": "folder_id", "value": str(fid)},
            }
            for fid, name, count in folder_counts_result.fetchall()
        ]

        images_data_result = await self.db.execute(
            select(Image.path, Image.prompt_json, Image.workflow_json)
        )
        rows = images_data_result.fetchall()

        checkpoint_counter: Counter[str] = Counter()
        lora_counter: Counter[str] = Counter()
        folder_type_counter: Counter[str] = Counter()
        missing_checkpoint_count = 0
        missing_lora_count = 0
        root_images = 0
        subfolder_images = 0

        for path, prompt_json, workflow_json in rows:
            rel_path = str(path or "")
            folder_type = classify_folder_type_from_rel_path(rel_path)
            folder_type_counter[folder_type] += 1

            if is_root_image_path(rel_path):
                root_images += 1
            else:
                subfolder_images += 1

            model_name, loras = extract_model_and_loras_from_json(prompt_json, workflow_json)
            if model_name:
                checkpoint_counter[model_name] += 1
            else:
                missing_checkpoint_count += 1

            if loras:
                for lora in loras:
                    lora_counter[lora.name] += 1
            else:
                missing_lora_count += 1

        top_checkpoints: List[NamedCount] = [
            {
                "name": name,
                "display_name": _friendly_resource_name(name),
                "count": int(count),
                "percent": _safe_percent(int(count), total_images),
                "filter": {"mode": "checkpoint_name", "value": name},
            }
            for name, count in checkpoint_counter.most_common(10)
        ]
        top_loras: List[NamedCount] = [
            {
                "name": name,
                "display_name": _friendly_resource_name(name),
                "count": int(count),
                "percent": _safe_percent(int(count), total_images),
                "filter": {"mode": "lora_name", "value": name},
            }
            for name, count in lora_counter.most_common(10)
        ]
        images_by_folder_type: List[NamedCount] = [
            {
                "name": name,
                "display_name": name,
                "count": int(count),
                "percent": _safe_percent(int(count), total_images),
                "filter": {"mode": "folder_type", "value": name},
            }
            for name, count in sorted(folder_type_counter.items(), key=lambda item: (-item[1], item[0]))
        ]

        return {
            "summary": {
                "total_images": total_images,
                "total_folders": total_folders,
                "total_subfolders": total_subfolders,
                "total_active_tags": total_active_tags,
            },
            "ai_usage": {
                "top_checkpoints": top_checkpoints,
                "top_loras": top_loras,
                "missing_checkpoint_count": missing_checkpoint_count,
                "missing_lora_count": missing_lora_count,
            },
            "distribution": {
                "images_by_folder": images_by_folder,
                "images_by_folder_type": images_by_folder_type,
                "root_vs_subfolder": {
                    "root_images": root_images,
                    "subfolder_images": subfolder_images,
                    "root_percent": _safe_percent(root_images, total_images),
                    "subfolder_percent": _safe_percent(subfolder_images, total_images),
                },
            },
        }

    async def sync_master_folder(self, master_path: str) -> SyncMasterResult:
        roots = list_master_roots(master_path)
        master_dir = Path(master_path.strip())
        existing_folders_result = await self.db.execute(select(Folder))
        existing_folders = list(existing_folders_result.scalars().all())
        # No conservar entidades ORM entre escaneos: un rollback de una imagen
        # expira toda la sesión y leer sus atributos después dispara MissingGreenlet.
        existing_by_path: Dict[str, Dict[str, Any]] = {
            canonicalize_path(f.path): {
                "id": str(f.id),
                "name": str(f.name),
                "path": str(f.path),
            }
            for f in existing_folders
        }

        roots_created = 0
        roots_existing = 0
        scanned_roots: List[SyncRootResult] = []
        errors: List[str] = []

        for root_dir in roots:
            folder_path = str(root_dir)
            canonical = canonicalize_path(folder_path)
            folder_info = existing_by_path.get(canonical)
            existed = folder_info is not None

            if not folder_info:
                try:
                    folder = await self.create_folder(path=folder_path, name=root_dir.name, enabled=True)
                    folder_info = {
                        "id": str(folder.id),
                        "name": str(folder.name),
                        "path": str(folder.path),
                    }
                    existing_by_path[canonical] = folder_info
                    roots_created += 1
                except ValueError:
                    # Condición de carrera o diferencia de normalización: reintentar lookup.
                    lookup = await self.db.execute(select(Folder).where(Folder.path == folder_path))
                    folder = lookup.scalar_one_or_none()
                    if not folder:
                        errors.append(f"No se pudo crear o recuperar carpeta raíz: {folder_path}")
                        continue
                    folder_info = {
                        "id": str(folder.id),
                        "name": str(folder.name),
                        "path": str(folder.path),
                    }
                    existing_by_path[canonical] = folder_info
                    existed = True
                    roots_existing += 1
            else:
                roots_existing += 1

            try:
                folder_id = str(folder_info["id"])
                folder_name = str(folder_info["name"])
                registered_path = str(folder_info["path"])
                scan = await self.scan_folder(folder_id, recursive=True, create_records=True)
                scanned_roots.append(
                    {
                        "folder_id": folder_id,
                        "folder_name": folder_name,
                        "folder_path": registered_path,
                        "existed": existed,
                        "created_count": int(scan.get("created_count", 0) or 0),
                        "updated_count": int(scan.get("updated_count", 0) or 0),
                        "image_count": int(scan.get("image_count", 0) or 0),
                        "errors": len(scan.get("errors", []) or []),
                    }
                )
            except Exception as e:
                errors.append(f"Error escaneando root '{root_dir.name}': {str(e)}")

        return {
            "master_path": str(master_dir),
            "roots_detected": len(roots),
            "roots_created": roots_created,
            "roots_existing": roots_existing,
            "scanned_roots": scanned_roots,
            "errors": errors,
        }
    
    async def list_images(
        self,
        folder_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Image]:
        """
        Lista imágenes con filtros opcionales
        
        Args:
            folder_id: Filtrar por ID de carpeta (opcional)
            limit: Límite de resultados (default: 100)
            offset: Offset para paginación (default: 0)
        
        Returns:
            List[Image]: Lista de imágenes que coinciden con los filtros
        """
        query = select(Image)
        
        # Aplicar filtros
        if folder_id:
            query = query.where(Image.folder_id == folder_id)
        
        # Aplicar paginación
        query = query.limit(limit).offset(offset)
        
        # Ordenar por fecha de creación (más recientes primero)
        query = query.order_by(Image.created_at.desc())
        
        result = await self.db.execute(query)
        images = result.scalars().all()
        return images
    
    async def get_image(self, image_id: int) -> Optional[Image]:
        """
        Obtiene una imagen por su ID
        
        Args:
            image_id: ID de la imagen
        
        Returns:
            Image | None: La imagen si existe, None en caso contrario
        """
        result = await self.db.execute(select(Image).where(Image.id == image_id))
        image = result.scalar_one_or_none()
        return image
    
    def _generate_thumbnail(self, image_path: Path, size: int = THUMBNAIL_SIZE) -> Optional[str]:
        """
        Genera un thumbnail de una imagen
        El thumbnail se guarda en: {carpeta_imagen}/thumb/{nombre_imagen}.jpg
        
        Args:
            image_path: Path de la imagen original
            size: Tamaño del thumbnail (default: THUMBNAIL_SIZE)
        
        Returns:
            str | None: Ruta relativa del thumbnail (thumb/{nombre}.jpg), o None si falla
        """
        logger.debug(f"[THUMBNAIL] Iniciando generación para: {image_path}")
        
        if not PIL_AVAILABLE or not PILImage:
            logger.error("[THUMBNAIL] PIL/Pillow no está disponible, no se pueden generar thumbnails")
            return None
        
        # Verificar que el archivo existe
        if not isinstance(image_path, Path):
            image_path = Path(image_path)
        
        if not image_path.exists():
            logger.error(f"[THUMBNAIL] El archivo NO existe: {image_path}")
            return None
        
        if not image_path.is_file():
            logger.error(f"[THUMBNAIL] La ruta NO es un archivo: {image_path}")
            return None
        
        try:
            # Nueva estrategia: thumbnails en carpeta thumb/ relativa a la imagen
            # thumb_path = {carpeta_imagen}/thumb/{nombre_imagen}.jpg
            # IMPORTANTE: Si la imagen ya está dentro de una carpeta thumb/, usar la carpeta padre original
            image_dir = image_path.parent
            
            # Protección contra bucles infinitos: si estamos dentro de thumb/, usar la carpeta padre
            if image_dir.name == "thumb":
                # La imagen está dentro de thumb/, usar la carpeta padre
                image_dir = image_dir.parent
                logger.warning(f"[THUMBNAIL] Imagen dentro de carpeta thumb/ detectada, usando carpeta padre: {image_dir}")
            
            thumb_dir = image_dir / "thumb"
            
            # Crear carpeta thumb/ si no existe
            thumb_dir.mkdir(exist_ok=True)
            
            # Nombre del thumbnail: mismo nombre que la imagen pero con extensión .jpg
            thumb_filename = image_path.stem + ".jpg"
            thumb_path = thumb_dir / thumb_filename
            
            # Ruta relativa para guardar en DB: thumb/{nombre}.jpg
            thumb_relative_path = f"thumb/{thumb_filename}"
            
            # Si ya existe, retornar ruta relativa
            if thumb_path.exists():
                logger.debug(f"[THUMBNAIL] Thumbnail ya existe: {thumb_path}")
                return thumb_relative_path
            
            # Abrir imagen original
            try:
                # Intentar abrir normalmente primero
                img = PILImage.open(image_path)
                # Intentar verificar (puede fallar si hay problemas)
                try:
                    img.verify()
                except Exception:
                    img.close()
                    raise PILImage.UnidentifiedImageError("Imagen no válida")
                # Reabrir porque verify() cierra el archivo
                img.close()
                img = PILImage.open(image_path)
            except Exception as e:
                logger.error(f"[THUMBNAIL] Error al abrir imagen {image_path}: {e}")
                # Si la imagen está corrupta o no se puede leer, no creamos el thumbnail
                return None
            
            try:
                # Convertir a RGB si es necesario (para formatos con transparencia)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Crear fondo blanco
                    background = PILImage.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Calcular dimensiones manteniendo aspect ratio
                img.thumbnail((size, size), PILImage.Resampling.LANCZOS)
                
                # Guardar como JPEG
                img.save(thumb_path, 'JPEG', quality=85, optimize=True)
                
                # Verificar que se guardó
                if not thumb_path.exists():
                    logger.error(f"[THUMBNAIL] ERROR: El thumbnail NO se guardó: {thumb_path}")
                    return None
                
                logger.debug(f"[THUMBNAIL] Thumbnail guardado exitosamente: {thumb_path}")
            finally:
                # Cerrar la imagen explícitamente
                img.close()
            
            # Publicar evento de thumbnail generado (async, pero no esperamos)
            # Usamos publish en lugar de publish_async porque este método es síncrono
            event_bus.publish(Event(
                event_type=EventType.THUMBNAIL_GENERATED,
                payload={
                    "image_path": str(image_path),
                    "thumb_path": str(thumb_path),
                    "thumb_relative_path": thumb_relative_path,
                    "size": size
                }
            ))
            
            logger.debug(f"[THUMBNAIL] Thumbnail generado: {thumb_relative_path}")
            return thumb_relative_path
        except Exception as e:
            # Si falla, retornar None (no es crítico)
            logger.error(f"[THUMBNAIL] ERROR al generar thumbnail para {image_path}: {e}", exc_info=True)
            return None
    
    async def create_folder(
        self, 
        path: str, 
        name: str, 
        enabled: bool = True
    ) -> Folder:
        """
        Crea una nueva carpeta manualmente
        
        Args:
            path: Ruta absoluta de la carpeta en el sistema
            name: Nombre de la carpeta
            enabled: Si la carpeta está habilitada para escaneo (default: True)
        
        Returns:
            Folder: La carpeta creada
        
        Raises:
            ValueError: Si la carpeta ya existe o los parámetros son inválidos
        """
        # Validar que el path no esté vacío
        if not path or not path.strip():
            raise ValueError("El path de la carpeta no puede estar vacío")
        
        # Normalizar el path (eliminar espacios al inicio y final)
        path = path.strip()
        
        # Validar que el name no esté vacío
        if not name or not name.strip():
            raise ValueError("El nombre de la carpeta no puede estar vacío")
        
        name = name.strip()
        
        # Verificar si ya existe una carpeta con el mismo path
        result = await self.db.execute(select(Folder).where(Folder.path == path))
        existing_folder = result.scalar_one_or_none()
        
        if existing_folder:
            status_msg = "deshabilitada" if not existing_folder.enabled else "habilitada"
            raise ValueError(f"Ya existe una carpeta con el path '{path}' (estado: {status_msg}). Si está deshabilitada, puedes activarla desde la lista de carpetas.")
        
        # Generar ID único basado en el path (MD5 hash)
        folder_id = hashlib.md5(path.encode()).hexdigest()
        
        # Crear nueva carpeta
        new_folder = Folder(
            id=folder_id,
            path=path,
            name=name,
            enabled=enabled
        )
        
        self.db.add(new_folder)
        await self.db.commit()
        await self.db.refresh(new_folder)
        
        return new_folder
    
    def _is_image_file(self, file_path: Path) -> bool:
        """
        Verifica si un archivo es una imagen soportada
        
        Args:
            file_path: Path del archivo
            
        Returns:
            bool: True si es una imagen soportada
        """
        if not file_path.is_file():
            return False
        
        extension = file_path.suffix.lower()
        return extension in SUPPORTED_IMAGE_EXTENSIONS

    async def _load_folder_nodes_cache(self, folder_id: str) -> Dict[str, FolderNode]:
        result = await self.db.execute(
            select(FolderNode).where(FolderNode.folder_root_id == folder_id)
        )
        nodes = result.scalars().all()
        return {node.rel_path: node for node in nodes}

    async def _ensure_root_node(
        self,
        folder_id: str,
        folder_name: str,
        node_cache: Dict[str, FolderNode],
    ) -> FolderNode:
        root_node = node_cache.get("")
        if root_node:
            return root_node

        root_node = FolderNode(
            folder_root_id=folder_id,
            parent_node_id=None,
            rel_path="",
            name=folder_name,
            depth=0,
        )
        self.db.add(root_node)
        await self.db.flush()
        node_cache[""] = root_node
        return root_node

    async def _ensure_folder_node_for_relative_path(
        self,
        folder_id: str,
        folder_name: str,
        relative_path: str,
        node_cache: Dict[str, FolderNode],
    ) -> FolderNode:
        """
        Retorna el nodo de carpeta que contiene el archivo `relative_path`.
        Para archivos en raíz, retorna el nodo raíz (rel_path="").
        """
        normalized = relative_path.replace("\\", "/")
        parent_rel = str(Path(normalized).parent).replace("\\", "/")
        if parent_rel in (".", ""):
            return await self._ensure_root_node(folder_id, folder_name, node_cache)

        return await self._ensure_folder_node_for_directory_path(
            folder_id=folder_id,
            folder_name=folder_name,
            directory_rel_path=parent_rel,
            node_cache=node_cache,
        )

    async def _ensure_folder_node_for_directory_path(
        self,
        folder_id: str,
        folder_name: str,
        directory_rel_path: str,
        node_cache: Dict[str, FolderNode],
    ) -> FolderNode:
        """Crea la cadena de nodos para una carpeta física, aunque esté vacía."""
        normalized = directory_rel_path.replace("\\", "/").strip("/")
        if normalized in ("", "."):
            return await self._ensure_root_node(folder_id, folder_name, node_cache)

        await self._ensure_root_node(folder_id, folder_name, node_cache)
        current_parent = node_cache[""]
        current_rel = ""
        for segment in [p for p in normalized.split("/") if p and p != "."]:
            current_rel = f"{current_rel}/{segment}" if current_rel else segment
            existing = node_cache.get(current_rel)
            if existing:
                current_parent = existing
                continue

            new_node = FolderNode(
                folder_root_id=folder_id,
                parent_node_id=current_parent.id,
                rel_path=current_rel,
                name=segment,
                depth=current_parent.depth + 1,
            )
            self.db.add(new_node)
            await self.db.flush()
            node_cache[current_rel] = new_node
            current_parent = new_node

        return current_parent

    @staticmethod
    def _is_thumbnail_relative_path(relative_path: str) -> bool:
        normalized = str(relative_path or "").replace("\\", "/")
        return any(part.casefold() == "thumb" for part in normalized.split("/") if part)

    @staticmethod
    def _walk_folder_without_thumbnails(folder_path: Path) -> Tuple[List[str], List[Path]]:
        """Lista todas las carpetas y archivos sin entrar en ramas `thumb`."""
        directory_paths: List[str] = []
        file_paths: List[Path] = []
        for current_root, dir_names, file_names in os.walk(folder_path):
            dir_names[:] = sorted(
                [name for name in dir_names if name.casefold() != "thumb"],
                key=str.casefold,
            )
            current_path = Path(current_root)
            if current_path != folder_path:
                directory_paths.append(
                    str(current_path.relative_to(folder_path)).replace("\\", "/")
                )
            for file_name in sorted(file_names, key=str.casefold):
                file_paths.append(current_path / file_name)
        return directory_paths, file_paths

    @staticmethod
    def _normalize_tag_name(tag_name: str) -> str:
        return " ".join((tag_name or "").strip().lower().split())

    async def list_folder_tags(self) -> List[FolderTag]:
        result = await self.db.execute(select(FolderTag).order_by(FolderTag.name.asc()))
        return result.scalars().all()

    async def get_folder_node(self, node_id: int) -> Optional[FolderNode]:
        result = await self.db.execute(select(FolderNode).where(FolderNode.id == node_id))
        return result.scalar_one_or_none()

    async def _resolve_or_create_tags(
        self,
        tag_ids: Optional[List[int]] = None,
        tag_names: Optional[List[str]] = None,
    ) -> List[FolderTag]:
        resolved: Dict[int, FolderTag] = {}

        if tag_ids:
            result = await self.db.execute(
                select(FolderTag).where(FolderTag.id.in_(tag_ids))
            )
            for tag in result.scalars().all():
                resolved[tag.id] = tag

        if tag_names:
            normalized_names = [self._normalize_tag_name(name) for name in tag_names]
            normalized_names = [name for name in normalized_names if name]
            if normalized_names:
                existing_result = await self.db.execute(
                    select(FolderTag).where(FolderTag.name.in_(normalized_names))
                )
                existing_by_name = {tag.name: tag for tag in existing_result.scalars().all()}
                for tag_name in normalized_names:
                    tag = existing_by_name.get(tag_name)
                    if tag is None:
                        tag = FolderTag(name=tag_name)
                        self.db.add(tag)
                        await self.db.flush()
                    resolved[tag.id] = tag

        return list(resolved.values())

    async def set_folder_node_tags(
        self,
        node_id: int,
        tag_ids: Optional[List[int]] = None,
        tag_names: Optional[List[str]] = None,
    ) -> List[FolderTag]:
        node = await self.get_folder_node(node_id)
        if not node:
            raise ValueError("folder_node_not_found")

        tags = await self._resolve_or_create_tags(tag_ids=tag_ids, tag_names=tag_names)

        await self.db.execute(
            folder_node_tags.delete().where(folder_node_tags.c.folder_node_id == node_id)
        )
        if tags:
            await self.db.execute(
                folder_node_tags.insert(),
                [{"folder_node_id": node_id, "tag_id": tag.id} for tag in tags],
            )

        await self.db.commit()
        return tags

    async def get_folder_tree(self, folder_id: str) -> List[Dict[str, Any]]:
        nodes_result = await self.db.execute(
            select(FolderNode)
            .where(FolderNode.folder_root_id == folder_id)
            .order_by(FolderNode.depth.asc(), FolderNode.rel_path.asc())
        )
        nodes = [
            node
            for node in nodes_result.scalars().all()
            if not self._is_thumbnail_relative_path(node.rel_path)
        ]
        if not nodes:
            return []

        node_ids = [node.id for node in nodes]
        image_counts_result = await self.db.execute(
            select(Image.folder_node_id, func.count(Image.id))
            .where(
                Image.folder_id == folder_id,
                Image.folder_node_id.in_(node_ids),
            )
            .group_by(Image.folder_node_id)
        )
        image_counts = {
            int(node_id): int(count)
            for node_id, count in image_counts_result.fetchall()
            if node_id is not None
        }
        tags_result = await self.db.execute(
            select(folder_node_tags.c.folder_node_id, FolderTag)
            .join(FolderTag, FolderTag.id == folder_node_tags.c.tag_id)
            .where(folder_node_tags.c.folder_node_id.in_(node_ids))
        )
        node_tags_map: Dict[int, List[FolderTag]] = {}
        for node_id, tag in tags_result.fetchall():
            node_tags_map.setdefault(node_id, []).append(tag)

        children_by_parent: Dict[int | None, List[FolderNode]] = {}
        nodes_by_id: Dict[int, FolderNode] = {}
        for node in nodes:
            children_by_parent.setdefault(node.parent_node_id, []).append(node)
            nodes_by_id[node.id] = node

        def own_tags_payload(node_id: int) -> List[Dict[str, Any]]:
            return [
                {"id": tag.id, "name": tag.name, "color": tag.color}
                for tag in sorted(node_tags_map.get(node_id, []), key=lambda x: x.name)
            ]

        def effective_tags_payload(node: FolderNode) -> List[Dict[str, Any]]:
            merged: Dict[int, FolderTag] = {}
            current: FolderNode | None = node
            while current is not None:
                for tag in node_tags_map.get(current.id, []):
                    merged[tag.id] = tag
                current = nodes_by_id.get(current.parent_node_id) if current.parent_node_id else None
            return [
                {"id": tag.id, "name": tag.name, "color": tag.color}
                for tag in sorted(merged.values(), key=lambda x: x.name)
            ]

        def build_node_payload(node: FolderNode) -> Dict[str, Any]:
            child_nodes = sorted(
                children_by_parent.get(node.id, []),
                key=lambda x: x.name.lower(),
            )
            own_tags = own_tags_payload(node.id)
            effective_tags = effective_tags_payload(node)
            return {
                "id": node.id,
                "folder_root_id": node.folder_root_id,
                "parent_node_id": node.parent_node_id,
                "rel_path": node.rel_path,
                "name": node.name,
                "depth": node.depth,
                "naming_base": node.naming_base,
                "naming_number_width": node.naming_number_width,
                "image_count": image_counts.get(node.id, 0),
                "tags": own_tags,
                "tag_ids": [tag["id"] for tag in own_tags],
                "effective_tags": effective_tags,
                "effective_tag_ids": [tag["id"] for tag in effective_tags],
                "children": [build_node_payload(child) for child in child_nodes],
            }

        root_nodes = sorted(children_by_parent.get(None, []), key=lambda x: x.name.lower())
        return [build_node_payload(node) for node in root_nodes]
    
    async def scan_folder(
        self, 
        folder_id: str, 
        recursive: bool = True,
        create_records: bool = True
    ) -> Dict[str, Any]:
        """
        Escanea una carpeta y detecta archivos de imagen.
        Si create_records=True, procesa las imágenes y crea registros en BD.
        
        Args:
            folder_id: ID de la carpeta a escanear
            recursive: Si debe escanear recursivamente (default: True)
            create_records: Si debe crear registros en BD (default: True)
            
        Returns:
            Dict con información del escaneo:
            {
                "folder_id": str,
                "folder_path": str,
                "total_files": int,
                "image_files": List[Dict[str, str]],  # [{"path": "...", "relative_path": "..."}]
                "image_count": int,
                "created_count": int,  # Solo si create_records=True
                "updated_count": int,  # Solo si create_records=True
                "errors": List[str]
            }
            
        Raises:
            ValueError: Si la carpeta no existe o no está habilitada
        """
        logger.info(f"[SCAN] ===== INICIANDO scan_folder =====")
        logger.info(f"[SCAN] Parámetros: folder_id={folder_id}, recursive={recursive}, create_records={create_records}")
        
        # Obtener la carpeta de la BD
        result = await self.db.execute(select(Folder).where(Folder.id == folder_id))
        folder = result.scalar_one_or_none()
        
        if not folder:
            logger.error(f"[SCAN] No existe una carpeta con ID '{folder_id}'")
            raise ValueError(f"No existe una carpeta con ID '{folder_id}'")
        
        # Guardar todos los atributos necesarios en variables locales inmediatamente
        # para evitar lazy-loading en contexto asíncrono
        folder_enabled = folder.enabled
        folder_name = folder.name
        folder_path_str = folder.path
        
        if not folder_enabled:
            logger.error(f"[SCAN] La carpeta '{folder_name}' no está habilitada para escaneo")
            raise ValueError(f"La carpeta '{folder_name}' no está habilitada para escaneo")
        
        folder_path = Path(folder_path_str)
        logger.info(f"[SCAN] Carpeta encontrada: name={folder_name}, path={folder_path}")
        
        if not folder_path.exists():
            logger.error(f"[SCAN] La ruta de la carpeta no existe: {folder_path_str}")
            raise ValueError(f"La ruta de la carpeta no existe: {folder_path_str}")
        
        if not folder_path.is_dir():
            logger.error(f"[SCAN] La ruta no es un directorio: {folder_path_str}")
            raise ValueError(f"La ruta no es un directorio: {folder_path_str}")
        
        # Escanear archivos
        image_files = []
        errors = []
        total_files = 0
        processed_count = 0  # Contador de imágenes procesadas
        created_count = 0
        updated_count = 0
        node_cache: Dict[str, FolderNode] = {}
        
        logger.info(f"[SCAN] Iniciando escaneo de archivos en: {folder_path}")
        if create_records:
            node_cache = await self._load_folder_nodes_cache(folder_id)
            await self._ensure_root_node(folder_id, folder_name, node_cache)
        
        try:
            if recursive:
                # Una sola caminata del disco obtiene el árbol completo y evita
                # entrar en cualquier carpeta de miniaturas, incluso anidada.
                physical_directories, physical_files = self._walk_folder_without_thumbnails(folder_path)
                if create_records:
                    for directory_rel_path in physical_directories:
                        await self._ensure_folder_node_for_directory_path(
                            folder_id=folder_id,
                            folder_name=folder_name,
                            directory_rel_path=directory_rel_path,
                            node_cache=node_cache,
                        )

                for file_path in physical_files:
                    total_files += 1
                    try:
                        if self._is_image_file(file_path):
                            # Calcular ruta relativa desde la carpeta base
                            try:
                                relative_path = str(file_path.relative_to(folder_path))
                            except ValueError:
                                # Si no es relativo, usar solo el nombre del archivo
                                relative_path = file_path.name
                                logger.warning(f"No se pudo calcular ruta relativa para {file_path}, usando solo nombre: {relative_path}")
                            
                            processed_count += 1
                            
                            # Log de progreso cada 50 imágenes
                            if processed_count % 50 == 0:
                                logger.info(f"[SCAN] Progreso: {processed_count} imágenes encontradas, {created_count} creadas, {updated_count} actualizadas, {len(errors)} errores")
                            
                            logger.info(f"[SCAN] Procesando imagen {processed_count}: {relative_path}")
                            
                            image_files.append({
                                "path": str(file_path),
                                "relative_path": relative_path
                            })
                            
                            # Si create_records=True, procesar y crear/actualizar registro
                            if create_records:
                                try:
                                    folder_node = await self._ensure_folder_node_for_relative_path(
                                        folder_id=folder_id,
                                        folder_name=folder_name,
                                        relative_path=relative_path,
                                        node_cache=node_cache,
                                    )
                                    logger.info(f"[SCAN] Llamando a _create_or_update_image_record para: {relative_path}")
                                    processed = await self._create_or_update_image_record(
                                        folder_id=folder_id,
                                        folder_path=folder_path,
                                        file_path=file_path,
                                        relative_path=relative_path,
                                        folder_node_id=folder_node.id,
                                    )
                                    logger.info(f"[SCAN] Resultado de _create_or_update_image_record: {processed}")
                                    if processed.get('created'):
                                        created_count += 1
                                        logger.info(f"[SCAN] ✓ Imagen CREADA: {relative_path} (Total creadas: {created_count})")
                                        if created_count % 10 == 0:
                                            logger.info(f"[SCAN] {created_count} imágenes creadas hasta ahora...")
                                    elif processed.get('updated'):
                                        updated_count += 1
                                        logger.info(f"[SCAN] ✓ Imagen ACTUALIZADA: {relative_path} (Total actualizadas: {updated_count})")
                                    else:
                                        logger.warning(f"[SCAN] ⚠ Resultado inesperado de _create_or_update_image_record: {processed}")
                                except Exception as e:
                                    error_msg = f"Error al crear registro para {relative_path}: {str(e)}"
                                    errors.append(error_msg)
                                    logger.error(f"[SCAN] ✗ {error_msg}", exc_info=True)
                                    # Un rollback expira los FolderNode cacheados. Recargarlos
                                    # evita que el siguiente archivo intente lazy-loading async.
                                    await self.db.rollback()
                                    node_cache = await self._load_folder_nodes_cache(folder_id)
                                    await self._ensure_root_node(folder_id, folder_name, node_cache)
                    except Exception as e:
                        error_msg = f"Error al procesar {file_path}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(f"[SCAN] ✗ Error procesando archivo {file_path}: {error_msg}", exc_info=True)
            else:
                # Escaneo no recursivo (solo primer nivel)
                for file_path in folder_path.iterdir():
                    total_files += 1
                    try:
                        if self._is_image_file(file_path):
                            relative_path = file_path.name
                            image_files.append({
                                "path": str(file_path),
                                "relative_path": relative_path
                            })
                            
                            # Si create_records=True, procesar y crear/actualizar registro
                            if create_records:
                                try:
                                    folder_node = await self._ensure_folder_node_for_relative_path(
                                        folder_id=folder_id,
                                        folder_name=folder_name,
                                        relative_path=relative_path,
                                        node_cache=node_cache,
                                    )
                                    processed = await self._create_or_update_image_record(
                                        folder_id=folder_id,
                                        folder_path=folder_path,
                                        file_path=file_path,
                                        relative_path=relative_path,
                                        folder_node_id=folder_node.id,
                                    )
                                    if processed['created']:
                                        created_count += 1
                                        logger.debug(f"[SCAN] Imagen creada: {relative_path} (Total creadas: {created_count})")
                                    elif processed['updated']:
                                        updated_count += 1
                                        logger.debug(f"[SCAN] Imagen actualizada: {relative_path} (Total actualizadas: {updated_count})")
                                except Exception as e:
                                    error_msg = f"Error al crear registro para {relative_path}: {str(e)}"
                                    errors.append(error_msg)
                                    logger.error(f"[SCAN] {error_msg}", exc_info=True)
                                    await self.db.rollback()
                                    node_cache = await self._load_folder_nodes_cache(folder_id)
                                    await self._ensure_root_node(folder_id, folder_name, node_cache)
                    except Exception as e:
                        error_msg = f"Error al procesar {file_path}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(f"[SCAN] ✗ Error procesando archivo {file_path}: {error_msg}", exc_info=True)
        except Exception as e:
            error_msg = f"Error general al escanear carpeta: {str(e)}"
            errors.append(error_msg)
            logger.error(f"[SCAN] ✗ Error general: {error_msg}", exc_info=True)
        
        # Actualizar last_scan_at si create_records=True
        if create_records:
            try:
                # Recargar folder para actualizar last_scan_at (necesitamos el objeto actualizado)
                result = await self.db.execute(select(Folder).where(Folder.id == folder_id))
                folder_for_update = result.scalar_one_or_none()
                if folder_for_update:
                    folder_for_update.last_scan_at = datetime.now()
                    await self.db.commit()
                    await self.db.refresh(folder_for_update)
                logger.info(f"[SCAN] Escaneo completado: {len(image_files)} imágenes encontradas, {created_count} creadas, {updated_count} actualizadas, {len(errors)} errores")
                
                # Mostrar resumen de errores si hay muchos
                if len(errors) > 0:
                    logger.warning(f"[SCAN] ⚠ Se encontraron {len(errors)} errores durante el escaneo")
                    # Mostrar los primeros 10 errores como ejemplo
                    for i, error in enumerate(errors[:10], 1):
                        logger.warning(f"[SCAN] Error {i}/{len(errors)}: {error}")
                    if len(errors) > 10:
                        logger.warning(f"[SCAN] ... y {len(errors) - 10} errores más (ver lista completa en respuesta)")
            except Exception as e:
                logger.error(f"[SCAN] Error al actualizar last_scan_at: {e}", exc_info=True)
                await self.db.rollback()
        
        # Detectar imágenes huérfanas DESPUÉS de actualizar la DB
        # Esto garantiza que todos los registros estén actualizados antes de la verificación
        orphaned_images = []
        if create_records:
            logger.info(f"[ORPHANED] Iniciando detección de imágenes huérfanas para carpeta {folder_id}")
            orphaned_images = await self._detect_orphaned_images(folder_id, folder_path)
            if orphaned_images:
                logger.warning(f"[ORPHANED] DETECCIÓN COMPLETADA: {len(orphaned_images)} imágenes huérfanas encontradas")
            else:
                logger.info(f"[ORPHANED] DETECCIÓN COMPLETADA: No se encontraron imágenes huérfanas")
        
        result = {
            "folder_id": folder_id,
            "folder_path": str(folder_path),
            "total_files": total_files,
            "image_files": image_files,
            "image_count": len(image_files),
            "errors": errors,
            "orphaned_images": orphaned_images
        }
        
        if create_records:
            result["created_count"] = created_count
            result["updated_count"] = updated_count
            
            # Publicar evento de escaneo completado
            await event_bus.publish_async(Event(
                event_type=EventType.FOLDER_SCANNED,
                payload={
                    "folder_id": folder_id,
                    "folder_path": str(folder_path),
                    "total_files": total_files,
                    "image_count": len(image_files),
                    "created": created_count,
                    "updated": updated_count,
                    "errors": errors
                }
            ))
        
        return result
    
    async def _detect_orphaned_images(self, folder_id: str, folder_path: Path) -> List[Dict[str, Any]]:
        """
        Detecta imágenes que están en la DB pero:
        1. No existen físicamente
        2. Existen físicamente pero no se pueden leer/procesar (corruptas)
        
        Args:
            folder_id: ID de la carpeta
            folder_path: Ruta física de la carpeta
            
        Returns:
            Lista de diccionarios con información de imágenes huérfanas o problemáticas
        """
        orphaned = []
        
        try:
            logger.info(f"[ORPHANED] ===== INICIANDO DETECCIÓN DE IMÁGENES HUÉRFANAS/PROBLEMÁTICAS =====")
            logger.info(f"[ORPHANED] Carpeta ID: {folder_id}")
            logger.info(f"[ORPHANED] Ruta física: {folder_path}")
            
            # Obtener todas las imágenes de esta carpeta desde la DB
            result = await self.db.execute(
                select(Image).where(Image.folder_id == folder_id)
            )
            db_images = result.scalars().all()
            
            logger.info(f"[ORPHANED] Verificando {len(db_images)} imágenes en DB para carpeta {folder_id}")
            
            for idx, image in enumerate(db_images, 1):
                # Construir la ruta física completa
                # image.path es relativa a la carpeta
                try:
                    physical_path = folder_path / image.path
                    
                    logger.debug(f"[ORPHANED] [{idx}/{len(db_images)}] Verificando: {image.path}")
                    logger.debug(f"[ORPHANED]   ID: {image.id}, GUID: {image.guid}")
                    logger.debug(f"[ORPHANED]   Ruta completa: {physical_path}")
                    
                    # Verificar si el archivo existe físicamente
                    if not physical_path.exists():
                        logger.warning(f"[ORPHANED] ❌ Archivo NO EXISTE: {physical_path}")
                        orphaned.append({
                            'id': image.id,
                            'guid': image.guid,
                            'path': image.path,
                            'folder_id': image.folder_id,
                            'thumb_path': image.thumb_path,
                            'reason': 'not_exists'
                        })
                    elif not physical_path.is_file():
                        logger.warning(f"[ORPHANED] ❌ NO ES UN ARCHIVO (es directorio): {physical_path}")
                        orphaned.append({
                            'id': image.id,
                            'guid': image.guid,
                            'path': image.path,
                            'folder_id': image.folder_id,
                            'thumb_path': image.thumb_path,
                            'reason': 'not_file'
                        })
                    else:
                        # El archivo existe, verificar si se puede leer/procesar
                        can_read = False
                        read_error = None
                        try:
                            if PIL_AVAILABLE:
                                test_img = PILImage.open(physical_path)
                                test_img.verify()  # Verificar integridad
                                test_img.close()
                                # Reabrir para verificar que se puede leer completamente
                                test_img = PILImage.open(physical_path)
                                test_img.load()  # Cargar completamente
                                test_img.close()
                                can_read = True
                                logger.debug(f"[ORPHANED] ✅ Archivo existe y es válido: {physical_path}")
                            else:
                                # Si PIL no está disponible, asumir que se puede leer
                                can_read = True
                                logger.debug(f"[ORPHANED] ✅ Archivo existe (PIL no disponible para validar): {physical_path}")
                        except Exception as read_err:
                            # El archivo existe pero no se puede leer/procesar
                            can_read = False
                            read_error = str(read_err)
                            logger.warning(f"[ORPHANED] ⚠️ Archivo existe pero NO SE PUEDE LEER: {physical_path}")
                            logger.warning(f"[ORPHANED]   Error: {read_error}")
                        
                        if not can_read:
                            orphaned.append({
                                'id': image.id,
                                'guid': image.guid,
                                'path': image.path,
                                'folder_id': image.folder_id,
                                'thumb_path': image.thumb_path,
                                'reason': 'cannot_read',
                                'error': read_error
                            })
                        
                except Exception as e:
                    logger.error(f"[ORPHANED] Error verificando imagen ID={image.id}: {e}")
                    # Si hay error al construir la ruta, también considerarla huérfana
                    orphaned.append({
                        'id': image.id,
                        'guid': image.guid,
                        'path': image.path,
                        'folder_id': image.folder_id,
                        'thumb_path': image.thumb_path,
                        'reason': 'error',
                        'error': str(e)
                    })
            
            if orphaned:
                logger.warning(f"[ORPHANED] ===== RESULTADO: {len(orphaned)} IMÁGENES HUÉRFANAS/PROBLEMÁTICAS ENCONTRADAS =====")
                for img in orphaned[:5]:  # Mostrar las primeras 5
                    reason = img.get('reason', 'unknown')
                    logger.warning(f"[ORPHANED]   - ID: {img['id']}, Path: {img['path']}, Razón: {reason}")
                if len(orphaned) > 5:
                    logger.warning(f"[ORPHANED]   ... y {len(orphaned) - 5} más")
            else:
                logger.info(f"[ORPHANED] ===== RESULTADO: NO SE ENCONTRARON IMÁGENES HUÉRFANAS =====")
                
        except Exception as e:
            logger.error(f"[ORPHANED] Error detectando imágenes huérfanas: {e}", exc_info=True)
        
        return orphaned
    
    async def cleanup_orphaned_images(self, folder_id: str, image_ids: List[int]) -> Dict[str, Any]:
        """
        Elimina imágenes huérfanas de la base de datos.
        Si el archivo existe físicamente, lo mueve a la papelera antes de eliminarlo de la BD.
        
        Args:
            folder_id: ID de la carpeta
            image_ids: Lista de IDs de imágenes a eliminar
            
        Returns:
            Diccionario con el resultado de la limpieza
        """
        deleted_count = 0
        moved_to_trash_count = 0
        errors = []
        
        try:
            # Obtener la ruta de papelera desde settings
            trash_result = await self.db.execute(
                select(Setting).where(Setting.key == SettingKeys.TRASH_PATH)
            )
            trash_setting = trash_result.scalar_one_or_none()
            trash_path = None
            
            if trash_setting and trash_setting.value:
                trash_path = Path(trash_setting.value)
                trash_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"[CLEANUP] Ruta de papelera configurada: {trash_path}")
            else:
                logger.warning(f"[CLEANUP] Ruta de papelera no configurada, los archivos no se moverán a papelera")
            
            # Obtener o crear carpeta de papelera en la BD (si existe trash_path)
            trash_folder = None
            if trash_path:
                trash_folder_result = await self.db.execute(
                    select(Folder).where(Folder.path == str(trash_path))
                )
                trash_folder = trash_folder_result.scalar_one_or_none()
                
                if not trash_folder:
                    # Crear carpeta de papelera en la DB si no existe (con enabled=False)
                    folder_id_hash = md5(str(trash_path).encode()).hexdigest()
                    trash_folder = Folder(
                        id=folder_id_hash,
                        path=str(trash_path),
                        name="Papelera",
                        enabled=False  # IMPORTANTE: No se carga automáticamente
                    )
                    self.db.add(trash_folder)
                    await self.db.flush()
                    logger.info(f"[CLEANUP] Carpeta papelera creada en BD (enabled=False): {folder_id_hash}")
            
            # Verificar que las imágenes pertenecen a la carpeta
            for image_id in image_ids:
                try:
                    result = await self.db.execute(
                        select(Image).where(Image.id == image_id, Image.folder_id == folder_id)
                    )
                    image = result.scalar_one_or_none()
                    
                    if not image:
                        errors.append(f"Imagen ID {image_id} no encontrada o no pertenece a la carpeta {folder_id}")
                        continue
                    
                    # Obtener la carpeta original
                    folder_result = await self.db.execute(
                        select(Folder).where(Folder.id == image.folder_id)
                    )
                    folder = folder_result.scalar_one_or_none()
                    
                    if not folder:
                        errors.append(f"Carpeta con ID {image.folder_id} no encontrada para imagen {image_id}")
                        continue
                    
                    # Construir ruta completa del archivo
                    original_folder_path = Path(folder.path)
                    original_file_path = original_folder_path / image.path
                    
                    # Si el archivo existe físicamente, moverlo a la papelera
                    if original_file_path.exists() and original_file_path.is_file() and trash_path and trash_folder:
                        try:
                            # Determinar nuevo nombre en papelera (evitar duplicados)
                            filename = original_file_path.name
                            dest_file_path = trash_path / filename
                            
                            # Si ya existe, agregar un número incremental
                            counter = 1
                            while dest_file_path.exists():
                                stem = original_file_path.stem
                                suffix = original_file_path.suffix
                                dest_file_path = trash_path / f"{stem}_{counter}{suffix}"
                                counter += 1
                            
                            # Mover archivo físico
                            shutil.move(str(original_file_path), str(dest_file_path))
                            logger.info(f"[CLEANUP] Archivo movido a papelera: {original_file_path} -> {dest_file_path}")
                            
                            # Mover thumbnail si existe
                            if image.thumb_path:
                                thumb_original = original_folder_path / image.thumb_path
                                if thumb_original.exists():
                                    thumb_dest = trash_path / thumb_original.name
                                    if not thumb_dest.exists():
                                        shutil.move(str(thumb_original), str(thumb_dest))
                                        logger.info(f"[CLEANUP] Thumbnail movido a papelera: {thumb_original} -> {thumb_dest}")
                            
                            moved_to_trash_count += 1
                        except Exception as move_error:
                            logger.warning(f"[CLEANUP] No se pudo mover archivo a papelera (se eliminará de BD): {move_error}")
                            # Continuar con la eliminación de BD aunque falle el movimiento
                    
                    # Eliminar la imagen de la base de datos (las relaciones se eliminarán por CASCADE o por GUID)
                    await self.db.delete(image)
                    deleted_count += 1
                    logger.info(f"[CLEANUP] Imagen eliminada de BD: ID={image_id}, GUID={image.guid}, path={image.path}")
                    
                except Exception as e:
                    error_msg = f"Error eliminando imagen ID {image_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"[CLEANUP] {error_msg}", exc_info=True)
            
            await self.db.commit()
            logger.info(f"[CLEANUP] Limpieza completada: {deleted_count} imágenes eliminadas de BD, {moved_to_trash_count} archivos movidos a papelera, {len(errors)} errores")
            
        except Exception as e:
            await self.db.rollback()
            error_msg = f"Error durante limpieza de imágenes huérfanas: {str(e)}"
            logger.error(f"[CLEANUP] {error_msg}", exc_info=True)
            raise ValueError(error_msg)
        
        return {
            'deleted_count': deleted_count,
            'moved_to_trash_count': moved_to_trash_count,
            'errors': errors
        }
    
    async def _create_or_update_image_record(
        self,
        folder_id: str,
        folder_path: Path,
        file_path: Path,
        relative_path: str,
        folder_node_id: int | None = None,
    ) -> Dict[str, bool]:
        """
        Crea o actualiza un registro de imagen en la BD
        
        Args:
            folder_id: ID de la carpeta
            folder_path: Path de la carpeta base
            file_path: Path absoluto del archivo de imagen
            relative_path: Ruta relativa del archivo desde la carpeta base
            
        Returns:
            Dict con {"created": bool, "updated": bool}
        """
        logger.info(f"[CREATE/UPDATE] Iniciando procesamiento de imagen: {relative_path}")
        
        # Procesar la imagen para obtener metadatos básicos
        try:
            image_info = self._process_image_file(file_path)
            logger.info(f"[CREATE/UPDATE] Imagen procesada: {relative_path} - {image_info.get('width')}x{image_info.get('height')}, size={image_info.get('size')}")
        except Exception as e:
            logger.error(f"[CREATE/UPDATE] Error procesando imagen {relative_path}: {e}", exc_info=True)
            raise
        
        # Extraer metadata AI (ComfyUI, SD WebUI)
        try:
            metadata = self.metadata_service.extract_metadata(file_path)
            logger.debug(f"Metadata extraída para {relative_path}: source={metadata.source}")
        except Exception as e:
            logger.error(f"Error extrayendo metadata de {relative_path}: {str(e)}", exc_info=True)
            # Crear metadata vacía en caso de error
            metadata = ImageMetadata(source='none')

        prompt_json = sanitize_json_for_database(metadata.prompt_json) if metadata.prompt_json else None
        workflow_json = sanitize_json_for_database(metadata.workflow_json) if metadata.workflow_json else None
        
        # Generar thumbnail
        # Asegurar que file_path es un Path
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        
        generated_thumb = self._generate_thumbnail(file_path)
        if not generated_thumb:
            logger.warning(f"[CREATE/UPDATE] No se pudo generar thumbnail para: {relative_path}")
            thumb_path = None
        else:
            # Guardar ruta del thumbnail relativa a la carpeta raíz registrada.
            # Ejemplo:
            # - imagen raíz: "img.png" -> "thumb/img.jpg"
            # - subcarpeta: "sub1/img.png" -> "sub1/thumb/img.jpg"
            rel_parent = Path(relative_path).parent
            thumb_filename = f"{file_path.stem}.jpg"
            if str(rel_parent) in ("", "."):
                thumb_path = str(Path("thumb") / thumb_filename)
            else:
                thumb_path = str(rel_parent / "thumb" / thumb_filename)
        
        # ====================================================================
        # GESTIÓN DE IDENTIFICADOR: Usar hash del contenido del archivo
        # ====================================================================
        # Generar identificador único basado en el hash del contenido del archivo
        # Esto es más confiable que GUIDs en PNGs y siempre funciona
        logger.info(f"[GUID] Generando hash del contenido para: {relative_path}")
        try:
            image_guid = generate_content_hash_guid(file_path)
            if not image_guid or len(image_guid) < 10:
                raise ValueError(f"generate_content_hash_guid retornó valor inválido: {image_guid}")
            logger.info(f"[GUID] Hash del contenido generado: {image_guid[:8]}... para {relative_path}")
        except Exception as hash_error:
            logger.error(f"[GUID] Error generando hash del contenido para {relative_path}: {hash_error}", exc_info=True)
            # Si falla el hash, lanzar el error para que se capture arriba
            raise
        
        content_guid = image_guid

        # La identidad primaria durante un escaneo es la ubicación física. Dos
        # archivos con el mismo contenido deben poder verse y gestionarse por separado.
        logger.debug(f"[GUID] Buscando por ubicación: folder_id={folder_id}, path={relative_path}")
        result = await self.db.execute(
            select(Image).where(
                Image.folder_id == folder_id,
                Image.path == relative_path,
            )
        )
        existing_image = result.scalar_one_or_none()

        if existing_image:
            logger.info(f"[GUID] Imagen encontrada por ubicación para {relative_path} (ID: {existing_image.id})")
            if existing_image.guid:
                image_guid = existing_image.guid
            else:
                collision_result = await self.db.execute(
                    select(Image.id).where(Image.guid == content_guid, Image.id != existing_image.id)
                )
                image_guid = (
                    build_location_guid(content_guid, folder_id, relative_path)
                    if collision_result.scalar_one_or_none() is not None
                    else content_guid
                )
        else:
            collision_result = await self.db.execute(
                select(Image.id, Image.folder_id, Image.path).where(Image.guid == content_guid)
            )
            collision = collision_result.first()
            if collision:
                image_guid = build_location_guid(content_guid, folder_id, relative_path)
                logger.info(
                    f"[GUID] Contenido duplicado del registro {collision.id}; "
                    f"se crea una identidad propia para {relative_path}."
                )
            logger.info(f"[GUID] Imagen nueva en esta ubicación. Creando nuevo registro...")
        
        if existing_image:
            # Actualizar registro existente
            logger.debug(f"Actualizando imagen existente ID {existing_image.id}: path={relative_path}")
            existing_image.size = image_info['size']
            existing_image.width = image_info['width']
            existing_image.height = image_info['height']
            existing_image.folder_node_id = folder_node_id
            # Conservar el GUID estable de la ubicación; solo completar si faltaba.
            if not existing_image.guid:
                existing_image.guid = image_guid
                logger.debug(f"[GUID] GUID actualizado en DB: {image_guid[:8]}... para imagen ID {existing_image.id}")
            # Actualizar thumbnail si se generó uno nuevo
            if thumb_path:
                existing_image.thumb_path = thumb_path
            # Actualizar metadata AI (siempre actualizar, incluso si es None para limpiar datos antiguos)
            existing_image.prompt_json = prompt_json
            existing_image.workflow_json = workflow_json
            
            try:
                await self.db.flush()
                await self.db.commit()
                await self.db.refresh(existing_image)
                
                # Guardar valores en variables locales para evitar lazy-load después del commit
                image_id = existing_image.id
                image_path_db = existing_image.path
                image_thumb_path = existing_image.thumb_path
                
                logger.info(f"Imagen actualizada exitosamente: id={image_id}, path={image_path_db}, thumb_path={image_thumb_path}, guid={image_guid[:8]}...")
            except Exception as commit_error:
                # Si el commit falla, hacer rollback y relanzar el error
                await self.db.rollback()
                logger.error(f"Error al hacer commit de actualización de imagen {relative_path}: {commit_error}", exc_info=True)
                raise
            
            # Verificar que se guardó correctamente
            logger.debug(f"Verificando guardado: prompt_json={existing_image.prompt_json is not None}, workflow_json={existing_image.workflow_json is not None}")
            
            return {"created": False, "updated": True}
        else:
            # Crear nuevo registro
            logger.info(f"[CREATE] Creando nuevo registro de imagen: path={relative_path}, guid={image_guid[:8]}...")
            new_image = Image(
                folder_id=folder_id,
                folder_node_id=folder_node_id,
                path=relative_path,  # Solo nombre del archivo o ruta relativa
                guid=image_guid,  # GUID único persistente (hash del contenido)
                size=image_info['size'],
                width=image_info['width'],
                height=image_info['height'],
                thumb_path=thumb_path,  # Ruta relativa a la carpeta raíz (respeta subcarpetas)
                prompt_json=prompt_json,
                workflow_json=workflow_json,
            )
            
            logger.info(f"[CREATE] Agregando imagen a la sesión de BD: guid={image_guid[:8]}...")
            self.db.add(new_image)
            try:
                logger.info(f"[CREATE] Haciendo flush de la imagen...")
                await self.db.flush()  # Flush antes de commit para obtener el ID
                logger.info(f"[CREATE] Haciendo commit de la imagen...")
                await self.db.commit()
                await self.db.refresh(new_image)
                
                # Guardar valores en variables locales para evitar lazy-load después del commit
                new_image_id = new_image.id
                new_image_path = new_image.path
                
                logger.info(f"[CREATE] Imagen guardada exitosamente: id={new_image_id}, path={new_image_path}, guid={image_guid[:8]}...")
            except Exception as commit_error:
                # Si el commit falla, hacer rollback y relanzar el error
                await self.db.rollback()
                logger.error(f"[CREATE] Error al hacer commit de imagen {relative_path}: {commit_error}", exc_info=True)
                raise
            
            # Publicar evento de imagen escaneada
            await event_bus.publish_async(Event(
                event_type=EventType.IMAGE_SCANNED,
                payload={
                    "image_id": new_image_id,
                    "image_guid": image_guid,
                    "folder_id": folder_id,
                    "path": relative_path,
                    "created": True
                }
            ))
            
            return {"created": True, "updated": False}
    
    def _process_image_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Procesa un archivo de imagen individual y extrae información básica
        (tamaño del archivo y dimensiones)
        
        Args:
            file_path: Path del archivo de imagen
            
        Returns:
            Dict con información de la imagen:
            {
                "path": str,
                "size": int,  # Tamaño en bytes
                "width": int | None,  # Ancho en píxeles
                "height": int | None,  # Alto en píxeles
                "format": str | None  # Formato de la imagen (PNG, JPEG, etc.)
            }
            
        Raises:
            ValueError: Si el archivo no existe o no es una imagen válida
        """
        if not file_path.exists():
            raise ValueError(f"El archivo no existe: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"La ruta no es un archivo: {file_path}")
        
        # Obtener tamaño del archivo
        file_size = file_path.stat().st_size
        
        result = {
            "path": str(file_path),
            "size": file_size,
            "width": None,
            "height": None,
            "format": None
        }
        
        # Intentar leer dimensiones con PIL/Pillow
        if PIL_AVAILABLE and PILImage:
            try:
                # Intentar abrir normalmente
                img = PILImage.open(file_path)
                try:
                    img.verify()
                except Exception:
                    img.close()
                    raise PILImage.UnidentifiedImageError("Imagen no válida")
                img.close()
                img = PILImage.open(file_path)
                
                result["width"] = img.width
                result["height"] = img.height
                result["format"] = img.format
                logger.info(f"[_process_image_file] Imagen leída exitosamente: {file_path.name} - {img.width}x{img.height} ({img.format})")
                img.close()
            except Exception as e:
                logger.error(f"[_process_image_file] Error al leer imagen {file_path.name}: {e}")
                # Si la imagen está corrupta o no se puede leer, dejamos width/height como None
                # No intentamos repararla, simplemente la ignoramos
        
        return result

    @staticmethod
    def _thumb_rel_for_image_path(image_rel_path: str) -> str:
        p = Path(image_rel_path)
        rel_parent = p.parent
        thumb_filename = f"{p.stem}.jpg"
        if str(rel_parent) in ("", "."):
            return str(Path("thumb") / thumb_filename)
        return str(rel_parent / "thumb" / thumb_filename)

    async def get_folder_node_in_root(self, folder_id: str, node_id: int) -> Optional[FolderNode]:
        result = await self.db.execute(
            select(FolderNode).where(
                FolderNode.id == node_id,
                FolderNode.folder_root_id == folder_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_folder_node_nomenclature(
        self,
        folder_id: str,
        node_id: int,
        naming_base: Optional[str],
        naming_number_width: Optional[int],
    ) -> FolderNode:
        node = await self.get_folder_node_in_root(folder_id, node_id)
        if not node:
            raise ValueError("folder_node_not_found")

        if naming_base is None and naming_number_width is None:
            node.naming_base = None
            node.naming_number_width = None
        elif naming_base and naming_number_width is not None and naming_number_width >= 1:
            node.naming_base = naming_base.strip()
            node.naming_number_width = int(naming_number_width)
        else:
            raise ValueError("nomenclature_invalid")

        await self.db.commit()
        await self.db.refresh(node)
        return node

    async def list_images_for_folder_node(self, folder_id: str, node_id: int) -> List[Image]:
        result = await self.db.execute(
            select(Image).where(
                Image.folder_id == folder_id,
                Image.folder_node_id == node_id,
            )
        )
        return list(result.scalars().all())

    def _build_rename_plan_for_node(
        self,
        *,
        node: FolderNode,
        images: List[Image],
        mode: Literal["all", "selected"],
        selected_ids: Optional[List[int]],
    ) -> Tuple[NamingPlanResult, List[ImageRow]]:
        base = (node.naming_base or "").strip()
        width = node.naming_number_width
        if not base or width is None or width < 1:
            raise ValueError("nomenclature_not_configured")

        for img in images:
            suf = Path(img.path).suffix.lower()
            if suf not in SUPPORTED_IMAGE_EXTENSIONS:
                raise ValueError(f"unsupported_extension:{img.path}")

        rows = [ImageRow(id=img.id, path=str(img.path).replace("\\", "/")) for img in images]
        try:
            plan = build_rename_plan(
                naming_base=base,
                naming_number_width=int(width),
                all_rows=rows,
                mode=mode,
                selected_ids=frozenset(selected_ids) if mode == "selected" else None,
            )
        except NamingPlanError as e:
            raise ValueError(str(e)) from e
        return plan, rows

    async def preview_rename_folder_node(
        self,
        folder_id: str,
        node_id: int,
        mode: Literal["all", "selected"],
        selected_ids: Optional[List[int]],
    ) -> Dict[str, Any]:
        node = await self.get_folder_node_in_root(folder_id, node_id)
        if not node:
            raise ValueError("folder_node_not_found")
        images = await self.list_images_for_folder_node(folder_id, node_id)
        plan, _rows = self._build_rename_plan_for_node(
            node=node, images=images, mode=mode, selected_ids=selected_ids
        )
        return {
            "folder_id": folder_id,
            "folder_node_id": node_id,
            "next_counter_start": plan.next_counter_start,
            "related_count": plan.related_count,
            "unrelated_count": plan.unrelated_count,
            "unchanged_count": plan.unchanged_count,
            "entries": [
                {
                    "image_id": e.image_id,
                    "old_path": e.old_path,
                    "new_path": e.new_path,
                    "reason": e.reason,
                    "name_class": e.name_class.value if e.name_class else None,
                }
                for e in plan.entries
            ],
        }

    async def apply_rename_folder_node(
        self,
        folder_id: str,
        node_id: int,
        mode: Literal["all", "selected"],
        selected_ids: Optional[List[int]],
    ) -> Dict[str, Any]:
        folder_result = await self.db.execute(select(Folder).where(Folder.id == folder_id))
        folder = folder_result.scalar_one_or_none()
        if not folder:
            raise ValueError("folder_not_found")

        node = await self.get_folder_node_in_root(folder_id, node_id)
        if not node:
            raise ValueError("folder_node_not_found")

        images = await self.list_images_for_folder_node(folder_id, node_id)
        by_id = {img.id: img for img in images}
        plan, _rows = self._build_rename_plan_for_node(
            node=node, images=images, mode=mode, selected_ids=selected_ids
        )

        renames: List[Tuple[Image, str, str]] = []
        for e in plan.entries:
            if e.reason != "rename" or not e.new_path:
                continue
            img = by_id.get(e.image_id)
            if not img:
                raise ValueError("image_missing")
            if str(img.path).replace("\\", "/") != e.old_path:
                raise ValueError("path_drift")
            if e.new_path == e.old_path:
                continue
            renames.append((img, e.old_path, e.new_path))

        root = Path(folder.path).resolve()
        image_moves: List[Tuple[Path, Path]] = []
        thumb_moves: List[Tuple[Path, Path]] = []

        try:
            for img, old_rel, new_rel in renames:
                src = (root / old_rel).resolve()
                dst = (root / new_rel).resolve()
                if not str(src).startswith(str(root)) or not str(dst).startswith(str(root)):
                    raise ValueError("path_escape")
                if not src.is_file():
                    raise ValueError(f"missing_file:{old_rel}")
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    raise ValueError(f"target_exists:{new_rel}")

                await asyncio.to_thread(lambda a=src, b=dst: a.rename(b))
                image_moves.append((src, dst))

                new_thumb_rel = self._thumb_rel_for_image_path(new_rel).replace("\\", "/")
                if img.thumb_path:
                    old_thumb = (root / str(img.thumb_path)).resolve()
                    if str(old_thumb).startswith(str(root)) and old_thumb.is_file():
                        new_thumb = (root / new_thumb_rel).resolve()
                        new_thumb.parent.mkdir(parents=True, exist_ok=True)
                        if new_thumb.exists() and new_thumb != old_thumb:
                            raise ValueError(f"thumb_target_exists:{new_thumb_rel}")

                        await asyncio.to_thread(lambda a=old_thumb, b=new_thumb: a.rename(b))
                        thumb_moves.append((old_thumb, new_thumb))
                    img.thumb_path = new_thumb_rel

                img.path = new_rel.replace("\\", "/")

            await self.db.commit()
        except Exception:
            for old_t, new_t in reversed(thumb_moves):
                if new_t.is_file() and not old_t.exists():
                    try:
                        await asyncio.to_thread(lambda fr=new_t, to=old_t: fr.rename(to))
                    except OSError:
                        logger.error(
                            "thumb_rename_rollback_failed",
                            extra={"from": str(new_t), "to": str(old_t)},
                        )
            for src_p, dst_p in reversed(image_moves):
                if dst_p.is_file() and not src_p.exists():
                    try:
                        await asyncio.to_thread(lambda fr=dst_p, to=src_p: fr.rename(to))
                    except OSError:
                        logger.error(
                            "rename_rollback_failed",
                            extra={"from": str(dst_p), "to": str(src_p)},
                        )
            await self.db.rollback()
            raise

        renamed = len(renames)
        logger.info(
            "gallery_rename_applied",
            extra={
                "folder_id": folder_id,
                "folder_node_id": node_id,
                "renamed": renamed,
            },
        )
        return {"renamed": renamed, "folder_id": folder_id, "folder_node_id": node_id}

    async def _master_naming_workset(self) -> Dict[str, Any]:
        setting_result = await self.db.execute(
            select(Setting).where(Setting.key == SettingKeys.IMG_MASTER_PATH)
        )
        setting = setting_result.scalar_one_or_none()
        master_path = str(setting.value or "").strip() if setting else ""
        if not master_path:
            raise ValueError("No hay una ruta maestra configurada.")

        physical_roots = list_master_roots(master_path)
        root_paths = {canonicalize_path(str(path)): path for path in physical_roots}
        folder_result = await self.db.execute(select(Folder))
        folders = [
            folder
            for folder in folder_result.scalars().all()
            if canonicalize_path(str(folder.path)) in root_paths
        ]
        if not folders:
            raise ValueError("No hay carpetas de la ruta maestra indexadas. Sincroniza primero la carpeta maestra.")

        folder_ids = [str(folder.id) for folder in folders]
        nodes_result = await self.db.execute(
            select(FolderNode).where(FolderNode.folder_root_id.in_(folder_ids))
        )
        nodes = list(nodes_result.scalars().all())
        images_result = await self.db.execute(
            select(Image).where(Image.folder_id.in_(folder_ids))
        )
        images = list(images_result.scalars().all())

        nodes_by_id = {int(node.id): node for node in nodes}
        nodes_by_rel = {
            (str(node.folder_root_id), str(node.rel_path or "").replace("\\", "/").strip("/").casefold()): node
            for node in nodes
        }
        grouped: Dict[Tuple[str, int], List[Image]] = {}
        unassigned = 0
        for image in images:
            node = nodes_by_id.get(int(image.folder_node_id)) if image.folder_node_id is not None else None
            if node is None:
                parent = Path(str(image.path).replace("\\", "/")).parent
                parent_rel = "" if str(parent) in ("", ".") else str(parent).replace("\\", "/").strip("/")
                node = nodes_by_rel.get((str(image.folder_id), parent_rel.casefold()))
            if node is None:
                unassigned += 1
                continue
            grouped.setdefault((str(image.folder_id), int(node.id)), []).append(image)

        folder_by_id = {str(folder.id): folder for folder in folders}
        groups: List[Dict[str, Any]] = []
        unchanged_count = 0
        for (folder_id, node_id), node_images in grouped.items():
            node = nodes_by_id[node_id]
            plan = build_missing_naming_plan(
                folder_name=str(node.name),
                all_rows=[
                    ImageRow(id=int(image.id), path=str(image.path).replace("\\", "/"))
                    for image in node_images
                ],
            )
            unchanged_count += plan.unchanged_count
            groups.append(
                {
                    "folder": folder_by_id[folder_id],
                    "node": node,
                    "images": {int(image.id): image for image in node_images},
                    "plan": plan,
                }
            )

        groups.sort(
            key=lambda item: (
                str(item["folder"].name).casefold(),
                str(item["node"].rel_path).casefold(),
            )
        )
        return {
            "master_path": str(Path(master_path).resolve()),
            "folders_scanned": len(folders),
            "folder_nodes_scanned": len(nodes),
            "images_scanned": len(images),
            "unchanged_count": unchanged_count,
            "unassigned_count": unassigned,
            "groups": groups,
        }

    @staticmethod
    def _master_naming_response(workset: Dict[str, Any], *, renamed_count: int | None = None) -> Dict[str, Any]:
        entries: List[Dict[str, Any]] = []
        rename_count = 0
        for group in workset["groups"]:
            folder = group["folder"]
            node = group["node"]
            for entry in group["plan"].entries:
                rename_count += 1
                if len(entries) < 500:
                    entries.append(
                        {
                            "image_id": int(entry.image_id),
                            "folder_id": str(folder.id),
                            "folder_name": str(node.name),
                            "old_path": str(entry.old_path),
                            "new_path": str(entry.new_path),
                        }
                    )
        response = {
            "master_path": workset["master_path"],
            "folders_scanned": int(workset["folders_scanned"]),
            "folder_nodes_scanned": int(workset["folder_nodes_scanned"]),
            "images_scanned": int(workset["images_scanned"]),
            "rename_count": rename_count,
            "unchanged_count": int(workset["unchanged_count"]),
            "unassigned_count": int(workset["unassigned_count"]),
            "entries": entries,
            "entries_truncated": rename_count > len(entries),
        }
        if renamed_count is not None:
            response["renamed_count"] = int(renamed_count)
        return response

    async def preview_master_missing_names(self) -> Dict[str, Any]:
        workset = await self._master_naming_workset()
        return self._master_naming_response(workset)

    async def apply_master_missing_names(self) -> Dict[str, Any]:
        workset = await self._master_naming_workset()
        image_moves: List[Tuple[Path, Path]] = []
        thumb_moves: List[Tuple[Path, Path]] = []

        try:
            for group in workset["groups"]:
                folder = group["folder"]
                root = Path(str(folder.path)).resolve()
                images_by_id: Dict[int, Image] = group["images"]
                for entry in group["plan"].entries:
                    image = images_by_id.get(int(entry.image_id))
                    if image is None or not entry.new_path:
                        raise ValueError("La imagen cambió mientras se preparaba el renombrado.")

                    old_rel = str(entry.old_path).replace("\\", "/")
                    new_rel = str(entry.new_path).replace("\\", "/")
                    src = (root / old_rel).resolve()
                    dst = (root / new_rel).resolve()
                    try:
                        src.relative_to(root)
                        dst.relative_to(root)
                    except ValueError as exc:
                        raise ValueError("Se detectó una ruta fuera de la carpeta registrada.") from exc
                    if not src.is_file():
                        raise ValueError(f"No existe la imagen: {old_rel}")
                    if dst.exists():
                        raise ValueError(f"Ya existe el nombre de destino: {new_rel}")

                    dst.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(lambda a=src, b=dst: a.rename(b))
                    image_moves.append((src, dst))

                    new_thumb_rel = self._thumb_rel_for_image_path(new_rel).replace("\\", "/")
                    if image.thumb_path:
                        old_thumb = (root / str(image.thumb_path)).resolve()
                        if old_thumb.is_file():
                            new_thumb = (root / new_thumb_rel).resolve()
                            try:
                                old_thumb.relative_to(root)
                                new_thumb.relative_to(root)
                            except ValueError as exc:
                                raise ValueError("Se detectó una miniatura fuera de la carpeta registrada.") from exc
                            new_thumb.parent.mkdir(parents=True, exist_ok=True)
                            if new_thumb.exists() and new_thumb != old_thumb:
                                raise ValueError(f"Ya existe la miniatura de destino: {new_thumb_rel}")
                            await asyncio.to_thread(lambda a=old_thumb, b=new_thumb: a.rename(b))
                            thumb_moves.append((old_thumb, new_thumb))
                        image.thumb_path = new_thumb_rel
                    image.path = new_rel

            await self.db.commit()
        except Exception:
            for old_thumb, new_thumb in reversed(thumb_moves):
                if new_thumb.is_file() and not old_thumb.exists():
                    old_thumb.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(lambda a=new_thumb, b=old_thumb: a.rename(b))
            for old_path, new_path in reversed(image_moves):
                if new_path.is_file() and not old_path.exists():
                    old_path.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(lambda a=new_path, b=old_path: a.rename(b))
            await self.db.rollback()
            raise

        return self._master_naming_response(workset, renamed_count=len(image_moves))


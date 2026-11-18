"""
Router - Endpoints API para el módulo Gallery
Paso 4.2 - Router Gallery - Listar Carpetas
Paso 4.4 - Router - Crear Carpeta
Paso 4.8 - Router - Escanear Carpeta
Paso 5.3 - Thumbnails
Rutas: /api/gallery/*
"""

from datetime import datetime
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, ConfigDict, Field
import json
import shutil
import logging
import re
import asyncio
from hashlib import md5
from uuid import uuid4

from ...shared.database import get_db
from ...shared.models import Setting, SettingKeys
from .service import GalleryService
from .models import Folder, Image, FolderNode, FolderTag, folder_node_tags
from .png_writer import PNGMetadataWriter
from .embedded_resources import build_linked_payload, extract_model_and_loras_from_json
from .dashboard_metrics import classify_folder_type_from_rel_path
from .workflow_json_mutate import apply_model_and_loras

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


class FolderCreate(BaseModel):
    """Request model para crear carpetas"""
    path: str = Field(..., min_length=1, description="Ruta absoluta de la carpeta en el sistema")
    name: str = Field(..., min_length=1, description="Nombre de la carpeta")
    enabled: bool = Field(True, description="Si la carpeta está habilitada para escaneo")


class FolderResponse(BaseModel):
    """Response model para carpetas"""
    id: str
    path: str
    name: str
    enabled: bool
    last_scan_at: datetime | None
    created_at: datetime
    image_count: int = 0  # Cantidad de imágenes en la carpeta
    
    model_config = ConfigDict(from_attributes=True)


class FolderTagResponse(BaseModel):
    id: int
    name: str
    color: str | None = None

    model_config = ConfigDict(from_attributes=True)


class FolderNodeTreeResponse(BaseModel):
    id: int
    folder_root_id: str
    parent_node_id: int | None = None
    rel_path: str
    name: str
    depth: int
    naming_base: Optional[str] = None
    naming_number_width: Optional[int] = None
    image_count: int = 0
    tag_ids: List[int] = []
    tags: List[FolderTagResponse] = []
    effective_tag_ids: List[int] = []
    effective_tags: List[FolderTagResponse] = []
    children: List["FolderNodeTreeResponse"] = []


class FolderTreeResponse(BaseModel):
    folder_id: str
    nodes: List[FolderNodeTreeResponse]


class UpdateFolderNodeTagsRequest(BaseModel):
    tag_ids: List[int] | None = None
    tags: List[str] | None = None


class FolderNodeNomenclatureUpdate(BaseModel):
    naming_base: Optional[str] = None
    naming_number_width: Optional[int] = None


class FolderNodeRenameRequest(BaseModel):
    mode: Literal["all", "selected"]
    image_ids: Optional[List[int]] = None


class FolderNodeRenamePreviewEntry(BaseModel):
    image_id: int
    old_path: str
    new_path: Optional[str] = None
    reason: Literal["unchanged", "rename"]
    name_class: Optional[str] = None


class FolderNodeRenamePreviewResponse(BaseModel):
    folder_id: str
    folder_node_id: int
    next_counter_start: int
    related_count: int
    unrelated_count: int
    unchanged_count: int
    entries: List[FolderNodeRenamePreviewEntry]


class FolderNodeRenameApplyResponse(BaseModel):
    renamed: int
    folder_id: str
    folder_node_id: int


class MasterNamingEntryResponse(BaseModel):
    image_id: int
    folder_id: str
    folder_name: str
    old_path: str
    new_path: str


class MasterNamingResponse(BaseModel):
    master_path: str
    folders_scanned: int
    folder_nodes_scanned: int
    images_scanned: int
    rename_count: int
    unchanged_count: int
    unassigned_count: int
    entries: List[MasterNamingEntryResponse]
    entries_truncated: bool = False
    renamed_count: Optional[int] = None


FolderNodeTreeResponse.model_rebuild()


def _delete_empty_source_directory(target: Path) -> bool:
    """Elimina una rama cuando no contiene archivos, aunque tenga subcarpetas vacías."""
    directories: list[Path] = []
    had_thumb_directory = False
    for entry in target.rglob("*"):
        if entry.is_symlink() or entry.is_file():
            raise ValueError("La carpeta o alguna de sus subcarpetas todavía contiene archivos.")
        if entry.is_dir():
            directories.append(entry)
            had_thumb_directory = had_thumb_directory or entry.name.casefold() == "thumb"

    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        directory.rmdir()
    target.rmdir()
    return had_thumb_directory


def _validate_thumbnail_only_source_folder(target: Path) -> int:
    """Permite una rama sin originales aunque conserve archivos dentro de carpetas thumb."""
    thumbnail_files = 0
    for entry in target.rglob("*"):
        if entry.is_symlink():
            raise ValueError("La carpeta contiene accesos simbólicos y no puede procesarse de forma segura.")
        if not entry.is_file():
            continue
        relative_parts = entry.relative_to(target).parts[:-1]
        if not any(part.casefold() == "thumb" for part in relative_parts):
            raise ValueError("La carpeta o alguna de sus subcarpetas todavía contiene archivos originales.")
        thumbnail_files += 1
    return thumbnail_files


def _next_available_trash_path(
    trash_path: Path,
    filename: str,
    reserved_names: set[str] | None = None,
) -> Path:
    """Genera nombre (1), nombre (2), etc. considerando disco y registros existentes."""
    reserved = {name.casefold() for name in (reserved_names or set())}
    source_name = Path(filename).name
    stem = Path(source_name).stem
    suffix = Path(source_name).suffix
    candidate = trash_path / source_name
    counter = 1
    while candidate.exists() or candidate.name.casefold() in reserved:
        candidate = trash_path / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def _delete_image_thumbnails(
    folder_root: Path,
    image_path: str,
    thumb_path: str | None,
) -> int:
    """Elimina miniaturas registradas o convencionales sin salir de la carpeta original."""
    root = folder_root.resolve()
    candidates: list[Path] = []
    if thumb_path:
        registered = Path(thumb_path)
        candidates.append(registered if registered.is_absolute() else root / registered)

    image_relative = Path(image_path)
    conventional_relative = (
        Path("thumb") / f"{image_relative.stem}.jpg"
        if str(image_relative.parent) in ("", ".")
        else image_relative.parent / "thumb" / f"{image_relative.stem}.jpg"
    )
    candidates.append(root / conventional_relative)

    deleted = 0
    visited: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        normalized = str(resolved).casefold()
        if normalized in visited or root not in resolved.parents:
            continue
        visited.add(normalized)
        if resolved.is_file():
            resolved.unlink()
            deleted += 1
    return deleted


class ScanFolderRequest(BaseModel):
    """Request model para escanear carpetas"""
    folder_id: str = Field(..., min_length=1, description="ID de la carpeta a escanear")
    recursive: bool = Field(True, description="Si debe escanear recursivamente")


class SourceFolderNodeMoveItem(BaseModel):
    folder_id: str = Field(..., min_length=1)
    node_id: int


class SourceFolderNodesMoveRequest(BaseModel):
    source_nodes: List[SourceFolderNodeMoveItem] = Field(..., min_length=1)
    destination_folder_id: str = Field(..., min_length=1)
    destination_node_id: int


class OrphanedImageInfo(BaseModel):
    """Información de una imagen huérfana o problemática"""
    id: int
    guid: str | None
    path: str
    folder_id: str
    thumb_path: str | None
    reason: str | None = None  # 'not_exists', 'not_file', 'cannot_read', 'error'
    error: str | None = None


class ScanFolderResponse(BaseModel):
    """Response model para resultado de escaneo"""
    folder_id: str
    folder_path: str
    total_files: int
    image_count: int
    created_count: int
    updated_count: int
    unchanged_count: int = 0
    errors: List[str]
    orphaned_images: List[OrphanedImageInfo] = []


class LinkedResourceInfo(BaseModel):
    """Información de un recurso vinculado (modelo o LoRA)"""
    resource_id: int
    nombre: str
    strength: float | None = None  # Solo para LoRAs
    strength_model: float | None = None  # Solo para LoRAs


class ImageResponse(BaseModel):
    """Response model para imágenes"""
    id: int
    guid: str | None  # GUID persistente de la imagen
    folder_id: str
    folder_node_id: int | None = None
    path: str
    thumb_path: str | None
    size: int
    width: int | None
    height: int | None
    prompt_json: dict | None
    workflow_json: dict | None
    created_at: datetime
    
    # Modelo / LoRAs inferidos desde prompt_json y workflow_json embebidos
    linked_model: LinkedResourceInfo | None = None
    linked_loras: List[LinkedResourceInfo] = []
    
    model_config = ConfigDict(from_attributes=True)


def _image_to_response(image: Image) -> ImageResponse:
    lm_raw, ll_raw = build_linked_payload(image.prompt_json, image.workflow_json)
    linked_model = LinkedResourceInfo(**lm_raw) if lm_raw else None
    linked_loras = [LinkedResourceInfo(**d) for d in ll_raw]
    return ImageResponse(
        id=image.id,
        guid=image.guid,
        folder_id=image.folder_id,
        folder_node_id=image.folder_node_id,
        path=image.path,
        thumb_path=image.thumb_path,
        size=image.size,
        width=image.width,
        height=image.height,
        prompt_json=image.prompt_json,
        workflow_json=image.workflow_json,
        created_at=image.created_at,
        linked_model=linked_model,
        linked_loras=linked_loras,
    )


_natural_chunk_re = re.compile(r"(\d+)")


def _natural_sort_key(value: str) -> tuple[tuple[int, object], ...]:
    """
    Crea una clave de orden natural:
    - números como enteros
    - texto en minúsculas
    """
    parts = _natural_chunk_re.split(value.lower())
    key: list[tuple[int, object]] = []
    for chunk in parts:
        if not chunk:
            continue
        if chunk.isdigit():
            key.append((0, int(chunk)))
        else:
            key.append((1, chunk))
    return tuple(key)


def _image_natural_order_key(image: Image) -> tuple[tuple[tuple[int, object], ...], tuple[tuple[int, object], ...], str]:
    """
    Orden natural por nombre de archivo (stem), luego por carpeta relativa y extensión.
    Así Marta_0001 queda antes que Marta_0038.
    """
    rel_raw = str(image.path or "")
    # Normalizar separadores para evitar desorden cuando hay mezcla "\" y "/".
    rel = rel_raw.replace("\\", "/")
    p = PurePosixPath(rel)
    parent = "" if str(p.parent) == "." else str(p.parent)
    stem = p.stem
    suffix = p.suffix.lower()
    return (_natural_sort_key(stem), _natural_sort_key(parent), suffix)


async def _build_effective_tags_map_for_folder(
    db: AsyncSession,
    folder_id: str,
) -> Dict[int, set[int]]:
    nodes_result = await db.execute(
        select(FolderNode)
        .where(FolderNode.folder_root_id == folder_id)
        .order_by(FolderNode.depth.asc())
    )
    nodes = nodes_result.scalars().all()
    if not nodes:
        return {}

    node_ids = [node.id for node in nodes]
    tags_result = await db.execute(
        select(folder_node_tags.c.folder_node_id, folder_node_tags.c.tag_id)
        .where(folder_node_tags.c.folder_node_id.in_(node_ids))
    )
    own_tags_map: Dict[int, set[int]] = {}
    for node_id, tag_id in tags_result.fetchall():
        own_tags_map.setdefault(node_id, set()).add(tag_id)

    nodes_by_id = {node.id: node for node in nodes}
    effective_map: Dict[int, set[int]] = {}
    for node in nodes:
        merged = set(own_tags_map.get(node.id, set()))
        parent_id = node.parent_node_id
        while parent_id is not None:
            merged.update(own_tags_map.get(parent_id, set()))
            parent_node = nodes_by_id.get(parent_id)
            if not parent_node:
                break
            parent_id = parent_node.parent_node_id
        effective_map[node.id] = merged
    return effective_map


class ImagesListResponse(BaseModel):
    """Response model para lista de imágenes con paginación"""
    images: List[ImageResponse]
    total: int


class DashboardNamedCountResponse(BaseModel):
    name: str
    display_name: str
    count: int
    percent: float
    filter: Dict[str, str] | None = None


class DashboardFolderCountResponse(BaseModel):
    folder_id: str
    folder_name: str
    display_name: str
    count: int
    percent: float
    filter: Dict[str, str] | None = None


class DashboardSummaryResponse(BaseModel):
    total_images: int
    total_folders: int
    total_subfolders: int
    total_active_tags: int


class DashboardAIUsageResponse(BaseModel):
    top_checkpoints: List[DashboardNamedCountResponse]
    top_loras: List[DashboardNamedCountResponse]
    missing_checkpoint_count: int
    missing_lora_count: int


class DashboardRootVsSubfolderResponse(BaseModel):
    root_images: int
    subfolder_images: int
    root_percent: float
    subfolder_percent: float


class DashboardDistributionResponse(BaseModel):
    images_by_folder: List[DashboardFolderCountResponse]
    images_by_folder_type: List[DashboardNamedCountResponse]
    root_vs_subfolder: DashboardRootVsSubfolderResponse


class DashboardMetricsResponse(BaseModel):
    summary: DashboardSummaryResponse
    ai_usage: DashboardAIUsageResponse
    distribution: DashboardDistributionResponse
    generated_at: datetime


class SyncMasterFoldersRequest(BaseModel):
    master_path: Optional[str] = None


class SyncMasterRootItemResponse(BaseModel):
    folder_id: str
    folder_name: str
    folder_path: str
    existed: bool
    created_count: int
    updated_count: int
    unchanged_count: int = 0
    image_count: int
    errors: int


class SyncMasterFoldersResponse(BaseModel):
    master_path: str
    roots_detected: int
    roots_created: int
    roots_existing: int
    scanned_roots: List[SyncMasterRootItemResponse]
    errors: List[str]


@router.get("/folders", response_model=List[FolderResponse])
async def list_folders(db: AsyncSession = Depends(get_db)):
    """
    Lista todas las carpetas registradas con conteo de imágenes
    """
    try:
        service = GalleryService(db)
        folders = await service.list_folders()
        
        # Optimizar: Obtener conteos de imágenes en una sola query usando group_by
        folder_ids = [folder.id for folder in folders]
        if folder_ids:
            count_query = select(
                Image.folder_id,
                func.count(Image.id).label('image_count')
            ).where(
                Image.folder_id.in_(folder_ids)
            ).group_by(Image.folder_id)
            count_result = await db.execute(count_query)
            counts_dict = {row[0]: row[1] for row in count_result.fetchall()}
        else:
            counts_dict = {}
        
        # Agregar conteo de imágenes para cada carpeta
        result = []
        for folder in folders:
            image_count = counts_dict.get(folder.id, 0)
            
            folder_dict = {
                "id": folder.id,
                "path": folder.path,
                "name": folder.name,
                "enabled": folder.enabled,
                "last_scan_at": folder.last_scan_at,
                "created_at": folder.created_at,
                "image_count": image_count
            }
            result.append(FolderResponse(**folder_dict))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener carpetas: {str(e)}")


@router.get("/dashboard/metrics", response_model=DashboardMetricsResponse)
async def get_dashboard_metrics(db: AsyncSession = Depends(get_db)):
    """Métricas globales de galería para el dashboard operativo."""
    try:
        service = GalleryService(db)
        metrics = await service.get_dashboard_metrics()
        ai_usage = metrics["ai_usage"]
        distribution = metrics["distribution"]
        return DashboardMetricsResponse(
            summary=DashboardSummaryResponse(**metrics["summary"]),
            ai_usage=DashboardAIUsageResponse(
                top_checkpoints=[DashboardNamedCountResponse(**item) for item in ai_usage["top_checkpoints"]],
                top_loras=[DashboardNamedCountResponse(**item) for item in ai_usage["top_loras"]],
                missing_checkpoint_count=ai_usage["missing_checkpoint_count"],
                missing_lora_count=ai_usage["missing_lora_count"],
            ),
            distribution=DashboardDistributionResponse(
                images_by_folder=[DashboardFolderCountResponse(**item) for item in distribution["images_by_folder"]],
                images_by_folder_type=[DashboardNamedCountResponse(**item) for item in distribution["images_by_folder_type"]],
                root_vs_subfolder=DashboardRootVsSubfolderResponse(**distribution["root_vs_subfolder"]),
            ),
            generated_at=datetime.utcnow(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener métricas de dashboard: {str(e)}",
        )


@router.get("/folders/{folder_id}/tree", response_model=FolderTreeResponse)
async def get_folder_tree(folder_id: str, db: AsyncSession = Depends(get_db)):
    try:
        folder_result = await db.execute(select(Folder).where(Folder.id == folder_id))
        folder = folder_result.scalar_one_or_none()
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta con ID {folder_id} no encontrada",
            )

        service = GalleryService(db)
        nodes_payload = await service.get_folder_tree(folder_id)
        return FolderTreeResponse(folder_id=folder_id, nodes=nodes_payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener árbol de carpetas: {str(e)}",
        )


@router.patch("/folders/{folder_id}/nodes/{node_id}/nomenclature", response_model=FolderNodeTreeResponse)
async def update_folder_node_nomenclature(
    folder_id: str,
    node_id: int,
    body: FolderNodeNomenclatureUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = GalleryService(db)
        node = await service.set_folder_node_nomenclature(
            folder_id=folder_id,
            node_id=node_id,
            naming_base=body.naming_base,
            naming_number_width=body.naming_number_width,
        )
        tree = await service.get_folder_tree(folder_id)

        def find_payload(nodes: List[Dict[str, Any]], target: int) -> Optional[Dict[str, Any]]:
            for n in nodes:
                if n["id"] == target:
                    return n
                inner = find_payload(n.get("children", []), target)
                if inner:
                    return inner
            return None

        def to_response(payload: Dict[str, Any]) -> FolderNodeTreeResponse:
            return FolderNodeTreeResponse(
                id=payload["id"],
                folder_root_id=payload["folder_root_id"],
                parent_node_id=payload.get("parent_node_id"),
                rel_path=payload["rel_path"],
                name=payload["name"],
                depth=payload["depth"],
                naming_base=payload.get("naming_base"),
                naming_number_width=payload.get("naming_number_width"),
                tag_ids=payload.get("tag_ids", []),
                tags=[FolderTagResponse(**t) for t in payload.get("tags", [])],
                effective_tag_ids=payload.get("effective_tag_ids", []),
                effective_tags=[FolderTagResponse(**t) for t in payload.get("effective_tags", [])],
                children=[to_response(c) for c in payload.get("children", [])],
            )

        found = find_payload(tree, node.id)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Nodo actualizado pero no encontrado en el árbol.",
            )
        return to_response(found)
    except ValueError as err:
        code = str(err)
        if code == "folder_node_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nodo de carpeta no encontrado.") from err
        if code == "nomenclature_invalid":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="naming_base y naming_number_width deben enviarse juntos (o ambos null para borrar).",
            ) from err
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from err
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar nomenclatura: {str(e)}",
        )


@router.post(
    "/folders/{folder_id}/nodes/{node_id}/rename/preview",
    response_model=FolderNodeRenamePreviewResponse,
)
async def preview_folder_node_rename(
    folder_id: str,
    node_id: int,
    body: FolderNodeRenameRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        if body.mode == "selected" and not body.image_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="image_ids es obligatorio cuando mode=selected.",
            )
        service = GalleryService(db)
        data = await service.preview_rename_folder_node(
            folder_id=folder_id,
            node_id=node_id,
            mode=body.mode,
            selected_ids=body.image_ids,
        )
        entries = [
            FolderNodeRenamePreviewEntry(
                image_id=e["image_id"],
                old_path=e["old_path"],
                new_path=e.get("new_path"),
                reason=e["reason"],
                name_class=e.get("name_class"),
            )
            for e in data["entries"]
        ]
        return FolderNodeRenamePreviewResponse(
            folder_id=data["folder_id"],
            folder_node_id=data["folder_node_id"],
            next_counter_start=data["next_counter_start"],
            related_count=data["related_count"],
            unrelated_count=data["unrelated_count"],
            unchanged_count=data["unchanged_count"],
            entries=entries,
        )
    except ValueError as err:
        code = str(err)
        if code == "folder_node_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nodo de carpeta no encontrado.") from err
        if code == "nomenclature_not_configured":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configura primero la nomenclatura de esta carpeta.",
            ) from err
        if code.startswith("unsupported_extension"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from err
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from err
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar vista previa: {str(e)}",
        )


@router.post(
    "/folders/{folder_id}/nodes/{node_id}/rename/apply",
    response_model=FolderNodeRenameApplyResponse,
)
async def apply_folder_node_rename(
    folder_id: str,
    node_id: int,
    body: FolderNodeRenameRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        if body.mode == "selected" and not body.image_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="image_ids es obligatorio cuando mode=selected.",
            )
        service = GalleryService(db)
        data = await service.apply_rename_folder_node(
            folder_id=folder_id,
            node_id=node_id,
            mode=body.mode,
            selected_ids=body.image_ids,
        )
        return FolderNodeRenameApplyResponse(**data)
    except ValueError as err:
        code = str(err)
        if code == "folder_node_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nodo de carpeta no encontrado.") from err
        if code == "folder_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada.") from err
        if code == "nomenclature_not_configured":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configura primero la nomenclatura de esta carpeta.",
            ) from err
        if code == "path_drift":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Los archivos cambiaron desde la vista previa. Vuelve a previsualizar.",
            ) from err
        if code.startswith("missing_file") or code.startswith("target_exists") or code.startswith("thumb_target"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from err
        if code == "path_escape":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ruta inválida.") from err
        if code.startswith("unsupported_extension"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from err
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from err
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al aplicar renombrado: {str(e)}",
        )


@router.get("/tags", response_model=List[FolderTagResponse])
async def list_gallery_tags(db: AsyncSession = Depends(get_db)):
    try:
        service = GalleryService(db)
        tags = await service.list_folder_tags()
        return [FolderTagResponse.model_validate(tag) for tag in tags]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar tags: {str(e)}",
        )


@router.patch("/folder-nodes/{node_id}/tags", response_model=List[FolderTagResponse])
async def update_folder_node_tags(
    node_id: int,
    request: UpdateFolderNodeTagsRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        if request.tag_ids is None and request.tags is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes enviar tag_ids o tags para actualizar.",
            )

        service = GalleryService(db)
        tags = await service.set_folder_node_tags(
            node_id=node_id,
            tag_ids=request.tag_ids or [],
            tag_names=request.tags or [],
        )
        return [FolderTagResponse.model_validate(tag) for tag in tags]
    except ValueError as err:
        if str(err) == "folder_node_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nodo de carpeta {node_id} no encontrado.",
            ) from err
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar tags del nodo: {str(e)}",
        )


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(folder_data: FolderCreate, db: AsyncSession = Depends(get_db)):
    """
    Crea una nueva carpeta manualmente
    """
    try:
        service = GalleryService(db)
        folder = await service.create_folder(
            path=folder_data.path,
            name=folder_data.name,
            enabled=folder_data.enabled
        )
        return folder
    except ValueError as e:
        # Errores de validación (path duplicado, parámetros inválidos)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear carpeta: {str(e)}"
        )


@router.post("/folders/sync-master", response_model=SyncMasterFoldersResponse)
async def sync_master_folders(body: SyncMasterFoldersRequest, db: AsyncSession = Depends(get_db)):
    """
    Sincroniza de forma masiva roots desde la carpeta maestra IMG.
    Solo registra novedades (carpetas/subcarpetas/imágenes nuevas) y evita duplicados.
    """
    try:
        master_path = body.master_path
        if not master_path:
            setting_result = await db.execute(
                select(Setting).where(Setting.key == SettingKeys.IMG_MASTER_PATH)
            )
            setting = setting_result.scalar_one_or_none()
            master_path = setting.value if setting else None

        if not master_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay ruta maestra configurada. Define img_master_path en Configuración.",
            )

        service = GalleryService(db)
        result = await service.sync_master_folder(master_path)
        return SyncMasterFoldersResponse(
            master_path=result["master_path"],
            roots_detected=result["roots_detected"],
            roots_created=result["roots_created"],
            roots_existing=result["roots_existing"],
            scanned_roots=[SyncMasterRootItemResponse(**item) for item in result["scanned_roots"]],
            errors=result["errors"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en sincronización masiva: {str(e)}",
        )


@router.post("/folders/master-naming/preview", response_model=MasterNamingResponse)
async def preview_master_missing_names(db: AsyncSession = Depends(get_db)):
    """Revisa la ruta maestra y conserva los archivos que ya usan carpeta_correlativo."""
    try:
        return await GalleryService(db).preview_master_missing_names()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error al revisar nomenclatura de la ruta maestra")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al revisar nomenclatura: {str(exc)}",
        ) from exc


@router.post("/folders/master-naming/apply", response_model=MasterNamingResponse)
async def apply_master_missing_names(db: AsyncSession = Depends(get_db)):
    """Renombra exclusivamente las imágenes fuera de la nomenclatura de su carpeta."""
    try:
        return await GalleryService(db).apply_master_missing_names()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error al corregir nomenclatura de la ruta maestra")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al corregir nomenclatura: {str(exc)}",
        ) from exc


class FolderToggleRequest(BaseModel):
    """Request model para toggle de enabled"""
    enabled: bool


@router.patch("/folders/{folder_id}/toggle", response_model=FolderResponse)
async def toggle_folder(folder_id: str, toggle_data: FolderToggleRequest, db: AsyncSession = Depends(get_db)):
    """
    Activa o desactiva una carpeta
    """
    try:
        # Buscar la carpeta
        result = await db.execute(select(Folder).where(Folder.id == folder_id))
        folder = result.scalar_one_or_none()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta con ID {folder_id} no encontrada"
            )
        
        # Actualizar el estado
        folder.enabled = toggle_data.enabled
        await db.commit()
        await db.refresh(folder)
        
        # Obtener conteo de imágenes
        count_query = select(func.count(Image.id)).where(Image.folder_id == folder.id)
        count_result = await db.execute(count_query)
        image_count = count_result.scalar() or 0
        
        return FolderResponse(
            id=folder.id,
            path=folder.path,
            name=folder.name,
            enabled=folder.enabled,
            last_scan_at=folder.last_scan_at,
            created_at=folder.created_at,
            image_count=image_count
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al cambiar estado de carpeta: {str(e)}"
        )


@router.delete("/folders/{folder_id}", status_code=status.HTTP_200_OK)
async def delete_folder(folder_id: str, db: AsyncSession = Depends(get_db)):
    """
    Elimina del registro (BD) una carpeta y todas sus imágenes asociadas.
    No elimina archivos físicos del disco.
    """
    try:
        # Verificar que la carpeta existe
        result = await db.execute(select(Folder).where(Folder.id == folder_id))
        folder = result.scalar_one_or_none()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta con ID {folder_id} no encontrada"
            )
        
        # Eliminar imágenes asociadas primero (por CASCADE debería ser automático, pero lo hacemos explícito)
        await db.execute(delete(Image).where(Image.folder_id == folder_id))
        
        # Eliminar la carpeta
        await db.delete(folder)
        await db.commit()
        
        return {"message": f"Carpeta '{folder.name}' y sus imágenes eliminadas correctamente", "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar carpeta: {str(e)}"
        )


@router.delete("/folders/{folder_id}/nodes/{node_id}", status_code=status.HTTP_200_OK)
async def delete_folder_node_registration(
    folder_id: str,
    node_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Elimina del registro (BD) una subcarpeta lógica (nodo) y su subárbol.
    No elimina archivos físicos del disco.
    """
    try:
        service = GalleryService(db)
        node = await service.get_folder_node_in_root(folder_id, node_id)
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nodo {node_id} no encontrado para folder {folder_id}.",
            )

        if node.rel_path == "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nodo raíz no puede eliminarse por este endpoint. Usa DELETE /folders/{folder_id}.",
            )

        node_rows = await db.execute(
            select(FolderNode.id, FolderNode.parent_node_id).where(FolderNode.folder_root_id == folder_id)
        )
        rows = node_rows.fetchall()
        children_by_parent: Dict[int, List[int]] = {}
        for row in rows:
            parent_id = row.parent_node_id
            if parent_id is None:
                continue
            children_by_parent.setdefault(int(parent_id), []).append(int(row.id))

        subtree_ids: List[int] = []
        stack: List[int] = [int(node_id)]
        while stack:
            current = stack.pop()
            subtree_ids.append(current)
            stack.extend(children_by_parent.get(current, []))

        if not subtree_ids:
            subtree_ids = [int(node_id)]

        delete_images_result = await db.execute(
            delete(Image).where(
                Image.folder_id == folder_id,
                Image.folder_node_id.in_(subtree_ids),
            )
        )
        delete_nodes_result = await db.execute(
            delete(FolderNode).where(
                FolderNode.folder_root_id == folder_id,
                FolderNode.id.in_(subtree_ids),
            )
        )
        await db.commit()

        deleted_images = int(delete_images_result.rowcount or 0)
        deleted_nodes = int(delete_nodes_result.rowcount or 0)
        return {
            "message": (
                f"Subcarpeta '{node.name}' eliminada del registro junto con {deleted_nodes} nodo(s) "
                f"y {deleted_images} imagen(es) en BD."
            ),
            "deleted": True,
            "deleted_nodes": deleted_nodes,
            "deleted_images": deleted_images,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar subcarpeta del registro: {str(e)}",
        )


@router.delete("/folders/{folder_id}/nodes/{node_id}/delete-empty", status_code=status.HTTP_200_OK)
async def delete_empty_source_folder(
    folder_id: str,
    node_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mueve a papelera una rama sin originales, aunque conserve miniaturas."""
    target: Path | None = None
    trash_destination: Path | None = None
    try:
        folder_result = await db.execute(select(Folder).where(Folder.id == folder_id))
        folder = folder_result.scalar_one_or_none()
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta original no encontrada.")

        service = GalleryService(db)
        node = await service.get_folder_node_in_root(folder_id, node_id)
        if not node:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcarpeta no encontrada.")
        node_name = str(node.name)
        nodes_result = await db.execute(
            select(FolderNode.id, FolderNode.rel_path).where(FolderNode.folder_root_id == folder_id)
        )
        node_rel = str(node.rel_path).replace("\\", "/").rstrip("/")
        is_root_node = not node_rel
        subtree_ids = [
            int(row.id)
            for row in nodes_result.fetchall()
            if is_root_node
            or str(row.rel_path).replace("\\", "/") == node_rel
            or str(row.rel_path).replace("\\", "/").startswith(f"{node_rel}/")
        ]
        root = Path(folder.path).resolve()
        target = root if is_root_node else (root / Path(node.rel_path)).resolve()
        if not is_root_node and root not in target.parents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ruta de subcarpeta no válida.")
        if not target.exists():
            # La ruta ya fue borrada o movida fuera de la aplicación. Limpiar el
            # registro huérfano permite que desaparezca del árbol sin exigir disco.
            image_delete_filter = Image.folder_id == folder_id
            if not is_root_node:
                image_delete_filter = image_delete_filter & Image.folder_node_id.in_(subtree_ids)
            delete_images_result = await db.execute(delete(Image).where(image_delete_filter))
            await db.execute(
                delete(FolderNode).where(
                    FolderNode.folder_root_id == folder_id,
                    FolderNode.id.in_(subtree_ids),
                )
            )
            if is_root_node:
                await db.execute(delete(Folder).where(Folder.id == folder_id))
            await db.commit()
            return {
                "message": f"Registro huérfano '{node_name}' eliminado; la carpeta ya no existía en el disco.",
                "deleted": True,
                "node_id": node_id,
                "trash_path": None,
                "deleted_image_records": int(delete_images_result.rowcount or 0),
                "missing_on_disk": True,
            }
        if not target.is_dir():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La ruta seleccionada no es una carpeta.")

        try:
            thumbnail_count = await asyncio.to_thread(_validate_thumbnail_only_source_folder, target)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

        trash_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.TRASH_PATH)
        )
        trash_setting = trash_result.scalar_one_or_none()
        if not trash_setting or not trash_setting.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ruta de papelera no configurada. Configúrala en Settings.",
            )
        trash_path = Path(trash_setting.value).resolve()
        await asyncio.to_thread(trash_path.mkdir, parents=True, exist_ok=True)
        trash_destination = _next_available_trash_path(trash_path, target.name)
        try:
            await asyncio.to_thread(shutil.move, str(target), str(trash_destination))
        except OSError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La carpeta está siendo utilizada o no pudo moverse a la papelera.",
            )

        image_delete_filter = Image.folder_id == folder_id
        if not is_root_node:
            image_delete_filter = (
                image_delete_filter
                & Image.folder_node_id.in_(subtree_ids)
            )
        delete_images_result = await db.execute(delete(Image).where(image_delete_filter))
        await db.execute(
            delete(FolderNode).where(
                FolderNode.folder_root_id == folder_id,
                FolderNode.id.in_(subtree_ids),
            )
        )
        if is_root_node:
            await db.execute(delete(Folder).where(Folder.id == folder_id))
        await db.commit()
        deleted_records = int(delete_images_result.rowcount or 0)
        return {
            "message": (
                f"Carpeta '{node_name}' movida a la papelera"
                f" con {thumbnail_count} miniatura{'s' if thumbnail_count != 1 else ''}."
            ),
            "deleted": True,
            "node_id": node_id,
            "trash_path": str(trash_destination),
            "deleted_image_records": deleted_records,
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        if (
            target is not None
            and trash_destination is not None
            and trash_destination.exists()
            and not target.exists()
        ):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(trash_destination), str(target))
            except OSError:
                logger.error("empty_source_folder_rollback_failed", exc_info=True)
        logger.error("empty_source_folder_delete_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo mover la carpeta a la papelera: {exc}",
        )


@router.post("/folders/nodes/move", status_code=status.HTTP_200_OK)
async def move_source_folder_nodes(
    request: SourceFolderNodesMoveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Corta una o más subcarpetas originales y las pega dentro de otra carpeta original."""
    destination_folder_result = await db.execute(
        select(Folder).where(Folder.id == request.destination_folder_id)
    )
    destination_folder = destination_folder_result.scalar_one_or_none()
    if not destination_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta destino no encontrada.")

    destination_node_result = await db.execute(
        select(FolderNode).where(
            FolderNode.id == request.destination_node_id,
            FolderNode.folder_root_id == request.destination_folder_id,
        )
    )
    destination_node = destination_node_result.scalar_one_or_none()
    if not destination_node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcarpeta destino no encontrada.")

    destination_root = Path(destination_folder.path).resolve()
    destination_rel = str(destination_node.rel_path).replace("\\", "/").strip("/")
    destination_directory = (
        destination_root
        if not destination_rel
        else (destination_root / Path(destination_rel)).resolve()
    )
    if not destination_directory.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La carpeta destino no existe en el disco.")

    requested_keys: set[tuple[str, int]] = set()
    raw_plans: list[dict[str, Any]] = []
    folders_cache: dict[str, Folder] = {destination_folder.id: destination_folder}
    for item in request.source_nodes:
        key = (item.folder_id, int(item.node_id))
        if key in requested_keys:
            continue
        requested_keys.add(key)

        source_folder = folders_cache.get(item.folder_id)
        if source_folder is None:
            folder_result = await db.execute(select(Folder).where(Folder.id == item.folder_id))
            source_folder = folder_result.scalar_one_or_none()
            if not source_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Una carpeta de origen no existe.")
            folders_cache[item.folder_id] = source_folder

        node_result = await db.execute(
            select(FolderNode).where(
                FolderNode.id == item.node_id,
                FolderNode.folder_root_id == item.folder_id,
            )
        )
        source_node = node_result.scalar_one_or_none()
        if not source_node:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Una subcarpeta de origen no existe.")
        source_rel = str(source_node.rel_path).replace("\\", "/").strip("/")
        if not source_rel:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Las carpetas raíz registradas no pueden moverse desde esta opción.",
            )
        source_root = Path(source_folder.path).resolve()
        source_directory = (source_root / Path(source_rel)).resolve()
        if source_root not in source_directory.parents or not source_directory.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La carpeta '{source_node.name}' no existe en el disco.",
            )
        raw_plans.append(
            {
                "folder": source_folder,
                "node": source_node,
                "old_rel": source_rel,
                "source": source_directory,
            }
        )

    raw_plans.sort(key=lambda plan: (len(PurePosixPath(plan["old_rel"]).parts), plan["old_rel"].casefold()))
    plans: list[dict[str, Any]] = []
    for plan in raw_plans:
        if any(
            existing["folder"].id == plan["folder"].id
            and plan["old_rel"].startswith(f"{existing['old_rel']}/")
            for existing in plans
        ):
            continue
        plans.append(plan)

    target_names: set[str] = set()
    for plan in plans:
        source = plan["source"]
        if destination_directory == source or source in destination_directory.parents:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No puedes mover '{source.name}' dentro de sí misma o de una subcarpeta suya.",
            )
        target = destination_directory / source.name
        if target == source:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La carpeta '{source.name}' ya está dentro del destino seleccionado.",
            )
        name_key = source.name.casefold()
        if target.exists() or name_key in target_names:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El destino ya contiene una carpeta llamada '{source.name}'.",
            )
        target_names.add(name_key)
        new_rel = (
            f"{destination_rel}/{source.name}"
            if destination_rel
            else source.name
        )
        plan["target"] = target
        plan["new_rel"] = new_rel
        plan["depth_delta"] = destination_node.depth + 1 - plan["node"].depth

    source_folder_ids = list({plan["folder"].id for plan in plans})
    nodes_result = await db.execute(
        select(FolderNode).where(FolderNode.folder_root_id.in_(source_folder_ids))
    )
    all_source_nodes = nodes_result.scalars().all()
    affected_nodes = []
    for node in all_source_nodes:
        node_rel = str(node.rel_path).replace("\\", "/").strip("/")
        for plan in plans:
            if node.folder_root_id != plan["folder"].id:
                continue
            old_rel = plan["old_rel"]
            old_prefix = f"{old_rel}/"
            if node_rel == old_rel:
                node.folder_root_id = destination_folder.id
                node.parent_node_id = destination_node.id
                node.rel_path = plan["new_rel"]
                node.depth += int(plan["depth_delta"])
                affected_nodes.append(node)
                break
            if node_rel.startswith(old_prefix):
                node.folder_root_id = destination_folder.id
                node.rel_path = f"{plan['new_rel']}/{node_rel[len(old_prefix):]}"
                node.depth += int(plan["depth_delta"])
                affected_nodes.append(node)
                break

    images_result = await db.execute(
        select(Image).where(Image.folder_id.in_(source_folder_ids))
    )
    affected_images = []
    for image in images_result.scalars().all():
        image_path = str(image.path).replace("\\", "/")
        thumb_path = str(image.thumb_path).replace("\\", "/") if image.thumb_path else None
        for plan in plans:
            if image.folder_id != plan["folder"].id:
                continue
            old_prefix = f"{plan['old_rel']}/"
            if not image_path.startswith(old_prefix):
                continue
            new_prefix = f"{plan['new_rel']}/"
            image.folder_id = destination_folder.id
            image.path = new_prefix + image_path[len(old_prefix):]
            if thumb_path and thumb_path.startswith(old_prefix):
                image.thumb_path = new_prefix + thumb_path[len(old_prefix):]
            affected_images.append(image)
            break

    completed_plans: list[dict[str, Any]] = []
    try:
        for plan in plans:
            await asyncio.to_thread(shutil.move, str(plan["source"]), str(plan["target"]))
            completed_plans.append(plan)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        for plan in reversed(completed_plans):
            try:
                if plan["target"].exists() and not plan["source"].exists():
                    plan["source"].parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(plan["target"]), str(plan["source"]))
            except OSError:
                logger.error("source_folder_move_rollback_failed", exc_info=True)
        logger.error("source_folder_move_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudieron mover las carpetas; se revirtieron los cambios: {exc}",
        )

    moved_count = len(plans)
    return {
        "message": f"{moved_count} carpeta{'s' if moved_count != 1 else ''} movida{'s' if moved_count != 1 else ''}.",
        "moved_count": moved_count,
        "updated_database_images": len(affected_images),
        "updated_database_nodes": len(affected_nodes),
        "destination_folder_id": destination_folder.id,
        "destination_node_id": destination_node.id,
    }


@router.post("/folders/scan", response_model=ScanFolderResponse, status_code=status.HTTP_200_OK)
async def scan_folder(scan_data: ScanFolderRequest, db: AsyncSession = Depends(get_db)):
    """
    Escanea una carpeta y crea/actualiza registros de imágenes en la BD
    """
    logger.info(f"[ROUTER] ===== INICIANDO ESCANEO DE CARPETA =====")
    logger.info(f"[ROUTER] folder_id={scan_data.folder_id}, recursive={scan_data.recursive}")
    try:
        service = GalleryService(db)
        logger.info(f"[ROUTER] GalleryService creado, llamando a scan_folder con create_records=True")
        result = await service.scan_folder(
            folder_id=scan_data.folder_id,
            recursive=scan_data.recursive,
            create_records=True
        )
        logger.info(f"[ROUTER] ===== ESCANEO COMPLETADO =====")
        logger.info(f"[ROUTER] Resultado: {result['image_count']} imágenes encontradas, {result['created_count']} creadas, {result['updated_count']} actualizadas, {len(result['errors'])} errores, {len(result.get('orphaned_images', []))} imágenes huérfanas")
        # Convertir dict a ScanFolderResponse
        orphaned_images = result.get('orphaned_images', [])
        return ScanFolderResponse(
            folder_id=result['folder_id'],
            folder_path=result['folder_path'],
            total_files=result['total_files'],
            image_count=result['image_count'],
            created_count=result['created_count'],
            updated_count=result['updated_count'],
            unchanged_count=result.get('unchanged_count', 0),
            errors=result['errors'],
            orphaned_images=[OrphanedImageInfo(**img) for img in orphaned_images]
        )
    except ValueError as e:
        # Errores de validación (carpeta no existe, no habilitada, etc.)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al escanear carpeta: {str(e)}"
        )


class CleanupOrphanedImagesRequest(BaseModel):
    """Request model para limpiar imágenes huérfanas"""
    folder_id: str = Field(..., min_length=1, description="ID de la carpeta")
    image_ids: List[int] = Field(..., description="Lista de IDs de imágenes a eliminar")


class CleanupOrphanedImagesResponse(BaseModel):
    """Response model para resultado de limpieza"""
    deleted_count: int
    moved_to_trash_count: int = 0
    errors: List[str]


@router.post("/folders/{folder_id}/cleanup-orphaned", response_model=CleanupOrphanedImagesResponse, status_code=status.HTTP_200_OK)
async def cleanup_orphaned_images(
    folder_id: str,
    request: CleanupOrphanedImagesRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Elimina imágenes huérfanas de la base de datos
    """
    try:
        # Verificar que el folder_id coincide
        if request.folder_id != folder_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El folder_id en la URL no coincide con el del body"
            )
        
        service = GalleryService(db)
        result = await service.cleanup_orphaned_images(
            folder_id=folder_id,
            image_ids=request.image_ids
        )
        
        return CleanupOrphanedImagesResponse(
            deleted_count=result['deleted_count'],
            errors=result['errors']
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al limpiar imágenes huérfanas: {str(e)}"
        )


@router.get("/debug/check-folder/{folder_id}/thumbnails")
async def debug_check_folder_thumbnails(folder_id: str, db: AsyncSession = Depends(get_db)):
    """
    Endpoint de debug para verificar thumbnails faltantes
    """
    try:
        from pathlib import Path
        
        # Obtener la carpeta
        folder_result = await db.execute(select(Folder).where(Folder.id == folder_id))
        folder = folder_result.scalar_one_or_none()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta con ID {folder_id} no encontrada"
            )
        
        folder_path = Path(folder.path)
        
        # Obtener todas las imágenes de esta carpeta desde la DB
        result = await db.execute(select(Image).where(Image.folder_id == folder_id))
        db_images = result.scalars().all()
        
        missing_thumbnails = []
        existing_thumbnails = []
        
        for image in db_images:
            # Verificar imagen original
            image_path = folder_path / image.path
            image_exists = image_path.exists() and image_path.is_file()
            
            # Verificar thumbnail
            if image.thumb_path:
                thumb_path = folder_path / image.thumb_path
                thumb_exists = thumb_path.exists() and thumb_path.is_file()
            else:
                thumb_exists = False
                thumb_path = None
            
            if image_exists and not thumb_exists:
                missing_thumbnails.append({
                    'id': image.id,
                    'guid': image.guid,
                    'image_path': str(image_path),
                    'thumb_path': str(thumb_path) if thumb_path else None,
                    'thumb_path_in_db': image.thumb_path
                })
            elif thumb_exists:
                existing_thumbnails.append({
                    'id': image.id,
                    'path': image.path
                })
        
        return {
            "folder_id": folder_id,
            "folder_path": str(folder_path),
            "total_images_in_db": len(db_images),
            "missing_thumbnails": len(missing_thumbnails),
            "existing_thumbnails": len(existing_thumbnails),
            "missing_thumbnails_list": missing_thumbnails[:20],  # Primeras 20
            "sample_existing": existing_thumbnails[:5]  # Muestra de las que sí tienen
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en debug_check_folder_thumbnails: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


@router.get("/debug/check-folder/{folder_id}/orphaned")
async def debug_check_folder_orphaned(folder_id: str, db: AsyncSession = Depends(get_db)):
    """
    Endpoint de debug para verificar TODAS las imágenes huérfanas de una carpeta
    """
    try:
        from pathlib import Path
        
        # Obtener la carpeta
        folder_result = await db.execute(select(Folder).where(Folder.id == folder_id))
        folder = folder_result.scalar_one_or_none()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta con ID {folder_id} no encontrada"
            )
        
        folder_path = Path(folder.path)
        
        # Obtener todas las imágenes de esta carpeta desde la DB
        result = await db.execute(select(Image).where(Image.folder_id == folder_id))
        db_images = result.scalars().all()
        
        orphaned = []
        existing = []
        
        for image in db_images:
            physical_path = folder_path / image.path
            exists = physical_path.exists() and physical_path.is_file()
            
            if not exists:
                orphaned.append({
                    'id': image.id,
                    'guid': image.guid,
                    'path': image.path,
                    'full_path': str(physical_path)
                })
            else:
                existing.append({
                    'id': image.id,
                    'guid': image.guid,
                    'path': image.path
                })
        
        return {
            "folder_id": folder_id,
            "folder_path": str(folder_path),
            "total_images_in_db": len(db_images),
            "existing_images": len(existing),
            "orphaned_images": len(orphaned),
            "orphaned_list": orphaned,
            "existing_list": existing[:10]  # Solo las primeras 10 para no saturar
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en debug_check_folder_orphaned: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


@router.get("/debug/check-guid/{guid}")
async def debug_check_guid(guid: str, db: AsyncSession = Depends(get_db)):
    """
    Endpoint de debug para verificar una imagen por GUID
    """
    try:
        # Buscar la imagen en la DB
        result = await db.execute(select(Image).where(Image.guid == guid))
        image = result.scalar_one_or_none()
        
        if not image:
            return {
                "found_in_db": False,
                "message": f"No se encontró ninguna imagen con GUID {guid} en la base de datos"
            }
        
        # Obtener la carpeta
        folder_result = await db.execute(select(Folder).where(Folder.id == image.folder_id))
        folder = folder_result.scalar_one_or_none()
        
        if not folder:
            return {
                "found_in_db": True,
                "image_id": image.id,
                "guid": image.guid,
                "path": image.path,
                "folder_id": image.folder_id,
                "error": "No se encontró la carpeta asociada"
            }
        
        # Construir la ruta física completa
        from pathlib import Path
        folder_path = Path(folder.path)
        physical_path = folder_path / image.path
        
        # Verificar si existe físicamente
        exists_physically = physical_path.exists() and physical_path.is_file()
        
        return {
            "found_in_db": True,
            "image_id": image.id,
            "guid": image.guid,
            "path": image.path,
            "folder_id": image.folder_id,
            "folder_path": str(folder_path),
            "full_physical_path": str(physical_path),
            "exists_physically": exists_physically,
            "is_orphaned": not exists_physically
        }
        
    except Exception as e:
        logger.error(f"Error en debug_check_guid: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


class ImagesListResponse(BaseModel):
    """Response model para lista de imágenes con paginación"""
    images: List[ImageResponse]
    total: int


@router.get("/images", response_model=ImagesListResponse)
async def list_images(
    folder_id: Optional[str] = None,
    folder_node_id: Optional[int] = None,
    include_descendants: bool = False,
    include_disabled: bool = False,
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    missing_checkpoint: bool = False,
    missing_lora: bool = False,
    checkpoint_name: Optional[str] = None,
    lora_name: Optional[str] = None,
    folder_type: Optional[str] = None,
    include_tag_ids: Optional[List[int]] = Query(default=None),
    exclude_tag_ids: Optional[List[int]] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista imágenes con filtros opcionales
    
    Query Parameters:
        folder_id: Filtrar por ID de carpeta raíz (opcional)
        folder_node_id: Filtrar por nodo exacto de carpeta (opcional)
        include_descendants: Incluir imágenes de subcarpetas del nodo seleccionado
        include_disabled: Incluir imágenes de carpetas desactivadas (default: False)
        limit: Límite de resultados (default: 100, max: 1000)
        offset: Offset para paginación (default: 0)
        search: Buscar por nombre de modelo o LoRA en los metadatos (opcional)
        missing_checkpoint: Filtrar imágenes sin checkpoint detectado
        missing_lora: Filtrar imágenes sin LoRA detectada
        checkpoint_name: Filtrar por checkpoint exacto
        lora_name: Filtrar por LoRA exacta
        folder_type: Filtrar por tipo de carpeta (Safe, NoSafe, FaceDetail, Upscale, Otros)
        include_tag_ids: Tag IDs requeridos (tags efectivos heredados)
        exclude_tag_ids: Tag IDs a excluir (tags efectivos heredados)
    """
    try:
        # Validar límite
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 1
        
        # Validar offset
        if offset < 0:
            offset = 0

        # Validaciones de nodo de carpeta
        node_folder_id = None
        selected_node_depth = None
        if folder_node_id is not None:
            node_result = await db.execute(
                select(FolderNode).where(FolderNode.id == folder_node_id)
            )
            node = node_result.scalar_one_or_none()
            if not node:
                # La carpeta pudo moverse o eliminarse mientras esta vista aún
                # conservaba la selección anterior. Tratarla como una lista vacía.
                return ImagesListResponse(images=[], total=0)
            node_folder_id = node.folder_root_id
            if folder_id and folder_id != node_folder_id:
                return ImagesListResponse(images=[], total=0)
            if folder_id is None:
                folder_id = node_folder_id
            selected_node_depth = node.depth
        
        # Obtener IDs de carpetas habilitadas si no incluimos desactivadas
        enabled_folder_ids = None
        if not include_disabled:
            enabled_query = select(Folder.id).where(Folder.enabled == True)
            enabled_result = await db.execute(enabled_query)
            enabled_folder_ids = [row[0] for row in enabled_result.fetchall()]
        
        # Construir query de imágenes
        # Ordenar por nombre de archivo (path) de forma ascendente
        query = select(Image).order_by(Image.path.asc())
        
        # Filtrar por carpetas habilitadas
        if enabled_folder_ids is not None:
            if folder_id:
                # Si se especifica folder_id, verificar que esté habilitada
                if folder_id not in enabled_folder_ids:
                    return ImagesListResponse(images=[], total=0)
                query = query.where(Image.folder_id == folder_id)
            else:
                # Filtrar solo por carpetas habilitadas
                query = query.where(Image.folder_id.in_(enabled_folder_ids))
        elif folder_id:
            query = query.where(Image.folder_id == folder_id)

        # Filtrar por nodo:
        # - nodo raíz (depth=0): incluir toda la jerarquía de esa carpeta raíz
        # - subnodo (depth>0): solo nodo exacto
        if folder_node_id is not None:
            if selected_node_depth and selected_node_depth > 0:
                if include_descendants:
                    selected_rel = str(node.rel_path).replace("\\", "/").strip("/")
                    descendants_result = await db.execute(
                        select(FolderNode.id, FolderNode.rel_path).where(
                            FolderNode.folder_root_id == node_folder_id
                        )
                    )
                    descendant_ids = [
                        int(row.id)
                        for row in descendants_result.fetchall()
                        if int(row.id) == folder_node_id
                        or str(row.rel_path).replace("\\", "/").strip("/").startswith(f"{selected_rel}/")
                    ]
                    query = query.where(Image.folder_node_id.in_(descendant_ids))
                else:
                    query = query.where(Image.folder_node_id == folder_node_id)
        
        # Obtener todas las imágenes que coincidan con los filtros básicos
        # (necesitamos todas para filtrar por búsqueda en JSON)
        result = await db.execute(query)
        all_images = result.scalars().all()
        
        # Filtrar por búsqueda si se proporciona
        if search and search.strip():
            search_term = search.lower().strip()
            filtered_images = []
            
            def matches_search(image: Image) -> bool:
                """Verifica si una imagen coincide con el término de búsqueda"""
                # Buscar en prompt_json
                if image.prompt_json and isinstance(image.prompt_json, dict):
                    for node_id, node in image.prompt_json.items():
                        if not isinstance(node, dict):
                            continue
                        class_type = node.get('class_type')
                        inputs = node.get('inputs', {})
                        
                        # Buscar en modelos
                        if class_type in ('CheckpointLoaderSimple', 'CheckpointLoader'):
                            ckpt_name = inputs.get('ckpt_name', '')
                            if isinstance(ckpt_name, str) and search_term in ckpt_name.lower():
                                return True
                        
                        # Buscar en LoRAs
                        if class_type in ('LoraLoader', 'LoraLoaderModelOnly'):
                            lora_name = inputs.get('lora_name', '')
                            if isinstance(lora_name, str) and search_term in lora_name.lower():
                                return True
                
                # Buscar en workflow_json
                if image.workflow_json and isinstance(image.workflow_json, dict):
                    for node_id, node in image.workflow_json.items():
                        if not isinstance(node, dict):
                            continue
                        class_type = node.get('class_type')
                        inputs = node.get('inputs', {})
                        
                        # Buscar en modelos
                        if class_type in ('CheckpointLoaderSimple', 'CheckpointLoader'):
                            ckpt_name = inputs.get('ckpt_name', '')
                            if isinstance(ckpt_name, str) and search_term in ckpt_name.lower():
                                return True
                        
                        # Buscar en LoRAs
                        if class_type in ('LoraLoader', 'LoraLoaderModelOnly'):
                            lora_name = inputs.get('lora_name', '')
                            if isinstance(lora_name, str) and search_term in lora_name.lower():
                                return True
                
                return False
            
            # Filtrar imágenes usando list comprehension (más eficiente)
            all_images = [img for img in all_images if matches_search(img)]

        if missing_checkpoint or missing_lora or checkpoint_name or lora_name or folder_type:
            normalized_folder_type = (folder_type or "").strip().lower()
            normalized_checkpoint = (checkpoint_name or "").strip()
            normalized_lora = (lora_name or "").strip()
            filtered_by_metadata: List[Image] = []
            for image in all_images:
                model_name, loras = extract_model_and_loras_from_json(image.prompt_json, image.workflow_json)
                lora_names = {item.name for item in loras}
                detected_folder_type = classify_folder_type_from_rel_path(str(image.path or ""))

                if missing_checkpoint and model_name:
                    continue
                if missing_lora and lora_names:
                    continue
                if normalized_checkpoint and model_name != normalized_checkpoint:
                    continue
                if normalized_lora and normalized_lora not in lora_names:
                    continue
                if normalized_folder_type and detected_folder_type.lower() != normalized_folder_type:
                    continue

                filtered_by_metadata.append(image)

            all_images = filtered_by_metadata

        # Filtrar por tags efectivos heredados de nodo si corresponde
        include_tag_ids = include_tag_ids or []
        exclude_tag_ids = exclude_tag_ids or []
        include_set = set(include_tag_ids)
        exclude_set = set(exclude_tag_ids)
        if include_set or exclude_set:
            effective_maps_by_folder: Dict[str, Dict[int, set[int]]] = {}
            effective_maps_by_rel_path: Dict[str, Dict[str, set[int]]] = {}
            folder_ids = sorted({img.folder_id for img in all_images})
            for fid in folder_ids:
                effective_maps_by_folder[fid] = await _build_effective_tags_map_for_folder(db, fid)
                nodes_result = await db.execute(
                    select(FolderNode)
                    .where(FolderNode.folder_root_id == fid)
                    .order_by(FolderNode.depth.asc())
                )
                nodes = nodes_result.scalars().all()
                by_id = {n.id: n for n in nodes}
                rel_map: Dict[str, set[int]] = {}
                own_tags_map: Dict[int, set[int]] = {}
                tags_result = await db.execute(
                    select(folder_node_tags.c.folder_node_id, folder_node_tags.c.tag_id)
                    .where(folder_node_tags.c.folder_node_id.in_([n.id for n in nodes] if nodes else [-1]))
                )
                for n_id, t_id in tags_result.fetchall():
                    own_tags_map.setdefault(n_id, set()).add(t_id)
                for node in nodes:
                    merged = set(own_tags_map.get(node.id, set()))
                    parent_id = node.parent_node_id
                    while parent_id is not None:
                        merged.update(own_tags_map.get(parent_id, set()))
                        parent_node = by_id.get(parent_id)
                        if not parent_node:
                            break
                        parent_id = parent_node.parent_node_id
                    rel_map[node.rel_path] = merged
                effective_maps_by_rel_path[fid] = rel_map

            def matches_tag_filters(image: Image) -> bool:
                node_tags: set[int]
                if image.folder_node_id is not None:
                    node_tags = effective_maps_by_folder.get(image.folder_id, {}).get(image.folder_node_id, set())
                else:
                    parent_rel = str(PurePosixPath(image.path).parent)
                    if parent_rel in (".", ""):
                        parent_rel = ""
                    node_tags = effective_maps_by_rel_path.get(image.folder_id, {}).get(parent_rel, set())
                if include_set and not include_set.issubset(node_tags):
                    return False
                if exclude_set and node_tags.intersection(exclude_set):
                    return False
                return True

            all_images = [img for img in all_images if matches_tag_filters(img)]
        
        # Orden natural por nombre de archivo para que ...0001, ...0002, ...0010 se muestren en secuencia humana.
        all_images = sorted(all_images, key=_image_natural_order_key)
        
        # Calcular total y aplicar paginación
        total = len(all_images)
        paginated_images = all_images[offset:offset + limit]
        
        response_images = [_image_to_response(img) for img in paginated_images]
        
        return ImagesListResponse(images=response_images, total=total)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener imágenes: {str(e)}"
        )


@router.get("/images/{image_id}", response_model=ImageResponse)
async def get_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """
    Obtiene una imagen por su ID
    
    Path Parameters:
        image_id: ID de la imagen
    """
    try:
        service = GalleryService(db)
        image = await service.get_image(image_id)
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Imagen con ID {image_id} no encontrada"
            )
        
        return _image_to_response(image)
    except HTTPException:
        # Re-lanzar HTTPException sin modificar
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener imagen: {str(e)}"
        )


@router.post("/images/{image_id}/reindex-metadata", response_model=ImageResponse)
async def reindex_image_metadata(image_id: int, db: AsyncSession = Depends(get_db)):
    """
    Re-indexa la metadata de una imagen existente
    Útil para actualizar imágenes que fueron indexadas antes de implementar la extracción de metadata
    """
    try:
        service = GalleryService(db)
        
        # Obtener la imagen
        result = await db.execute(
            select(Image).where(Image.id == image_id)
        )
        image = result.scalar_one_or_none()
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Imagen con ID {image_id} no encontrada"
            )
        
        # Obtener la carpeta
        folder_result = await db.execute(
            select(Folder).where(Folder.id == image.folder_id)
        )
        folder = folder_result.scalar_one()
        
        # Construir path absoluto
        folder_path = Path(folder.path)
        file_path = folder_path / image.path
        
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Archivo no encontrado: {file_path}"
            )
        
        # Extraer metadata
        metadata = service.metadata_service.extract_metadata(file_path)
        
        # Actualizar imagen
        image.prompt_json = metadata.prompt_json
        image.workflow_json = metadata.workflow_json
        
        await db.commit()
        await db.refresh(image)
        
        return _image_to_response(image)
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al re-indexar metadata: {str(e)}"
        )


class UpdateMetadataRequest(BaseModel):
    """Request model para actualizar metadatos de imagen"""
    model_name: Optional[str] = Field(None, description="Nuevo nombre del modelo")
    loras: Optional[List[Dict[str, Any]]] = Field(None, description="Lista de LoRAs actualizados. Cada LoRA debe tener: name, strength (opcional), strength_model (opcional)")


@router.patch("/images/{image_id}/metadata", response_model=ImageResponse)
async def update_image_metadata(
    image_id: int,
    request: UpdateMetadataRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Actualiza modelo y/o LoRAs en prompt_json y workflow_json, y escribe los chunks en el PNG si aplica.
    """
    try:
        result = await db.execute(
            select(Image).where(Image.id == image_id)
        )
        image = result.scalar_one_or_none()
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Imagen con ID {image_id} no encontrada"
            )
        
        if request.model_name is None and request.loras is None:
            return _image_to_response(image)
        
        new_pj, new_wj = apply_model_and_loras(
            image.prompt_json,
            image.workflow_json,
            model_name=request.model_name,
            loras=request.loras,
        )
        image.prompt_json = new_pj
        image.workflow_json = new_wj
        
        folder_result = await db.execute(
            select(Folder).where(Folder.id == image.folder_id)
        )
        folder = folder_result.scalar_one()
        file_path = Path(folder.path) / image.path
        
        if file_path.suffix.lower() == ".png" and file_path.is_file():
            writer = PNGMetadataWriter()
            writer.update_png_metadata(
                file_path,
                prompt_json=new_pj,
                workflow_json=new_wj,
            )
        
        await db.commit()
        await db.refresh(image)
        return _image_to_response(image)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando metadatos de imagen {image_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar metadatos: {str(e)}"
        )


@router.post("/folders/{folder_id}/reindex-metadata")
async def reindex_folder_metadata(
    folder_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Re-indexa la metadata de todas las imágenes en una carpeta que no tienen metadata
    """
    try:
        service = GalleryService(db)
        
        # Obtener la carpeta
        folder_result = await db.execute(
            select(Folder).where(Folder.id == folder_id)
        )
        folder = folder_result.scalar_one_or_none()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta con ID {folder_id} no encontrada"
            )
        
        # Obtener imágenes sin metadata
        result = await db.execute(
            select(Image).where(
                Image.folder_id == folder_id,
                (Image.prompt_json.is_(None)) | (Image.workflow_json.is_(None))
            )
        )
        images = result.scalars().all()
        
        folder_path = Path(folder.path)
        updated_count = 0
        error_count = 0
        errors = []
        
        for image in images:
            try:
                file_path = folder_path / image.path
                
                if not file_path.exists():
                    error_count += 1
                    errors.append(f"Archivo no encontrado: {image.path}")
                    continue
                
                # Extraer metadata
                metadata = service.metadata_service.extract_metadata(file_path)
                
                # Actualizar solo si hay metadata nueva
                if metadata.prompt_json or metadata.workflow_json:
                    image.prompt_json = metadata.prompt_json
                    image.workflow_json = metadata.workflow_json
                    updated_count += 1
            
            except Exception as e:
                error_count += 1
                errors.append(f"Error procesando {image.path}: {str(e)}")
        
        await db.commit()
        
        return {
            "folder_id": folder_id,
            "total_images": len(images),
            "updated_count": updated_count,
            "error_count": error_count,
            "errors": errors[:10]  # Limitar a 10 errores
        }
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al re-indexar metadata: {str(e)}"
        )


@router.post("/images/{image_id}/move-to-trash")
async def move_image_to_trash(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Mueve una imagen a la papelera de reciclaje
    No borra la imagen, solo la mueve físicamente y actualiza la referencia en la DB
    """
    moved_file: tuple[Path, Path] | None = None
    moved_thumb: tuple[Path, Path] | None = None
    try:
        result = await db.execute(select(Image).where(Image.id == image_id))
        image = result.scalar_one_or_none()
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Imagen con ID {image_id} no encontrada",
            )

        folder_result = await db.execute(select(Folder).where(Folder.id == image.folder_id))
        folder = folder_result.scalar_one_or_none()
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta con ID {image.folder_id} no encontrada",
            )

        original_folder_path = Path(folder.path)
        original_file_path = original_folder_path / image.path
        thumb_original = original_folder_path / image.thumb_path if image.thumb_path else None

        # Si el original ya no existe, limpiar miniatura y registro en vez de bloquear la vista.
        if not original_file_path.is_file():
            deleted_thumbnail_count = await asyncio.to_thread(
                _delete_image_thumbnails,
                original_folder_path,
                image.path,
                image.thumb_path,
            )
            thumbnail_deleted = deleted_thumbnail_count > 0
            await db.delete(image)
            await db.commit()
            logger.warning(
                "Imagen original ausente; registro limpiado: image_id=%s path=%s thumbnail_deleted=%s",
                image_id,
                original_file_path,
                thumbnail_deleted,
            )
            return {
                "message": (
                    "El archivo original ya no existía. Se eliminó su miniatura y el registro."
                    if thumbnail_deleted
                    else "El archivo original ya no existía. Se eliminó el registro pendiente."
                ),
                "image_id": image_id,
                "trash_path": None,
                "missing_original": True,
                "thumbnail_deleted": thumbnail_deleted,
            }

        trash_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.TRASH_PATH)
        )
        trash_setting = trash_result.scalar_one_or_none()
        if not trash_setting or not trash_setting.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ruta de papelera no configurada. Configúrala en Settings.",
            )

        trash_path = Path(trash_setting.value)
        trash_path.mkdir(parents=True, exist_ok=True)
        trash_folder_result = await db.execute(
            select(Folder).where(Folder.path == str(trash_path))
        )
        trash_folder = trash_folder_result.scalar_one_or_none()
        if not trash_folder:
            trash_folder = Folder(
                id=md5(str(trash_path).encode()).hexdigest(),
                path=str(trash_path),
                name="Papelera",
                enabled=False,
            )
            db.add(trash_folder)
            await db.flush()

        reserved_result = await db.execute(
            select(Image.path, Image.thumb_path).where(Image.folder_id == trash_folder.id)
        )
        reserved_rows = reserved_result.fetchall()
        reserved_image_names = {Path(str(row.path)).name for row in reserved_rows if row.path}
        reserved_thumb_names = {Path(str(row.thumb_path)).name for row in reserved_rows if row.thumb_path}

        dest_file_path = _next_available_trash_path(
            trash_path,
            original_file_path.name,
            reserved_image_names,
        )
        await asyncio.to_thread(shutil.move, str(original_file_path), str(dest_file_path))
        moved_file = (original_file_path, dest_file_path)
        logger.info("Imagen %s movida a papelera: %s -> %s", image_id, original_file_path, dest_file_path)

        new_thumb_path: str | None = None
        if thumb_original and thumb_original.is_file():
            preferred_thumb_name = f"{dest_file_path.stem}{thumb_original.suffix}"
            thumb_dest = _next_available_trash_path(
                trash_path,
                preferred_thumb_name,
                reserved_thumb_names | reserved_image_names | {dest_file_path.name},
            )
            await asyncio.to_thread(shutil.move, str(thumb_original), str(thumb_dest))
            moved_thumb = (thumb_original, thumb_dest)
            new_thumb_path = thumb_dest.name

        image.folder_id = trash_folder.id
        image.folder_node_id = None
        image.path = dest_file_path.name
        image.thumb_path = new_thumb_path
        await db.commit()
        await db.refresh(image)

        return {
            "message": f"Imagen movida a papelera como “{dest_file_path.name}”.",
            "image_id": image_id,
            "trash_path": str(dest_file_path),
            "missing_original": False,
            "thumbnail_deleted": False,
        }
    
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        for movement in (moved_thumb, moved_file):
            if movement is None:
                continue
            original, destination = movement
            if destination.exists() and not original.exists():
                try:
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(original))
                except OSError:
                    logger.error("Error restaurando archivo tras fallo de papelera", exc_info=True)
        logger.error(f"Error moviendo imagen a papelera: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al mover imagen a papelera: {str(e)}"
        )


@router.get("/images/{image_id}/thumbnail")
async def get_image_thumbnail(image_id: int, db: AsyncSession = Depends(get_db)):
    """
    Obtiene el thumbnail de una imagen
    
    Path Parameters:
        image_id: ID de la imagen
    """
    try:
        service = GalleryService(db)
        image = await service.get_image(image_id)
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Imagen con ID {image_id} no encontrada"
            )
        
        folder_result = await db.execute(
            select(Folder).where(Folder.id == image.folder_id)
        )
        folder = folder_result.scalar_one_or_none()
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta no encontrada para la imagen {image_id}"
            )
        folder_path = Path(folder.path)

        # thumb_path puede ser absoluto o relativo.
        # Si falta o está desfasado (caso histórico en subcarpetas), intentamos fallback.
        thumb_path: Path | None = None
        thumb_path_str = image.thumb_path or ""
        if thumb_path_str:
            candidate = Path(thumb_path_str)
            thumb_path = candidate if candidate.is_absolute() else folder_path / candidate
        else:
            thumb_path = folder_path / "__missing_thumb__"
        
        # Normalizar la ruta
        thumb_path = thumb_path.resolve()
        
        logger.debug(f"Buscando thumbnail para imagen {image_id}: {thumb_path}")
        
        if not thumb_path.exists():
            # Fallback para imágenes en subcarpetas con thumb_path legado.
            image_rel = Path(image.path)
            candidate_rel = (
                Path("thumb") / f"{image_rel.stem}.jpg"
                if str(image_rel.parent) in ("", ".")
                else image_rel.parent / "thumb" / f"{image_rel.stem}.jpg"
            )
            candidate_abs = (folder_path / candidate_rel).resolve()
            if candidate_abs.exists():
                thumb_path = candidate_abs
                # Auto-reparar referencia para próximas consultas.
                image.thumb_path = str(candidate_rel)
                await db.commit()
            else:
                logger.error(f"Thumbnail no encontrado en disco: {thumb_path} (thumb_path en DB: {image.thumb_path})")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Archivo de thumbnail no encontrado: {thumb_path}"
                )
        
        return FileResponse(
            path=thumb_path,
            media_type="image/jpeg",
            filename=f"thumb_{image_id}.jpg"
        )
    except HTTPException:
        # Re-lanzar HTTPException sin modificar
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener thumbnail: {str(e)}"
        )


@router.get("/images/{image_id}/full")
async def get_full_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """
    Obtiene la imagen completa en tamaño original
    
    Path Parameters:
        image_id: ID de la imagen
    """
    try:
        # Obtener imagen directamente de la DB para asegurar datos actualizados
        image_result = await db.execute(
            select(Image).where(Image.id == image_id)
        )
        image = image_result.scalar_one_or_none()
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Imagen con ID {image_id} no encontrada"
            )
        
        logger.debug(f"Imagen {image_id}: folder_id={image.folder_id}, path={image.path}")
        
        # Obtener la carpeta para construir el path absoluto
        folder_result = await db.execute(
            select(Folder).where(Folder.id == image.folder_id)
        )
        folder = folder_result.scalar_one_or_none()
        
        if not folder:
            logger.error(f"Carpeta no encontrada para imagen {image_id}, folder_id={image.folder_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Carpeta no encontrada para la imagen {image_id}"
            )
        
        logger.debug(f"Carpeta encontrada: id={folder.id}, path={folder.path}")
        
        # Construir path absoluto de la imagen
        folder_path = Path(folder.path).resolve()  # Resolver para obtener ruta absoluta normalizada
        full_image_path = (folder_path / image.path).resolve()
        
        logger.info(f"Buscando imagen {image_id} en: {full_image_path}")
        logger.info(f"  - folder.path: {folder.path}")
        logger.info(f"  - image.path: {image.path}")
        logger.info(f"  - folder_path (resolved): {folder_path}")
        logger.info(f"  - full_image_path (resolved): {full_image_path}")
        logger.info(f"  - Existe: {full_image_path.exists()}")
        
        if not full_image_path.exists():
            # Intentar verificar si el problema es con la ruta
            logger.error(f"Archivo no encontrado: {full_image_path}")
            logger.error(f"  - folder_path.exists(): {folder_path.exists()}")
            if folder_path.exists():
                # Listar archivos en la carpeta para debug
                try:
                    files_in_folder = list(folder_path.iterdir())
                    logger.error(f"  - Archivos en carpeta: {[f.name for f in files_in_folder]}")
                except Exception as e:
                    logger.error(f"  - Error listando carpeta: {e}")
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Archivo de imagen no encontrado: {full_image_path}"
            )
        
        # Determinar el tipo MIME basado en la extensión
        extension = full_image_path.suffix.lower()
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp'
        }
        media_type = media_types.get(extension, 'image/jpeg')
        
        logger.info(f"Sirviendo imagen {image_id}: {full_image_path.name} ({media_type})")
        
        return FileResponse(
            path=str(full_image_path),  # Asegurar que sea string
            media_type=media_type,
            filename=full_image_path.name
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener imagen completa: {str(e)}"
        )


class MoveImagesRequest(BaseModel):
    """Request model para mover imágenes a una carpeta"""
    image_ids: List[int] = Field(..., description="Lista de IDs de imágenes a mover")
    folder_name: str = Field(..., min_length=1, description="Nombre de la carpeta destino (dentro de IMG_SORTED_PATH)")


class OrganizerFolderCreateRequest(BaseModel):
    """Crea una carpeta o subcarpeta dentro de la carpeta ordenada."""

    name: str = Field(..., min_length=1, max_length=120)
    parent_path: str = Field("", description="Ruta relativa de la carpeta padre")


class OrganizerFolderRenameRequest(BaseModel):
    """Renombra una carpeta ordenada y las imágenes que contiene directamente."""

    path: str = Field(..., min_length=1, description="Ruta relativa actual")
    new_name: str = Field(..., min_length=1, max_length=120)


class OrganizerFoldersMoveRequest(BaseModel):
    """Mueve una o más carpetas existentes dentro de otra carpeta ordenada."""

    source_paths: List[str] = Field(..., min_length=1)
    destination_path: str = Field(..., min_length=1)


class OrganizerSourceFoldersMoveRequest(BaseModel):
    """Mueve subcarpetas originales completas al árbol ordenado."""

    source_nodes: List[SourceFolderNodeMoveItem] = Field(..., min_length=1)
    destination_path: str = Field(..., min_length=1)


class OrganizerMoveRequest(BaseModel):
    """Mueve una selección de imágenes al árbol del organizador."""

    image_ids: List[int] = Field(..., min_length=1)
    destination_path: str = Field(..., min_length=1, description="Ruta relativa de destino")


ORGANIZER_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"
}
ORGANIZER_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*]')


async def _get_organizer_root(db: AsyncSession, *, create: bool = False) -> Path | None:
    result = await db.execute(
        select(Setting).where(Setting.key == SettingKeys.IMG_SORTED_PATH)
    )
    setting = result.scalar_one_or_none()
    if not setting or not setting.value or not setting.value.strip():
        return None

    root = Path(setting.value).expanduser().resolve()
    if create:
        await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    return root


async def _organizer_configuration_error(db: AsyncSession, root: Path) -> str | None:
    """Evita mezclar el árbol temporal de salida con el árbol maestro de origen."""
    result = await db.execute(
        select(Setting).where(Setting.key == SettingKeys.IMG_MASTER_PATH)
    )
    setting = result.scalar_one_or_none()
    if not setting or not setting.value or not setting.value.strip():
        return None

    master = Path(setting.value).expanduser().resolve()
    overlaps = root == master or master in root.parents or root in master.parents
    if overlaps:
        return (
            "La carpeta ordenada debe ser independiente de la carpeta maestra de origen. "
            "Selecciona otra ubicación en Settings."
        )
    return None


def _organizer_relative_parts(relative_path: str, *, allow_empty: bool = True) -> list[str]:
    normalized = (relative_path or "").strip().replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ValueError("absolute_path_not_allowed")
    normalized = normalized.strip("/")
    if not normalized:
        if allow_empty:
            return []
        raise ValueError("destination_required")

    pure = PurePosixPath(normalized)
    parts = list(pure.parts)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in parts):
        raise ValueError("invalid_relative_path")
    if any(part.lower() == "thumb" for part in parts):
        raise ValueError("thumb_is_reserved")
    return parts


def _organizer_child_path(root: Path, relative_path: str, *, allow_empty: bool = True) -> Path:
    parts = _organizer_relative_parts(relative_path, allow_empty=allow_empty)
    candidate = root.joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("path_escape")
    return candidate


def _organizer_rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _collapse_organizer_move_sources(paths: List[str]) -> list[str]:
    """Quita duplicados y descendientes cuando su carpeta padre ya fue seleccionada."""
    normalized: list[str] = []
    for value in paths:
        parts = _organizer_relative_parts(value, allow_empty=False)
        relative = PurePosixPath(*parts).as_posix()
        if relative not in normalized:
            normalized.append(relative)

    normalized.sort(key=lambda value: (len(PurePosixPath(value).parts), value.casefold()))
    collapsed: list[str] = []
    for candidate in normalized:
        if any(candidate.startswith(f"{parent}/") for parent in collapsed):
            continue
        collapsed.append(candidate)
    return collapsed


def _organizer_prefix(folder_name: str) -> str:
    prefix = re.sub(r"[^\w-]+", "_", folder_name.strip(), flags=re.UNICODE).strip("_-.")
    if not prefix:
        raise ValueError("invalid_folder_name")
    return prefix.lower()


def _validate_organizer_folder_name(name: str) -> str:
    normalized = name.strip()
    if (
        not normalized
        or normalized in (".", "..")
        or normalized.lower() == "thumb"
        or ORGANIZER_INVALID_FOLDER_CHARS.search(normalized)
        or normalized.endswith((" ", "."))
    ):
        raise ValueError("invalid_folder_name")
    return normalized


def _organizer_tree(root: Path) -> tuple[list[dict[str, Any]], int]:
    def visit(directory: Path) -> tuple[dict[str, Any], int]:
        children: list[dict[str, Any]] = []
        total = 0
        try:
            entries = sorted(directory.iterdir(), key=lambda item: _natural_sort_key(item.name))
        except OSError:
            entries = []

        direct_images = sum(
            1
            for item in entries
            if item.is_file() and item.suffix.lower() in ORGANIZER_IMAGE_EXTENSIONS
        )
        total += direct_images
        for item in entries:
            if not item.is_dir() or item.name.lower() == "thumb":
                continue
            child, child_total = visit(item)
            children.append(child)
            total += child_total

        # En cada nivel, mostrar primero las ramas que contienen subcarpetas
        # y luego las carpetas simples. Dentro de cada grupo se mantiene el
        # orden natural por nombre.
        children.sort(
            key=lambda child: (
                0 if child["children"] else 1,
                _natural_sort_key(child["name"]),
            )
        )

        return (
            {
                "name": directory.name,
                "path": _organizer_rel(root, directory),
                "image_count": direct_images,
                "total_image_count": total,
                "has_thumb": (directory / "thumb").is_dir(),
                "children": children,
            },
            total,
        )

    nodes: list[dict[str, Any]] = []
    grand_total = 0
    if not root.is_dir():
        return nodes, grand_total
    try:
        top_level = sorted(root.iterdir(), key=lambda item: _natural_sort_key(item.name))
    except OSError:
        top_level = []
    for item in top_level:
        if not item.is_dir() or item.name.lower() == "thumb":
            continue
        node, node_total = visit(item)
        nodes.append(node)
        grand_total += node_total
    nodes.sort(
        key=lambda node: (
            0 if node["children"] else 1,
            _natural_sort_key(node["name"]),
        )
    )
    return nodes, grand_total


async def _ensure_organizer_folder_record(db: AsyncSession, root: Path) -> Folder:
    folder_id = md5(str(root).encode()).hexdigest()
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if folder:
        return folder

    folder = Folder(
        id=folder_id,
        path=str(root),
        name="Mnemos galery · Ordenadas",
        enabled=True,
    )
    db.add(folder)
    await db.flush()
    return folder


@router.post("/folders/open")
async def open_folder_in_explorer(
    path: str = Query(..., description="Ruta de la carpeta a abrir")
):
    """
    Abre una carpeta en el explorador de archivos del sistema
    """
    import os
    import platform
    from pathlib import Path
    
    try:
        folder_path = Path(path)
        
        if not folder_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La carpeta no existe: {path}"
            )
        
        if not folder_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La ruta no es una carpeta: {path}"
            )
        
        # Abrir carpeta según el sistema operativo
        system = platform.system()
        
        if system == "Windows":
            os.startfile(str(folder_path))
        elif system == "Darwin":  # macOS
            os.system(f'open "{folder_path}"')
        elif system == "Linux":
            os.system(f'xdg-open "{folder_path}"')
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Sistema operativo no soportado: {system}"
            )
        
        return {"message": f"Carpeta abierta: {path}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al abrir carpeta: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al abrir carpeta: {str(e)}"
        )


@router.get("/organizer")
async def get_organizer(db: AsyncSession = Depends(get_db)):
    """Retorna la configuración y el árbol físico de carpetas ordenadas."""
    root = await _get_organizer_root(db)
    if root is None:
        return {
            "configured": False,
            "root_path": None,
            "folder_id": None,
            "configuration_error": None,
            "tree": [],
            "total_images": 0,
        }

    configuration_error = await _organizer_configuration_error(db, root)
    if configuration_error:
        return {
            "configured": False,
            "root_path": str(root),
            "folder_id": None,
            "configuration_error": configuration_error,
            "tree": [],
            "total_images": 0,
        }

    tree, total_images = await asyncio.to_thread(_organizer_tree, root)
    folder_id = md5(str(root).encode()).hexdigest()
    return {
        "configured": True,
        "root_path": str(root),
        "folder_id": folder_id,
        "configuration_error": None,
        "tree": tree,
        "total_images": total_images,
    }


@router.post("/organizer/folders", status_code=status.HTTP_201_CREATED)
async def create_organizer_folder(
    request: OrganizerFolderCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Crea una carpeta del organizador y su directorio reservado de miniaturas."""
    root = await _get_organizer_root(db, create=True)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configura primero la carpeta ordenada en Settings.",
        )
    configuration_error = await _organizer_configuration_error(db, root)
    if configuration_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=configuration_error)

    try:
        name = _validate_organizer_folder_name(request.name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de carpeta no es válido o está reservado.",
        )

    try:
        parent = _organizer_child_path(root, request.parent_path)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La carpeta padre no es válida.",
        )
    if not parent.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La carpeta padre no existe.",
        )

    target = (parent / name).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ruta fuera del organizador.")
    if target.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La carpeta ya existe.")

    try:
        await asyncio.to_thread(target.mkdir)
        await asyncio.to_thread((target / "thumb").mkdir)
    except OSError as exc:
        logger.error("organizer_folder_create_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear la carpeta: {exc}",
        )

    tree, total_images = await asyncio.to_thread(_organizer_tree, root)
    return {
        "created_path": _organizer_rel(root, target),
        "tree": tree,
        "total_images": total_images,
    }


@router.patch("/organizer/folders")
async def rename_organizer_folder(
    request: OrganizerFolderRenameRequest,
    db: AsyncSession = Depends(get_db),
):
    """Renombra una carpeta, sus imágenes directas, miniaturas y rutas persistidas."""
    root = await _get_organizer_root(db)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configura primero la carpeta ordenada en Settings.",
        )
    configuration_error = await _organizer_configuration_error(db, root)
    if configuration_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=configuration_error)

    try:
        source = _organizer_child_path(root, request.path, allow_empty=False)
        new_name = _validate_organizer_folder_name(request.new_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La ruta o el nuevo nombre no son válidos.",
        )
    if not source.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La carpeta no existe.")

    old_rel = _organizer_rel(root, source)
    target = source.parent / new_name
    new_rel = _organizer_rel(root, target)
    if source.name == new_name:
        tree, total_images = await asyncio.to_thread(_organizer_tree, root)
        return {
            "message": "La carpeta ya tiene ese nombre.",
            "old_path": old_rel,
            "new_path": old_rel,
            "renamed_image_count": 0,
            "tree": tree,
            "total_images": total_images,
        }

    same_windows_path = str(source).casefold() == str(target).casefold()
    if target.exists() and not same_windows_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe otra carpeta con ese nombre en el mismo nivel.",
        )

    direct_images = sorted(
        [
            item
            for item in source.iterdir()
            if item.is_file() and item.suffix.lower() in ORGANIZER_IMAGE_EXTENSIONS
        ],
        key=lambda item: _natural_sort_key(item.name),
    )
    prefix = _organizer_prefix(new_name)
    width = max(2, len(str(len(direct_images))))
    rename_plans: list[dict[str, Any]] = []
    direct_path_map: dict[str, str] = {}
    direct_thumb_map: dict[str, str] = {}

    for index, original in enumerate(direct_images, start=1):
        final_name = f"{prefix}_{index:0{width}d}{original.suffix}"
        final = source / final_name
        temp = source / f".mnemos-rename-{uuid4().hex}{original.suffix}"
        rename_plans.append(
            {
                "original_rel": Path(original.name),
                "temp_rel": Path(temp.name),
                "final_rel": Path(final.name),
            }
        )
        direct_path_map[f"{old_rel}/{original.name}"] = f"{new_rel}/{final_name}"

        old_thumb_rel = f"{old_rel}/thumb/{original.stem}.jpg"
        new_thumb_rel = f"{new_rel}/thumb/{Path(final_name).stem}.jpg"
        direct_thumb_map[old_thumb_rel] = new_thumb_rel
        thumb = source / "thumb" / f"{original.stem}.jpg"
        if thumb.is_file():
            thumb_final = source / "thumb" / f"{Path(final_name).stem}.jpg"
            thumb_temp = source / "thumb" / f".mnemos-rename-{uuid4().hex}.jpg"
            rename_plans.append(
                {
                    "original_rel": thumb.relative_to(source),
                    "temp_rel": thumb_temp.relative_to(source),
                    "final_rel": thumb_final.relative_to(source),
                }
            )

    # Cargar y preparar las rutas persistidas antes de tocar el sistema de archivos.
    destination_folder_id = md5(str(root).encode()).hexdigest()
    images_result = await db.execute(
        select(Image).where(Image.folder_id == destination_folder_id)
    )
    affected_images = []
    old_prefix = f"{old_rel}/"
    new_prefix = f"{new_rel}/"
    for image in images_result.scalars().all():
        image_path = str(image.path).replace("\\", "/")
        thumb_path = str(image.thumb_path).replace("\\", "/") if image.thumb_path else None
        if image_path == old_rel or image_path.startswith(old_prefix):
            image.path = direct_path_map.get(
                image_path,
                new_prefix + image_path[len(old_prefix):],
            )
            if thumb_path:
                image.thumb_path = direct_thumb_map.get(
                    thumb_path,
                    new_prefix + thumb_path[len(old_prefix):]
                    if thumb_path.startswith(old_prefix)
                    else thumb_path,
                )
            affected_images.append(image)

    nodes_result = await db.execute(
        select(FolderNode).where(FolderNode.folder_root_id == destination_folder_id)
    )
    affected_nodes = []
    for node in nodes_result.scalars().all():
        node_rel = str(node.rel_path).replace("\\", "/")
        if node_rel == old_rel:
            node.rel_path = new_rel
            node.name = new_name
            affected_nodes.append(node)
        elif node_rel.startswith(old_prefix):
            node.rel_path = new_prefix + node_rel[len(old_prefix):]
            affected_nodes.append(node)

    finalized_plans: list[dict[str, Any]] = []
    staged_plans: list[dict[str, Any]] = []
    folder_renamed = False
    intermediate_folder: Path | None = None

    try:
        # Dos fases evitan colisiones entre nombres existentes y los nuevos correlativos.
        for plan in rename_plans:
            original_path = source / plan["original_rel"]
            temp_path = source / plan["temp_rel"]
            await asyncio.to_thread(original_path.rename, temp_path)
            staged_plans.append(plan)

        for plan in rename_plans:
            temp_path = source / plan["temp_rel"]
            final_path = source / plan["final_rel"]
            await asyncio.to_thread(temp_path.rename, final_path)
            finalized_plans.append(plan)

        if same_windows_path:
            intermediate_folder = source.parent / f".mnemos-folder-{uuid4().hex}"
            await asyncio.to_thread(source.rename, intermediate_folder)
            await asyncio.to_thread(intermediate_folder.rename, target)
        else:
            await asyncio.to_thread(source.rename, target)
        folder_renamed = True

        await db.commit()
    except Exception as exc:
        await db.rollback()
        if intermediate_folder and intermediate_folder.exists() and not source.exists():
            try:
                intermediate_folder.rename(source)
            except OSError:
                logger.error("organizer_intermediate_folder_rollback_failed", exc_info=True)
        rollback_base = target if folder_renamed else source
        if folder_renamed and target.exists():
            try:
                if same_windows_path:
                    rollback_temp = target.parent / f".mnemos-folder-rollback-{uuid4().hex}"
                    target.rename(rollback_temp)
                    rollback_temp.rename(source)
                else:
                    target.rename(source)
                rollback_base = source
            except OSError:
                logger.error("organizer_folder_rename_rollback_failed", exc_info=True)

        for plan in reversed(finalized_plans):
            final_path = rollback_base / plan["final_rel"]
            original_path = rollback_base / plan["original_rel"]
            if final_path.exists() and not original_path.exists():
                try:
                    final_path.rename(original_path)
                except OSError:
                    logger.error("organizer_file_rename_rollback_failed", exc_info=True)
        for plan in reversed(staged_plans):
            temp_path = rollback_base / plan["temp_rel"]
            original_path = rollback_base / plan["original_rel"]
            if temp_path.exists() and not original_path.exists():
                try:
                    temp_path.rename(original_path)
                except OSError:
                    logger.error("organizer_temp_rename_rollback_failed", exc_info=True)

        logger.error("organizer_folder_rename_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo renombrar la carpeta; se revirtieron los cambios: {exc}",
        )

    tree, total_images = await asyncio.to_thread(_organizer_tree, root)
    renamed_count = len(direct_images)
    return {
        "message": (
            f"Carpeta renombrada y {renamed_count} imagen"
            f"{'es' if renamed_count != 1 else ''} actualizada{'s' if renamed_count != 1 else ''}."
            if renamed_count
            else "Carpeta vacía renombrada."
        ),
        "old_path": old_rel,
        "new_path": new_rel,
        "renamed_image_count": renamed_count,
        "updated_database_images": len(affected_images),
        "updated_database_nodes": len(affected_nodes),
        "tree": tree,
        "total_images": total_images,
    }


@router.post("/organizer/folders/move")
async def move_organizer_folders(
    request: OrganizerFoldersMoveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Corta una o más carpetas ordenadas y las inserta dentro de otra."""
    root = await _get_organizer_root(db)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configura primero la carpeta ordenada en Settings.",
        )
    configuration_error = await _organizer_configuration_error(db, root)
    if configuration_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=configuration_error)

    try:
        source_rel_paths = _collapse_organizer_move_sources(request.source_paths)
        destination = _organizer_child_path(root, request.destination_path, allow_empty=False)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Una de las rutas de carpeta no es válida.",
        )

    if not destination.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La carpeta destino no existe.")

    move_plans: list[dict[str, Any]] = []
    target_names: set[str] = set()
    for source_rel in source_rel_paths:
        source = _organizer_child_path(root, source_rel, allow_empty=False)
        if not source.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La carpeta '{source_rel}' ya no existe.",
            )
        if destination == source or source in destination.parents:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No puedes mover '{source.name}' dentro de sí misma o de una subcarpeta suya.",
            )

        target = destination / source.name
        target_name_key = source.name.casefold()
        if target == source:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La carpeta '{source.name}' ya está dentro del destino seleccionado.",
            )
        if target.exists() or target_name_key in target_names:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El destino ya contiene una carpeta llamada '{source.name}'.",
            )
        target_names.add(target_name_key)
        move_plans.append(
            {
                "source": source,
                "target": target,
                "old_rel": source_rel,
                "new_rel": _organizer_rel(root, target),
            }
        )

    organizer_folder = await _ensure_organizer_folder_record(db, root)
    organizer_folder_id = organizer_folder.id
    service = GalleryService(db)
    node_cache = await service._load_folder_nodes_cache(organizer_folder_id)
    destination_rel = _organizer_rel(root, destination)
    destination_node = await service._ensure_folder_node_for_relative_path(
        folder_id=organizer_folder_id,
        folder_name=organizer_folder.name,
        relative_path=f"{destination_rel}/__mnemos_placeholder__.png",
        node_cache=node_cache,
    )
    for plan in move_plans:
        source_node = node_cache.get(plan["old_rel"])
        plan["source_node_id"] = source_node.id if source_node else None
        plan["depth_delta"] = (
            destination_node.depth + 1 - source_node.depth
            if source_node
            else 0
        )

    images_result = await db.execute(
        select(Image).where(Image.folder_id == organizer_folder_id)
    )
    affected_images = []
    for image in images_result.scalars().all():
        image_path = str(image.path).replace("\\", "/")
        thumb_path = str(image.thumb_path).replace("\\", "/") if image.thumb_path else None
        for plan in move_plans:
            old_prefix = f"{plan['old_rel']}/"
            if image_path.startswith(old_prefix):
                new_prefix = f"{plan['new_rel']}/"
                image.path = new_prefix + image_path[len(old_prefix):]
                if thumb_path and thumb_path.startswith(old_prefix):
                    image.thumb_path = new_prefix + thumb_path[len(old_prefix):]
                affected_images.append(image)
                break

    nodes_result = await db.execute(
        select(FolderNode).where(FolderNode.folder_root_id == organizer_folder_id)
    )
    affected_nodes = []
    for node in nodes_result.scalars().all():
        node_rel = str(node.rel_path).replace("\\", "/")
        for plan in move_plans:
            old_rel = plan["old_rel"]
            old_prefix = f"{old_rel}/"
            if node_rel == old_rel:
                node.rel_path = plan["new_rel"]
                if plan["source_node_id"] == node.id:
                    node.parent_node_id = destination_node.id
                node.depth += int(plan["depth_delta"])
                affected_nodes.append(node)
                break
            if node_rel.startswith(old_prefix):
                node.rel_path = f"{plan['new_rel']}/{node_rel[len(old_prefix):]}"
                node.depth += int(plan["depth_delta"])
                affected_nodes.append(node)
                break

    completed_plans: list[dict[str, Any]] = []
    try:
        for plan in move_plans:
            await asyncio.to_thread(plan["source"].rename, plan["target"])
            completed_plans.append(plan)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        for plan in reversed(completed_plans):
            try:
                if plan["target"].exists() and not plan["source"].exists():
                    plan["target"].rename(plan["source"])
            except OSError:
                logger.error("organizer_folder_move_rollback_failed", exc_info=True)
        logger.error("organizer_folder_move_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudieron mover las carpetas; se revirtieron los cambios: {exc}",
        )

    tree, total_images = await asyncio.to_thread(_organizer_tree, root)
    moved_paths = {
        str(plan["old_rel"]): str(plan["new_rel"])
        for plan in move_plans
    }
    moved_count = len(move_plans)
    return {
        "message": f"{moved_count} carpeta{'s' if moved_count != 1 else ''} movida{'s' if moved_count != 1 else ''}.",
        "moved_count": moved_count,
        "moved_paths": moved_paths,
        "updated_database_images": len(affected_images),
        "updated_database_nodes": len(affected_nodes),
        "tree": tree,
        "total_images": total_images,
    }


@router.post("/organizer/source-folders/move")
async def move_source_folders_to_organizer(
    request: OrganizerSourceFoldersMoveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Corta subcarpetas originales completas y las pega en una carpeta ordenada."""
    root = await _get_organizer_root(db, create=True)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configura primero la carpeta ordenada en Settings.",
        )
    configuration_error = await _organizer_configuration_error(db, root)
    if configuration_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=configuration_error)

    try:
        destination = _organizer_child_path(root, request.destination_path, allow_empty=False)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La carpeta destino no es válida.")
    if not destination.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La carpeta destino no existe.")

    organizer_folder = await _ensure_organizer_folder_record(db, root)
    service = GalleryService(db)
    organizer_node_cache = await service._load_folder_nodes_cache(organizer_folder.id)
    destination_rel = _organizer_rel(root, destination)
    destination_node = await service._ensure_folder_node_for_relative_path(
        folder_id=organizer_folder.id,
        folder_name=organizer_folder.name,
        relative_path=f"{destination_rel}/__mnemos_placeholder__.png",
        node_cache=organizer_node_cache,
    )

    folders_cache: dict[str, Folder] = {}
    requested_keys: set[tuple[str, int]] = set()
    raw_plans: list[dict[str, Any]] = []
    for item in request.source_nodes:
        key = (item.folder_id, int(item.node_id))
        if key in requested_keys:
            continue
        requested_keys.add(key)
        if item.folder_id == organizer_folder.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selecciona carpetas originales, no carpetas que ya están ordenadas.",
            )

        source_folder = folders_cache.get(item.folder_id)
        if source_folder is None:
            folder_result = await db.execute(select(Folder).where(Folder.id == item.folder_id))
            source_folder = folder_result.scalar_one_or_none()
            if not source_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Una carpeta original no existe.")
            folders_cache[item.folder_id] = source_folder

        node_result = await db.execute(
            select(FolderNode).where(
                FolderNode.id == item.node_id,
                FolderNode.folder_root_id == item.folder_id,
            )
        )
        source_node = node_result.scalar_one_or_none()
        if not source_node:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Una subcarpeta original no existe.")
        source_rel = str(source_node.rel_path).replace("\\", "/").strip("/")
        is_root_node = not source_rel
        source_root = Path(source_folder.path).resolve()
        source = source_root if is_root_node else (source_root / Path(source_rel)).resolve()
        if (not is_root_node and source_root not in source.parents) or not source.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La carpeta '{source_folder.name if is_root_node else source_node.name}' no existe en el disco.",
            )
        raw_plans.append(
            {
                "folder": source_folder,
                "node": source_node,
                "old_rel": source_rel,
                "source": source,
                "is_root": is_root_node,
            }
        )

    raw_plans.sort(key=lambda plan: (len(PurePosixPath(plan["old_rel"]).parts), plan["old_rel"].casefold()))
    plans: list[dict[str, Any]] = []
    for plan in raw_plans:
        if any(
            existing["folder"].id == plan["folder"].id
            and (
                existing["is_root"]
                or plan["old_rel"].startswith(f"{existing['old_rel']}/")
            )
            for existing in plans
        ):
            continue
        plans.append(plan)

    target_names: set[str] = set()
    for plan in plans:
        target = destination / plan["source"].name
        name_key = target.name.casefold()
        if target.exists() or name_key in target_names:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La carpeta ordenada ya contiene una carpeta llamada '{target.name}'.",
            )
        target_names.add(name_key)
        plan["target"] = target
        plan["new_rel"] = f"{destination_rel}/{target.name}"
        plan["depth_delta"] = destination_node.depth + 1 - plan["node"].depth

    source_folder_ids = list({plan["folder"].id for plan in plans})
    nodes_result = await db.execute(
        select(FolderNode).where(FolderNode.folder_root_id.in_(source_folder_ids))
    )
    affected_nodes = []
    for node in nodes_result.scalars().all():
        node_rel = str(node.rel_path).replace("\\", "/").strip("/")
        for plan in plans:
            if node.folder_root_id != plan["folder"].id:
                continue
            old_rel = plan["old_rel"]
            old_prefix = f"{old_rel}/"
            if plan["is_root"]:
                node.folder_root_id = organizer_folder.id
                if node.id == plan["node"].id:
                    node.parent_node_id = destination_node.id
                    node.rel_path = plan["new_rel"]
                else:
                    node.rel_path = f"{plan['new_rel']}/{node_rel}"
                node.depth += int(plan["depth_delta"])
                affected_nodes.append(node)
                break
            if node_rel == old_rel:
                node.folder_root_id = organizer_folder.id
                node.parent_node_id = destination_node.id
                node.rel_path = plan["new_rel"]
                node.depth += int(plan["depth_delta"])
                affected_nodes.append(node)
                break
            if node_rel.startswith(old_prefix):
                node.folder_root_id = organizer_folder.id
                node.rel_path = f"{plan['new_rel']}/{node_rel[len(old_prefix):]}"
                node.depth += int(plan["depth_delta"])
                affected_nodes.append(node)
                break

    images_result = await db.execute(select(Image).where(Image.folder_id.in_(source_folder_ids)))
    affected_images = []
    for image in images_result.scalars().all():
        image_path = str(image.path).replace("\\", "/")
        thumb_path = str(image.thumb_path).replace("\\", "/") if image.thumb_path else None
        for plan in plans:
            if image.folder_id != plan["folder"].id:
                continue
            if plan["is_root"]:
                new_prefix = f"{plan['new_rel']}/"
                image.folder_id = organizer_folder.id
                image.path = new_prefix + image_path
                if thumb_path:
                    image.thumb_path = new_prefix + thumb_path
                affected_images.append(image)
                break
            old_prefix = f"{plan['old_rel']}/"
            if not image_path.startswith(old_prefix):
                continue
            new_prefix = f"{plan['new_rel']}/"
            image.folder_id = organizer_folder.id
            image.path = new_prefix + image_path[len(old_prefix):]
            if thumb_path and thumb_path.startswith(old_prefix):
                image.thumb_path = new_prefix + thumb_path[len(old_prefix):]
            affected_images.append(image)
            break

    moved_root_folder_ids = [
        plan["folder"].id
        for plan in plans
        if plan["is_root"]
    ]

    completed_plans: list[dict[str, Any]] = []
    try:
        for plan in plans:
            await asyncio.to_thread(shutil.move, str(plan["source"]), str(plan["target"]))
            completed_plans.append(plan)
        if moved_root_folder_ids:
            # Persiste primero la reasignación para que la eliminación de la raíz
            # original no alcance por cascada a nodos o imágenes ya organizados.
            await db.flush()
            await db.execute(delete(Folder).where(Folder.id.in_(moved_root_folder_ids)))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        for plan in reversed(completed_plans):
            try:
                if plan["target"].exists() and not plan["source"].exists():
                    plan["source"].parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(plan["target"]), str(plan["source"]))
            except OSError:
                logger.error("organizer_source_folder_move_rollback_failed", exc_info=True)
        logger.error("organizer_source_folder_move_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudieron mover las carpetas; se revirtieron los cambios: {exc}",
        )

    tree, total_images = await asyncio.to_thread(_organizer_tree, root)
    moved_count = len(plans)
    return {
        "message": f"{moved_count} carpeta{'s' if moved_count != 1 else ''} movida{'s' if moved_count != 1 else ''} a la estructura ordenada.",
        "moved_count": moved_count,
        "updated_database_images": len(affected_images),
        "updated_database_nodes": len(affected_nodes),
        "destination_path": destination_rel,
        "tree": tree,
        "total_images": total_images,
    }


@router.post("/organizer/move")
async def move_images_with_organizer(
    request: OrganizerMoveRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mueve atómicamente una selección a una subcarpeta ordenada.

    Las imágenes reciben el nombre de la carpeta de destino y un correlativo de
    al menos dos dígitos. La miniatura se mueve junto a su imagen o se regenera.
    """
    root = await _get_organizer_root(db, create=True)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configura primero la carpeta ordenada en Settings.",
        )
    configuration_error = await _organizer_configuration_error(db, root)
    if configuration_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=configuration_error)

    try:
        destination = _organizer_child_path(root, request.destination_path, allow_empty=False)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Destino no válido.")
    if not destination.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La carpeta destino no existe.")

    unique_ids = list(dict.fromkeys(request.image_ids))
    result = await db.execute(select(Image).where(Image.id.in_(unique_ids)))
    images_by_id = {image.id: image for image in result.scalars().all()}
    missing_ids = [image_id for image_id in unique_ids if image_id not in images_by_id]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontraron las imágenes: {missing_ids}",
        )

    folder_ids = {image.folder_id for image in images_by_id.values()}
    folder_result = await db.execute(select(Folder).where(Folder.id.in_(folder_ids)))
    source_folders = {folder.id: folder for folder in folder_result.scalars().all()}
    if len(source_folders) != len(folder_ids):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Falta una carpeta de origen.")

    prefix = _organizer_prefix(destination.name)
    number_pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$", re.IGNORECASE)
    max_number = 0
    for item in destination.iterdir():
        if not item.is_file() or item.suffix.lower() not in ORGANIZER_IMAGE_EXTENSIONS:
            continue
        match = number_pattern.match(item.stem)
        if match:
            max_number = max(max_number, int(match.group(1)))

    ordered_images = [images_by_id[image_id] for image_id in unique_ids]
    prepared: list[dict[str, Any]] = []
    skipped_ids: list[int] = []
    next_number = max_number + 1
    width = max(2, len(str(max_number + len(ordered_images))))
    thumb_dir = destination / "thumb"
    await asyncio.to_thread(thumb_dir.mkdir, parents=True, exist_ok=True)

    for image in ordered_images:
        source_folder = source_folders[image.folder_id]
        source_root = Path(source_folder.path).resolve()
        source_file = (source_root / str(image.path)).resolve()
        if source_file.parent == destination:
            skipped_ids.append(image.id)
            continue
        if source_root != source_file and source_root not in source_file.parents:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ruta insegura para imagen {image.id}.")
        if not source_file.is_file():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No existe el archivo de la imagen {image.id}: {image.path}",
            )

        while True:
            filename = f"{prefix}_{next_number:0{width}d}{source_file.suffix.lower()}"
            destination_file = destination / filename
            if not destination_file.exists():
                break
            next_number += 1

        source_thumb: Path | None = None
        if image.thumb_path:
            raw_thumb = Path(str(image.thumb_path))
            source_thumb = raw_thumb.resolve() if raw_thumb.is_absolute() else (source_root / raw_thumb).resolve()
            if source_thumb != source_root and source_root not in source_thumb.parents:
                source_thumb = None

        destination_thumb = thumb_dir / f"{destination_file.stem}.jpg"
        if destination_thumb.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe la miniatura destino {destination_thumb.name}.",
            )
        prepared.append(
            {
                "image": image,
                "source_folder_id": image.folder_id,
                "source_node_id": image.folder_node_id,
                "source_parent": source_file.parent,
                "source_file": source_file,
                "destination_file": destination_file,
                "source_thumb": source_thumb if source_thumb and source_thumb.is_file() else None,
                "destination_thumb": destination_thumb,
            }
        )
        next_number += 1

    if not prepared:
        tree, total_images = await asyncio.to_thread(_organizer_tree, root)
        return {
            "message": "Las imágenes seleccionadas ya estaban en la carpeta destino.",
            "moved_count": 0,
            "skipped_count": len(skipped_ids),
            "destination_path": _organizer_rel(root, destination),
            "tree": tree,
            "total_images": total_images,
        }

    destination_folder = await _ensure_organizer_folder_record(db, root)
    service = GalleryService(db)
    node_cache = await service._load_folder_nodes_cache(destination_folder.id)
    destination_rel = _organizer_rel(root, destination)
    destination_node = await service._ensure_folder_node_for_relative_path(
        folder_id=destination_folder.id,
        folder_name=destination_folder.name,
        relative_path=f"{destination_rel}/__mnemos_placeholder__.png",
        node_cache=node_cache,
    )

    image_moves: list[tuple[Path, Path]] = []
    thumb_moves: list[tuple[Path, Path]] = []
    generated_thumbs: list[Path] = []
    try:
        for entry in prepared:
            source_file = entry["source_file"]
            destination_file = entry["destination_file"]
            await asyncio.to_thread(shutil.move, str(source_file), str(destination_file))
            image_moves.append((source_file, destination_file))

            source_thumb = entry["source_thumb"]
            destination_thumb = entry["destination_thumb"]
            if source_thumb:
                await asyncio.to_thread(shutil.move, str(source_thumb), str(destination_thumb))
                thumb_moves.append((source_thumb, destination_thumb))
            else:
                generated = await asyncio.to_thread(service._generate_thumbnail, destination_file)
                if not generated or not destination_thumb.is_file():
                    raise RuntimeError(f"No se pudo crear la miniatura de {destination_file.name}")
                generated_thumbs.append(destination_thumb)

            image = entry["image"]
            image.folder_id = destination_folder.id
            image.folder_node_id = destination_node.id
            image.path = _organizer_rel(root, destination_file)
            image.thumb_path = _organizer_rel(root, destination_thumb)

        await db.commit()
    except Exception as exc:
        await db.rollback()
        for generated_thumb in reversed(generated_thumbs):
            if generated_thumb.exists():
                try:
                    generated_thumb.unlink()
                except OSError:
                    logger.error("organizer_generated_thumb_rollback_failed", exc_info=True)
        for source_thumb, destination_thumb in reversed(thumb_moves):
            if destination_thumb.exists() and not source_thumb.exists():
                try:
                    source_thumb.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination_thumb), str(source_thumb))
                except OSError:
                    logger.error("organizer_thumb_rollback_failed", exc_info=True)
        for source_file, destination_file in reversed(image_moves):
            if destination_file.exists() and not source_file.exists():
                try:
                    source_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination_file), str(source_file))
                except OSError:
                    logger.error("organizer_image_rollback_failed", exc_info=True)
        logger.error("organizer_move_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo completar el movimiento; se revirtieron los cambios: {exc}",
        )

    for entry in prepared:
        source_thumb = entry["source_thumb"]
        if source_thumb and source_thumb.parent.name.lower() == "thumb":
            try:
                if source_thumb.parent.is_dir() and not any(source_thumb.parent.iterdir()):
                    source_thumb.parent.rmdir()
            except OSError:
                pass

    # Si las carpetas que contenían las imágenes quedaron sin originales,
    # eliminar sus miniaturas residuales, directorio y nodos del árbol.
    cleanup_candidates: dict[tuple[str, int], Path] = {}
    for entry in prepared:
        source_folder_id = str(entry["source_folder_id"])
        source_node_id = entry["source_node_id"]
        if source_folder_id == destination_folder.id or source_node_id is None:
            continue
        cleanup_candidates[(source_folder_id, int(source_node_id))] = entry["source_parent"]

    removed_source_folders: list[str] = []
    for (source_folder_id, source_node_id), source_directory in sorted(
        cleanup_candidates.items(),
        key=lambda item: len(item[1].parts),
        reverse=True,
    ):
        if not source_directory.is_dir():
            continue
        try:
            await asyncio.to_thread(_validate_thumbnail_only_source_folder, source_directory)
        except (ValueError, OSError):
            continue

        node_result = await db.execute(
            select(FolderNode).where(
                FolderNode.id == source_node_id,
                FolderNode.folder_root_id == source_folder_id,
            )
        )
        source_node = node_result.scalar_one_or_none()
        if not source_node:
            continue
        source_rel = str(source_node.rel_path).replace("\\", "/").strip("/")
        is_source_root = not source_rel
        nodes_result = await db.execute(
            select(FolderNode.id, FolderNode.rel_path).where(
                FolderNode.folder_root_id == source_folder_id
            )
        )
        subtree_ids = [
            int(row.id)
            for row in nodes_result.fetchall()
            if is_source_root
            or str(row.rel_path).replace("\\", "/").strip("/") == source_rel
            or str(row.rel_path).replace("\\", "/").strip("/").startswith(f"{source_rel}/")
        ]
        try:
            await db.execute(
                delete(Image).where(
                    Image.folder_id == source_folder_id,
                    Image.folder_node_id.in_(subtree_ids),
                )
            )
            await db.execute(
                delete(FolderNode).where(
                    FolderNode.folder_root_id == source_folder_id,
                    FolderNode.id.in_(subtree_ids),
                )
            )
            if is_source_root:
                await db.execute(delete(Folder).where(Folder.id == source_folder_id))
            await asyncio.to_thread(shutil.rmtree, source_directory)
            await db.commit()
            removed_source_folders.append(str(source_directory))
        except Exception:
            await db.rollback()
            logger.warning(
                "organizer_empty_source_folder_cleanup_failed path=%s",
                source_directory,
                exc_info=True,
            )

    tree, total_images = await asyncio.to_thread(_organizer_tree, root)
    moved_count = len(prepared)
    return {
        "message": (
            f"{moved_count} imagen{'es' if moved_count != 1 else ''} organizada{'s' if moved_count != 1 else ''}."
            + (
                f" {len(removed_source_folders)} carpeta{'s' if len(removed_source_folders) != 1 else ''} de origen vacía{'s' if len(removed_source_folders) != 1 else ''} eliminada{'s' if len(removed_source_folders) != 1 else ''}."
                if removed_source_folders
                else ""
            )
        ),
        "moved_count": moved_count,
        "skipped_count": len(skipped_ids),
        "removed_source_folders": removed_source_folders,
        "destination_path": destination_rel,
        "tree": tree,
        "total_images": total_images,
    }


@router.get("/sorted-folders", response_model=List[str])
async def list_sorted_folders(db: AsyncSession = Depends(get_db)):
    """
    Lista las carpetas dentro de la ruta IMG_SORTED_PATH
    """
    try:
        # Obtener la ruta de imágenes ordenadas
        sorted_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.IMG_SORTED_PATH)
        )
        sorted_setting = sorted_result.scalar_one_or_none()
        
        if not sorted_setting or not sorted_setting.value:
            return []
        
        sorted_path = Path(sorted_setting.value)
        
        if not sorted_path.exists():
            return []
        
        # Listar carpetas (solo directorios, no archivos)
        folders = []
        for item in sorted_path.iterdir():
            if item.is_dir():
                folders.append(item.name)
        
        return sorted(folders)
    except Exception as e:
        logger.error(f"Error listando carpetas ordenadas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar carpetas: {str(e)}"
        )


@router.post("/images/move-to-sorted-folder")
async def move_images_to_sorted_folder(
    request: MoveImagesRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Mueve imágenes a una carpeta dentro de IMG_SORTED_PATH.
    Renombra las imágenes con el nombre de la carpeta + número secuencial.
    Crea la carpeta si no existe y la registra en la DB.
    """
    try:
        # Obtener la ruta de imágenes ordenadas
        sorted_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.IMG_SORTED_PATH)
        )
        sorted_setting = sorted_result.scalar_one_or_none()
        
        if not sorted_setting or not sorted_setting.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ruta de imágenes ordenadas no configurada. Configúrala en Settings."
            )
        
        sorted_path = Path(sorted_setting.value).resolve()
        folder_path = (sorted_path / request.folder_name).resolve()
        
        # Crear carpeta si no existe
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # Verificar si la carpeta ya está registrada en la DB
        # Usar la ruta resuelta y normalizada para el ID
        folder_id = md5(str(folder_path).encode()).hexdigest()
        folder_result = await db.execute(
            select(Folder).where(Folder.id == folder_id)
        )
        folder = folder_result.scalar_one_or_none()
        
        # Si no existe, crear el registro
        if not folder:
            folder = Folder(
                id=folder_id,
                path=str(folder_path),  # Guardar ruta absoluta resuelta
                name=request.folder_name,
                enabled=True
            )
            db.add(folder)
            await db.flush()
            logger.info(f"Carpeta registrada en DB: {request.folder_name} (path: {folder_path})")
        
        # Obtener todas las imágenes que se van a mover
        images_result = await db.execute(
            select(Image).where(Image.id.in_(request.image_ids))
        )
        images = images_result.scalars().all()
        
        logger.info(f"[MOVE] Intentando mover {len(images)} imágenes a carpeta '{request.folder_name}' (folder_id: {folder_id})")
        logger.info(f"[MOVE] IDs de imágenes solicitadas: {request.image_ids}")
        logger.info(f"[MOVE] IDs de imágenes encontradas: {[img.id for img in images]}")
        
        if len(images) != len(request.image_ids):
            missing_ids = set(request.image_ids) - {img.id for img in images}
            logger.warning(f"[MOVE] Algunas imágenes no fueron encontradas: {missing_ids}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Algunas imágenes no fueron encontradas: {missing_ids}"
            )
        
        # Obtener el último número de imagen en la carpeta destino
        # Revisar tanto imágenes en BD como archivos físicos en la carpeta
        max_number = 0
        
        # 1. Revisar imágenes en la BD
        existing_images_result = await db.execute(
            select(Image).where(Image.folder_id == folder_id)
        )
        existing_images = existing_images_result.scalars().all()
        
        logger.info(f"[MOVE] Revisando {len(existing_images)} imágenes existentes en BD para carpeta '{request.folder_name}'")
        
        for img in existing_images:
            # El nombre debería ser: folder_name_N.ext
            # Intentar extraer el número del final del nombre
            stem = Path(img.path).stem
            # Buscar el patrón: folder_name_N donde N es un número
            # El nombre puede ser: "Selene_8" o "Selene_123"
            if stem.startswith(request.folder_name + '_'):
                # Extraer la parte después del guion bajo
                number_part = stem[len(request.folder_name) + 1:]
                try:
                    num = int(number_part)
                    max_number = max(max_number, num)
                    logger.debug(f"[MOVE] Imagen en BD: {img.path} -> número: {num}")
                except ValueError:
                    logger.debug(f"[MOVE] No se pudo extraer número de: {img.path}")
                    pass
        
        # 2. Revisar archivos físicos en la carpeta destino (por si hay archivos que no están en BD)
        if folder_path.exists() and folder_path.is_dir():
            logger.info(f"[MOVE] Revisando archivos físicos en carpeta destino: {folder_path}")
            for file_path in folder_path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif'}:
                    stem = file_path.stem
                    # Buscar el patrón: folder_name_N
                    if stem.startswith(request.folder_name + '_'):
                        number_part = stem[len(request.folder_name) + 1:]
                        try:
                            num = int(number_part)
                            max_number = max(max_number, num)
                            logger.debug(f"[MOVE] Archivo físico: {file_path.name} -> número: {num}")
                        except ValueError:
                            logger.debug(f"[MOVE] No se pudo extraer número de archivo físico: {file_path.name}")
                            pass
        
        logger.info(f"[MOVE] Número máximo encontrado en carpeta destino: {max_number}. Las nuevas imágenes empezarán desde: {max_number + 1}")
        
        # Mover y renombrar cada imagen
        moved_count = 0
        skipped_count = 0  # Imágenes que ya están en la carpeta destino
        errors = []
        # Rastrear carpetas de origen para verificar si quedan vacías
        source_folders = {}  # {folder_id: Folder}
        # Contador para asignar números secuenciales (solo se incrementa cuando se mueve una imagen)
        number_counter = 0
        
        for image in images:
            try:
                # Verificar si la imagen ya está en la carpeta destino
                if image.folder_id == folder_id:
                    logger.info(f"Imagen {image.id} ya está en la carpeta destino {request.folder_name}, saltando...")
                    skipped_count += 1
                    continue
                
                # Guardar folder_id original antes de modificarlo
                original_folder_id = image.folder_id
                
                # Obtener la carpeta original
                original_folder_result = await db.execute(
                    select(Folder).where(Folder.id == original_folder_id)
                )
                original_folder = original_folder_result.scalar_one_or_none()
                
                if not original_folder:
                    error_msg = f"Imagen {image.id}: Carpeta original no encontrada (folder_id: {original_folder_id})"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    continue
                
                # Guardar referencia a la carpeta de origen para verificación posterior
                if original_folder_id not in source_folders:
                    source_folders[original_folder_id] = original_folder
                
                # Construir rutas (resolver para evitar problemas con rutas relativas/absolutas)
                original_file_path = Path(original_folder.path).resolve() / image.path
                original_file_path = original_file_path.resolve()
                
                if not original_file_path.exists():
                    errors.append(f"Imagen {image.id}: Archivo no encontrado: {original_file_path}")
                    logger.error(f"Archivo no encontrado: {original_file_path} (folder.path={original_folder.path}, image.path={image.path})")
                    continue
                
                # Verificar que el archivo original existe y es un archivo
                if not original_file_path.is_file():
                    errors.append(f"Imagen {image.id}: La ruta no es un archivo: {original_file_path}")
                    logger.error(f"La ruta no es un archivo: {original_file_path}")
                    continue
                
                # Determinar extensión
                extension = original_file_path.suffix
                
                # Nuevo nombre: folder_name_N.ext
                # Usar number_counter para asegurar números secuenciales sin gaps
                # Buscar el siguiente número disponible
                attempt_number = number_counter
                new_number = None
                new_filename = None
                new_file_path = None
                
                while True:
                    new_number = max_number + attempt_number + 1
                    new_filename = f"{request.folder_name}_{new_number}{extension}"
                    new_file_path = folder_path.resolve() / new_filename
                    
                    # Si el archivo no existe, usar este número
                    if not new_file_path.exists():
                        break
                    
                    # Si existe, intentar con el siguiente número
                    logger.warning(f"El archivo destino ya existe: {new_file_path}, intentando siguiente número...")
                    attempt_number += 1
                
                logger.info(f"[MOVE] Asignando número {new_number} a imagen {image.id} (archivo: {new_filename})")
                
                # Mover archivo físico
                logger.info(f"Moviendo imagen {image.id}: {original_file_path} -> {new_file_path}")
                
                # Verificar tamaño del archivo original para comparar después
                original_size = original_file_path.stat().st_size
                
                try:
                    # Intentar mover el archivo
                    # En Windows, a veces shutil.move crea un .bak si el archivo está en uso
                    # Intentamos primero con move, y si falla, intentamos copy + delete
                    try:
                        shutil.move(str(original_file_path), str(new_file_path))
                    except (OSError, PermissionError) as move_error:
                        # Si falla por permisos o archivo en uso, intentar copiar y luego eliminar
                        logger.warning(f"Error al mover directamente, intentando copiar: {move_error}")
                        shutil.copy2(str(original_file_path), str(new_file_path))
                        # Verificar que la copia fue exitosa antes de eliminar
                        if new_file_path.exists() and new_file_path.stat().st_size == original_size:
                            original_file_path.unlink()
                            logger.info(f"Archivo copiado y original eliminado: {original_file_path}")
                        else:
                            raise Exception("La copia no coincide con el original")
                except Exception as move_error:
                    error_msg = f"Error al mover archivo: {move_error}"
                    logger.error(f"Error moviendo archivo {original_file_path}: {move_error}", exc_info=True)
                    errors.append(f"Imagen {image.id}: {error_msg}")
                    continue
                
                # Verificar que el archivo se movió correctamente
                if not new_file_path.exists():
                    error_msg = f"El archivo no existe después de mover: {new_file_path}"
                    logger.error(error_msg)
                    errors.append(f"Imagen {image.id}: {error_msg}")
                    continue
                
                # Verificar que el tamaño del archivo movido es correcto
                new_size = new_file_path.stat().st_size
                if new_size != original_size:
                    error_msg = f"El tamaño del archivo movido no coincide: original={original_size}, nuevo={new_size}"
                    logger.error(error_msg)
                    errors.append(f"Imagen {image.id}: {error_msg}")
                    continue
                
                # Verificar que el archivo original ya no existe
                if original_file_path.exists():
                    error_msg = f"El archivo original todavía existe después de mover: {original_file_path}"
                    logger.warning(error_msg)
                    # Intentar eliminar el archivo original si todavía existe
                    try:
                        # Verificar que el archivo en el destino es el mismo (mismo tamaño)
                        if new_file_path.exists() and new_file_path.stat().st_size == original_size:
                            original_file_path.unlink()
                            logger.info(f"Archivo original eliminado manualmente: {original_file_path}")
                        else:
                            # Si los tamaños no coinciden, no eliminar (podría ser una copia)
                            logger.error(f"No se elimina el archivo original porque los tamaños no coinciden")
                            errors.append(f"Imagen {image.id}: {error_msg}")
                            continue
                    except Exception as delete_error:
                        logger.error(f"No se pudo eliminar el archivo original: {delete_error}")
                        errors.append(f"Imagen {image.id}: {error_msg}")
                        continue
                
                logger.info(f"Archivo movido exitosamente: {new_file_path}")
                
                # Limpiar archivos .bak si existen (Windows a veces los crea)
                bak_file = original_file_path.with_suffix(original_file_path.suffix + '.bak')
                if bak_file.exists():
                    try:
                        bak_file.unlink()
                        logger.info(f"Archivo .bak eliminado: {bak_file}")
                    except Exception as e:
                        logger.warning(f"No se pudo eliminar archivo .bak: {e}")
                
                # Mover thumbnail si existe (nueva ubicación: thumb/ relativa)
                old_thumb_path = None
                new_thumb_path = None
                thumbnail_moved = False
                
                if image.thumb_path:
                    # Construir ruta del thumbnail antiguo
                    if Path(image.thumb_path).is_absolute():
                        # Ruta absoluta (formato antiguo)
                        old_thumb_path = Path(image.thumb_path)
                    else:
                        # Ruta relativa (formato nuevo: thumb/nombre.jpg)
                        old_thumb_path = Path(original_folder.path) / image.thumb_path
                    
                    # Mover thumbnail a nueva ubicación
                    if old_thumb_path and old_thumb_path.exists():
                        new_thumb_dir = new_file_path.parent / "thumb"
                        new_thumb_dir.mkdir(exist_ok=True)
                        new_thumb_path_file = new_thumb_dir / f"{new_file_path.stem}.jpg"
                        
                        try:
                            # Si el thumbnail destino ya existe, eliminarlo primero
                            if new_thumb_path_file.exists():
                                new_thumb_path_file.unlink()
                            
                            shutil.move(str(old_thumb_path), str(new_thumb_path_file))
                            new_thumb_path = f"thumb/{new_file_path.stem}.jpg"
                            thumbnail_moved = True
                            logger.info(f"Thumbnail movido: {old_thumb_path} -> {new_thumb_path_file}")
                            
                            # Limpiar carpeta thumb/ de origen si está vacía
                            old_thumb_dir = old_thumb_path.parent
                            if old_thumb_dir.name == "thumb" and old_thumb_dir.exists():
                                try:
                                    # Verificar si la carpeta thumb está vacía
                                    if not any(old_thumb_dir.iterdir()):
                                        old_thumb_dir.rmdir()
                                        logger.info(f"Carpeta thumb vacía eliminada: {old_thumb_dir}")
                                except Exception as e:
                                    logger.debug(f"No se pudo eliminar carpeta thumb vacía: {e}")
                        except Exception as e:
                            logger.warning(f"Error moviendo thumbnail: {e}, se regenerará")
                            old_thumb_path = None
                
                # Regenerar thumbnail si no se pudo mover o no existe
                if not new_thumb_path or not (new_file_path.parent / "thumb" / f"{new_file_path.stem}.jpg").exists():
                    from .service import GalleryService
                    service = GalleryService(db)
                    generated_thumb = service._generate_thumbnail(new_file_path)
                    if generated_thumb:
                        new_thumb_path = generated_thumb
                        logger.info(f"Thumbnail generado: {new_thumb_path}")
                    else:
                        logger.warning(f"No se pudo generar thumbnail para {new_file_path}")
                        new_thumb_path = None
                
                # Actualizar imagen en DB - CRÍTICO: Actualizar folder_id y path
                image.folder_id = folder_id
                image.path = new_filename  # Solo el nombre del archivo, no la ruta completa
                image.thumb_path = new_thumb_path
                
                # Hacer flush después de cada actualización para asegurar que se guarda
                await db.flush()
                
                # Verificar que los cambios se aplicaron
                await db.refresh(image)
                
                # Verificación adicional: confirmar que los valores se guardaron correctamente
                if image.folder_id != folder_id:
                    logger.error(f"ERROR: folder_id no se actualizó correctamente. Esperado: {folder_id}, Actual: {image.folder_id}")
                    raise Exception(f"Error al actualizar folder_id para imagen {image.id}")
                
                if image.path != new_filename:
                    logger.error(f"ERROR: path no se actualizó correctamente. Esperado: {new_filename}, Actual: {image.path}")
                    raise Exception(f"Error al actualizar path para imagen {image.id}")
                
                logger.info(f"Imagen {image.id} actualizada correctamente en DB:")
                logger.info(f"  - folder_id: {image.folder_id} (nuevo: {folder_id})")
                logger.info(f"  - path: {image.path} (nuevo: {new_filename})")
                logger.info(f"  - thumb_path: {image.thumb_path}")
                
                moved_count += 1
                # Actualizar number_counter al número usado (para que el siguiente empiece desde ahí)
                # attempt_number es el offset desde max_number, así que el siguiente será attempt_number + 1
                number_counter = attempt_number + 1
                
            except Exception as e:
                logger.error(f"Error moviendo imagen {image.id}: {e}", exc_info=True)
                errors.append(f"Imagen {image.id}: {str(e)}")
        
        await db.commit()
        
        # ====================================================================
        # POST-PROCESAMIENTO: Verificar carpetas de origen y reindexar
        # ====================================================================
        logger.info(f"[MOVE] Iniciando post-procesamiento: {len(source_folders)} carpetas de origen a verificar")
        
        # Crear servicio para reindexación
        from .service import GalleryService
        service = GalleryService(db)
        
        folders_to_reindex = []  # Carpetas que necesitan reindexación
        folders_to_delete = []  # Carpetas que deben eliminarse
        
        # Verificar cada carpeta de origen
        for source_folder_id, source_folder in source_folders.items():
            try:
                # Verificar si quedan imágenes en la BD para esta carpeta
                remaining_images_result = await db.execute(
                    select(Image).where(Image.folder_id == source_folder_id)
                )
                remaining_images = remaining_images_result.scalars().all()
                
                # Verificar si la carpeta física tiene archivos (excluyendo thumb/)
                source_folder_path = Path(source_folder.path)
                has_files = False
                
                if source_folder_path.exists() and source_folder_path.is_dir():
                    # Verificar si hay archivos (excluyendo thumb/)
                    for item in source_folder_path.iterdir():
                        if item.is_file():
                            has_files = True
                            break
                        elif item.is_dir() and item.name != "thumb":
                            # Verificar si hay archivos en subdirectorios (excepto thumb/)
                            for subitem in item.rglob('*'):
                                if subitem.is_file() and "thumb" not in subitem.parts:
                                    has_files = True
                                    break
                            if has_files:
                                break
                
                # Si no hay imágenes en BD ni archivos físicos, marcar para eliminar
                if len(remaining_images) == 0 and not has_files:
                    logger.info(f"[MOVE] Carpeta de origen vacía detectada: {source_folder.name} (ID: {source_folder_id})")
                    folders_to_delete.append(source_folder)
                elif len(remaining_images) > 0:
                    # Si aún tiene imágenes, necesita reindexación
                    logger.info(f"[MOVE] Carpeta de origen aún tiene {len(remaining_images)} imágenes: {source_folder.name}")
                    folders_to_reindex.append(source_folder_id)
                else:
                    logger.info(f"[MOVE] Carpeta de origen sin imágenes en BD pero con archivos físicos: {source_folder.name}")
                    # Si tiene archivos pero no en BD, también necesita reindexación
                    folders_to_reindex.append(source_folder_id)
                    
            except Exception as e:
                logger.error(f"[MOVE] Error verificando carpeta de origen {source_folder.name}: {e}", exc_info=True)
                # En caso de error, intentar reindexar por seguridad
                folders_to_reindex.append(source_folder_id)
        
        # Eliminar carpetas vacías
        for folder_to_delete in folders_to_delete:
            try:
                folder_path = Path(folder_to_delete.path)
                
                # Eliminar carpeta thumb/ si existe y está vacía
                thumb_dir = folder_path / "thumb"
                if thumb_dir.exists() and thumb_dir.is_dir():
                    try:
                        # Verificar si está vacía
                        if not any(thumb_dir.iterdir()):
                            thumb_dir.rmdir()
                            logger.info(f"[MOVE] Carpeta thumb/ eliminada: {thumb_dir}")
                    except Exception as e:
                        logger.warning(f"[MOVE] No se pudo eliminar carpeta thumb/: {e}")
                
                # Eliminar carpeta física si está vacía
                if folder_path.exists() and folder_path.is_dir():
                    try:
                        # Verificar que esté realmente vacía (sin archivos ni subdirectorios excepto thumb/)
                        has_any_content = False
                        for item in folder_path.iterdir():
                            if item.name != "thumb":
                                has_any_content = True
                                break
                        
                        if not has_any_content:
                            folder_path.rmdir()
                            logger.info(f"[MOVE] Carpeta física eliminada: {folder_path}")
                    except Exception as e:
                        logger.warning(f"[MOVE] No se pudo eliminar carpeta física: {e}")
                
                # Eliminar imágenes asociadas si quedan (por seguridad)
                from sqlalchemy import delete
                await db.execute(delete(Image).where(Image.folder_id == folder_to_delete.id))
                
                # Eliminar registro de la BD
                await db.delete(folder_to_delete)
                await db.commit()
                logger.info(f"[MOVE] Carpeta eliminada del sistema: {folder_to_delete.name} (ID: {folder_to_delete.id})")
                
            except Exception as e:
                logger.error(f"[MOVE] Error eliminando carpeta {folder_to_delete.name}: {e}", exc_info=True)
                await db.rollback()
        
        # Reindexar carpetas de origen que aún tienen imágenes
        for folder_id_to_reindex in folders_to_reindex:
            try:
                logger.info(f"[MOVE] Reindexando carpeta de origen: {folder_id_to_reindex}")
                await service.scan_folder(
                    folder_id=folder_id_to_reindex,
                    recursive=True,
                    create_records=True
                )
                logger.info(f"[MOVE] Carpeta de origen reindexada exitosamente: {folder_id_to_reindex}")
            except Exception as e:
                logger.error(f"[MOVE] Error reindexando carpeta de origen {folder_id_to_reindex}: {e}", exc_info=True)
                errors.append(f"Error reindexando carpeta de origen: {str(e)}")
        
        # Reindexar carpeta de destino
        try:
            logger.info(f"[MOVE] Reindexando carpeta de destino: {folder_id} ({request.folder_name})")
            await service.scan_folder(
                folder_id=folder_id,
                recursive=True,
                create_records=True
            )
            logger.info(f"[MOVE] Carpeta de destino reindexada exitosamente: {folder_id}")
        except Exception as e:
            logger.error(f"[MOVE] Error reindexando carpeta de destino {folder_id}: {e}", exc_info=True)
            errors.append(f"Error reindexando carpeta de destino: {str(e)}")
        
        logger.info(f"[MOVE] Post-procesamiento completado: {len(folders_to_delete)} carpetas eliminadas, {len(folders_to_reindex)} carpetas reindexadas")
        
        # Construir mensaje informativo
        message_parts = []
        if moved_count > 0:
            message_parts.append(f"{moved_count} imagen{'es' if moved_count != 1 else ''} movida{'s' if moved_count != 1 else ''} exitosamente")
        if skipped_count > 0:
            message_parts.append(f"{skipped_count} imagen{'es' if skipped_count != 1 else ''} ya {'estaban' if skipped_count != 1 else 'estaba'} en la carpeta destino")
        if len(errors) > 0:
            message_parts.append(f"{len(errors)} error{'es' if len(errors) != 1 else ''}")
        
        message = ". ".join(message_parts) if message_parts else "No se movieron imágenes"
        
        return {
            "message": message,
            "moved_count": moved_count,
            "skipped_count": skipped_count,
            "folder_id": folder_id,
            "folder_name": request.folder_name,
            "errors": errors,
            "folders_deleted": len(folders_to_delete),
            "folders_reindexed": len(folders_to_reindex) + 1  # +1 por la carpeta de destino
        }
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error moviendo imágenes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al mover imágenes: {str(e)}"
        )

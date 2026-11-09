"""
Utilidades para manejo de GUIDs de imágenes

Este módulo proporciona funciones helper para generar y validar GUIDs
que se almacenan en los metadatos PNG de las imágenes.
"""

import uuid
import hashlib
import logging
from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .models import Image

logger = logging.getLogger(__name__)


def generate_image_guid() -> str:
    """
    Genera un GUID único para una imagen
    
    Returns:
        String UUID v4 (ej: "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


def generate_content_hash_guid(file_path: Path) -> str:
    """
    Genera un GUID basado en el hash del contenido del archivo.
    Este es un identificador persistente que no depende de metadatos externos.
    
    Hashea TODO el contenido del archivo para garantizar unicidad.
    Para archivos grandes puede ser lento, pero es necesario para evitar colisiones.
    
    Args:
        file_path: Ruta del archivo de imagen
        
    Returns:
        String con formato UUID (basado en hash SHA256 del contenido)
    """
    try:
        # Verificar que el archivo existe
        if not file_path.exists():
            logger.error(f"[GUID] El archivo no existe: {file_path}")
            raise FileNotFoundError(f"El archivo no existe: {file_path}")
        
        if not file_path.is_file():
            logger.error(f"[GUID] La ruta no es un archivo: {file_path}")
            raise ValueError(f"La ruta no es un archivo: {file_path}")
        
        file_size = file_path.stat().st_size
        logger.debug(f"[GUID] Calculando hash SHA256 completo para: {file_path.name} (tamaño: {file_size} bytes)")
        
        # Calcular hash SHA256 del contenido completo
        sha256_hash = hashlib.sha256()
        
        # Leer el archivo en chunks para manejar archivos grandes eficientemente
        bytes_read = 0
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)  # 64KB chunks para mejor rendimiento
                if not chunk:
                    break
                sha256_hash.update(chunk)
                bytes_read += len(chunk)
                # Log de progreso cada 10MB para archivos muy grandes
                if bytes_read % (10 * 1024 * 1024) == 0:
                    logger.debug(f"[GUID] Procesando hash... {bytes_read} bytes leídos de {file_size}")
        
        hash_hex = sha256_hash.hexdigest()
        
        # Convertir el hash a formato UUID (32 caracteres hex)
        # Formato: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        uuid_str = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
        
        logger.debug(f"[GUID] Hash generado para {file_path.name}: {uuid_str[:8]}... (tamaño procesado: {bytes_read} bytes)")
        return uuid_str
        
    except Exception as e:
        logger.error(f"[GUID] Error generando hash del contenido para {file_path}: {e}", exc_info=True)
        # No usar fallback, lanzar el error para que se capture arriba
        raise


async def ensure_guid_unique(
    db: AsyncSession,
    guid: str,
    max_attempts: int = 10
) -> str:
    """
    Verifica que un GUID sea único en la base de datos.
    Si no lo es, genera uno nuevo hasta encontrar uno único.
    
    Args:
        db: Sesión de base de datos
        guid: GUID a verificar
        max_attempts: Número máximo de intentos antes de lanzar error
        
    Returns:
        GUID único garantizado
        
    Raises:
        RuntimeError: Si no se puede generar un GUID único después de max_attempts
    """
    attempt = 0
    
    while attempt < max_attempts:
        # Verificar si el GUID ya existe
        result = await db.execute(
            select(Image).where(Image.guid == guid)
        )
        existing = result.scalar_one_or_none()
        
        if existing is None:
            # GUID es único
            return guid
        
        # GUID ya existe, generar uno nuevo
        logger.warning(f"GUID {guid[:8]}... ya existe, generando uno nuevo (intento {attempt + 1}/{max_attempts})")
        guid = generate_image_guid()
        attempt += 1
    
    # Si llegamos aquí, no pudimos generar un GUID único
    raise RuntimeError(
        f"No se pudo generar un GUID único después de {max_attempts} intentos. "
        "Esto es extremadamente improbable con UUID v4."
    )


async def get_or_generate_guid(
    db: AsyncSession,
    file_path: Optional[str] = None,
    existing_guid: Optional[str] = None
) -> str:
    """
    Obtiene un GUID existente o genera uno nuevo.
    
    Prioridad:
    1. Si se proporciona existing_guid y es válido, usarlo
    2. Si se proporciona file_path, intentar leer del PNG
    3. Generar uno nuevo
    
    Args:
        db: Sesión de base de datos
        file_path: Ruta del archivo PNG (opcional)
        existing_guid: GUID existente (opcional)
        
    Returns:
        GUID único garantizado
    """
    # Si tenemos un GUID existente, verificar que sea único
    if existing_guid:
        try:
            return await ensure_guid_unique(db, existing_guid)
        except RuntimeError:
            # Si falla, generar uno nuevo
            logger.warning(f"GUID existente {existing_guid[:8]}... no es único, generando uno nuevo")
    
    # Si tenemos un archivo, intentar leer el GUID del PNG
    if file_path:
        try:
            from pathlib import Path
            from .png_writer import PNGMetadataWriter
            
            png_path = Path(file_path)
            if png_path.exists() and png_path.suffix.lower() == '.png':
                png_writer = PNGMetadataWriter()
                guid_from_file = png_writer.read_guid(png_path)
                
                if guid_from_file:
                    # Verificar que sea único
                    try:
                        return await ensure_guid_unique(db, guid_from_file)
                    except RuntimeError:
                        logger.warning(f"GUID del archivo {guid_from_file[:8]}... no es único, generando uno nuevo")
        except Exception as e:
            logger.debug(f"Error leyendo GUID del archivo {file_path}: {e}")
    
    # Generar un nuevo GUID
    new_guid = generate_image_guid()
    return await ensure_guid_unique(db, new_guid)


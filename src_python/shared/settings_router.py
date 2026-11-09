"""
Router - Endpoints API para Settings
Rutas: /api/settings/*
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from .database import get_db
from .models import Setting, SettingKeys

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingResponse(BaseModel):
    """Response model para un setting"""
    key: str
    value: str | None
    description: str | None
    
    model_config = ConfigDict(from_attributes=True)


class SettingUpdate(BaseModel):
    """Request model para actualizar un setting"""
    value: str | None = Field(None, description="Valor del setting")
    description: str | None = Field(None, description="Descripción opcional")


class SettingCreate(BaseModel):
    """Request model para crear un setting"""
    key: str = Field(..., min_length=1, description="Clave única del setting")
    value: str | None = Field(None, description="Valor del setting")
    description: str | None = Field(None, description="Descripción opcional")


class DownloadPathsResponse(BaseModel):
    """Response model para las rutas de descarga"""
    loras_path: str | None
    models_path: str | None


class DownloadPathsUpdate(BaseModel):
    """Request model para actualizar rutas de descarga"""
    loras_path: str | None = Field(None, description="Ruta para descargar LoRAs")
    models_path: str | None = Field(None, description="Ruta para descargar modelos")


class ImagePathsResponse(BaseModel):
    """Response model para las rutas de imágenes"""
    trash_path: str | None
    img_sorted_path: str | None


class ImagePathsUpdate(BaseModel):
    """Request model para actualizar rutas de imágenes"""
    trash_path: str | None = Field(None, description="Ruta de la papelera de reciclaje")
    img_sorted_path: str | None = Field(None, description="Ruta para imágenes ordenadas")


class MasterImgPathResponse(BaseModel):
    """Response model para la carpeta maestra de importación IMG"""
    img_master_path: str | None


class MasterImgPathUpdate(BaseModel):
    """Request model para actualizar carpeta maestra IMG"""
    img_master_path: str | None = Field(None, description="Ruta maestra para sincronización masiva")


@router.get("", response_model=List[SettingResponse])
async def list_settings(db: AsyncSession = Depends(get_db)):
    """
    Lista todos los settings
    """
    try:
        result = await db.execute(select(Setting).order_by(Setting.key))
        settings = result.scalars().all()
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener settings: {str(e)}"
        )


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    """
    Obtiene un setting por su clave
    """
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' no encontrado"
        )
    
    return setting


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(key: str, data: SettingUpdate, db: AsyncSession = Depends(get_db)):
    """
    Actualiza o crea un setting
    """
    try:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        
        if setting:
            # Actualizar existente
            if data.value is not None:
                setting.value = data.value
            if data.description is not None:
                setting.description = data.description
        else:
            # Crear nuevo
            setting = Setting(
                key=key,
                value=data.value,
                description=data.description
            )
            db.add(setting)
        
        await db.commit()
        await db.refresh(setting)
        return setting
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar setting: {str(e)}"
        )


@router.delete("/{key}")
async def delete_setting(key: str, db: AsyncSession = Depends(get_db)):
    """
    Elimina un setting
    """
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' no encontrado"
        )
    
    await db.delete(setting)
    await db.commit()
    
    return {"message": f"Setting '{key}' eliminado", "deleted": True}


# ============================================
# Endpoints específicos para rutas de descarga
# ============================================

@router.get("/paths/download", response_model=DownloadPathsResponse)
async def get_download_paths(db: AsyncSession = Depends(get_db)):
    """
    Obtiene las rutas de descarga configuradas para LoRAs y modelos
    """
    try:
        # Obtener ambos settings
        loras_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.LORAS_DOWNLOAD_PATH)
        )
        loras_setting = loras_result.scalar_one_or_none()
        
        models_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.MODELS_DOWNLOAD_PATH)
        )
        models_setting = models_result.scalar_one_or_none()
        
        return DownloadPathsResponse(
            loras_path=loras_setting.value if loras_setting else None,
            models_path=models_setting.value if models_setting else None
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener rutas de descarga: {str(e)}"
        )


@router.put("/paths/download", response_model=DownloadPathsResponse)
async def update_download_paths(data: DownloadPathsUpdate, db: AsyncSession = Depends(get_db)):
    """
    Actualiza las rutas de descarga para LoRAs y modelos
    """
    try:
        # Actualizar ruta de LoRAs
        if data.loras_path is not None:
            loras_result = await db.execute(
                select(Setting).where(Setting.key == SettingKeys.LORAS_DOWNLOAD_PATH)
            )
            loras_setting = loras_result.scalar_one_or_none()
            
            if loras_setting:
                loras_setting.value = data.loras_path
            else:
                loras_setting = Setting(
                    key=SettingKeys.LORAS_DOWNLOAD_PATH,
                    value=data.loras_path,
                    description="Ruta donde se descargan los archivos LoRA"
                )
                db.add(loras_setting)
        
        # Actualizar ruta de modelos
        if data.models_path is not None:
            models_result = await db.execute(
                select(Setting).where(Setting.key == SettingKeys.MODELS_DOWNLOAD_PATH)
            )
            models_setting = models_result.scalar_one_or_none()
            
            if models_setting:
                models_setting.value = data.models_path
            else:
                models_setting = Setting(
                    key=SettingKeys.MODELS_DOWNLOAD_PATH,
                    value=data.models_path,
                    description="Ruta donde se descargan los archivos de modelos"
                )
                db.add(models_setting)
        
        await db.commit()
        
        # Retornar valores actuales
        return await get_download_paths(db)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar rutas de descarga: {str(e)}"
        )


# ============================================
# Endpoints específicos para rutas de imágenes
# ============================================

@router.get("/paths/images", response_model=ImagePathsResponse)
async def get_image_paths(db: AsyncSession = Depends(get_db)):
    """
    Obtiene las rutas configuradas para papelera e imágenes ordenadas
    """
    try:
        trash_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.TRASH_PATH)
        )
        trash_setting = trash_result.scalar_one_or_none()
        
        sorted_result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.IMG_SORTED_PATH)
        )
        sorted_setting = sorted_result.scalar_one_or_none()
        
        return ImagePathsResponse(
            trash_path=trash_setting.value if trash_setting else None,
            img_sorted_path=sorted_setting.value if sorted_setting else None
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener rutas de imágenes: {str(e)}"
        )


@router.put("/paths/images", response_model=ImagePathsResponse)
async def update_image_paths(data: ImagePathsUpdate, db: AsyncSession = Depends(get_db)):
    """
    Actualiza las rutas para papelera e imágenes ordenadas
    """
    try:
        # Actualizar ruta de papelera
        if data.trash_path is not None:
            trash_result = await db.execute(
                select(Setting).where(Setting.key == SettingKeys.TRASH_PATH)
            )
            trash_setting = trash_result.scalar_one_or_none()
            
            if trash_setting:
                trash_setting.value = data.trash_path
            else:
                trash_setting = Setting(
                    key=SettingKeys.TRASH_PATH,
                    value=data.trash_path,
                    description="Ruta de la papelera de reciclaje"
                )
                db.add(trash_setting)
        
        # Actualizar o desactivar la ruta de imágenes ordenadas. Es importante
        # distinguir entre un campo omitido y un null explícito: el frontend
        # envía null cuando el usuario deja la ruta vacía.
        provided_fields = getattr(data, "model_fields_set", getattr(data, "__fields_set__", set()))
        if "img_sorted_path" in provided_fields:
            sorted_result = await db.execute(
                select(Setting).where(Setting.key == SettingKeys.IMG_SORTED_PATH)
            )
            sorted_setting = sorted_result.scalar_one_or_none()

            normalized_sorted_path = (data.img_sorted_path or "").strip()
            if not normalized_sorted_path:
                if sorted_setting:
                    await db.delete(sorted_setting)
            elif sorted_setting:
                sorted_setting.value = normalized_sorted_path
            else:
                sorted_setting = Setting(
                    key=SettingKeys.IMG_SORTED_PATH,
                    value=normalized_sorted_path,
                    description="Ruta para imágenes ordenadas"
                )
                db.add(sorted_setting)
        
        await db.commit()
        
        # Retornar valores actuales
        return await get_image_paths(db)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar rutas de imágenes: {str(e)}"
        )


@router.get("/paths/master-img", response_model=MasterImgPathResponse)
async def get_master_img_path(db: AsyncSession = Depends(get_db)):
    """
    Obtiene la ruta maestra configurada para sincronización masiva de IMG
    """
    try:
        result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.IMG_MASTER_PATH)
        )
        setting = result.scalar_one_or_none()
        return MasterImgPathResponse(
            img_master_path=setting.value if setting else None
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener ruta maestra IMG: {str(e)}"
        )


@router.put("/paths/master-img", response_model=MasterImgPathResponse)
async def update_master_img_path(data: MasterImgPathUpdate, db: AsyncSession = Depends(get_db)):
    """
    Actualiza la ruta maestra para sincronización masiva de IMG
    """
    try:
        if data.img_master_path is None:
            return await get_master_img_path(db)

        result = await db.execute(
            select(Setting).where(Setting.key == SettingKeys.IMG_MASTER_PATH)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = data.img_master_path
        else:
            setting = Setting(
                key=SettingKeys.IMG_MASTER_PATH,
                value=data.img_master_path,
                description="Ruta maestra para sincronización masiva de carpetas de imágenes",
            )
            db.add(setting)

        await db.commit()
        return await get_master_img_path(db)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar ruta maestra IMG: {str(e)}"
        )


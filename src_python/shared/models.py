"""
Modelos compartidos - Settings y configuraciones globales
"""

from sqlalchemy import Column, Text, DateTime
from sqlalchemy.sql import func

from .database import Base


class Setting(Base):
    """
    Modelo para configuraciones de la aplicación (key-value store)
    Permite almacenar configuraciones de forma flexible
    """
    
    __tablename__ = "settings"
    
    key = Column(Text, primary_key=True, index=True)  # Clave única del setting
    value = Column(Text, nullable=True)  # Valor del setting (puede ser JSON stringificado)
    description = Column(Text, nullable=True)  # Descripción del setting
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Setting(key='{self.key}', value='{self.value[:50] if self.value else None}...')>"


# Constantes para las claves de settings conocidas
class SettingKeys:
    """Claves conocidas de settings para evitar errores de typo"""
    LORAS_DOWNLOAD_PATH = "loras_download_path"
    MODELS_DOWNLOAD_PATH = "models_download_path"
    THUMBNAILS_PATH = "thumbnails_path"
    DEFAULT_THEME = "default_theme"
    TRASH_PATH = "trash_path"  # Ruta de la papelera de reciclaje
    IMG_SORTED_PATH = "img_sorted_path"  # Ruta para imágenes ordenadas
    IMG_MASTER_PATH = "img_master_path"  # Ruta maestra para sincronización masiva de carpetas
    CONFIRM_TRASH_MOVE = "confirm_trash_move"  # Preguntar antes de mover a papelera (default: true)
    LOAD_FULL_IMAGE_IN_BULK = "load_full_image_in_bulk"  # Cargar imagen real en lugar de miniatura en gestión masiva (default: false)
    SHOW_ORDERED_FOLDER_IN_ORGANIZER = "show_ordered_folder_in_organizer"  # Mostrar destino también como origen (default: false)


"""
Configuración centralizada de la aplicación
Paso 1.1 - Configuración Básica
"""

import os
from pathlib import Path
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Obtener ruta del proyecto (2 niveles arriba desde shared/)
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_ROOT = Path(os.getenv("MNEMOS_CONFIG_DIR", str(PROJECT_ROOT)))


class Settings(BaseSettings):
    """Configuración de la aplicación"""

    model_config = SettingsConfigDict(
        env_file=CONFIG_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_suite_db"
    )
    
    # API
    api_title: str = "Mnemos galery API"
    api_version: str = "1.0.0"
    api_host: str = "127.0.0.1"
    api_port: int = 8005
    
    # CORS - String separado por comas (se convierte a lista automáticamente)
    # Incluye localhost:5175 para Vite dev server y electron:// para Electron
    cors_origins: str = "http://localhost:5175,http://localhost:3000,http://127.0.0.1:5175,null"
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Convierte string separado por comas a lista"""
        # Si es None o vacío, usar default
        if v is None:
            return "http://localhost:5175,http://localhost:3000"
        # Si es lista, convertir a string
        if isinstance(v, list):
            return ','.join(v)
        # Si es string, retornar tal cual
        if isinstance(v, str):
            return v
        # Default
        return "http://localhost:5175,http://localhost:3000"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Retorna cors_origins como lista para usar en FastAPI"""
        if isinstance(self.cors_origins, str):
            if not self.cors_origins.strip():
                return []
            return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]
        return []
    
# Instancia global de configuración
settings = Settings()


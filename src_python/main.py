"""
Main - El "Pegamento" que une los routers de los módulos
Paso 3.1 - FastAPI App Básica
FastAPI application entry point
"""

import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .shared.config import settings
from .shared.database import init_db, close_db
from .modules.gallery.router import router as gallery_router
from .modules.metadata_normalizer.router import router as normalizer_router
from .modules.database_viewer.router import router as database_viewer_router
from .shared.settings_router import router as settings_router

# Importar todos los modelos para que SQLAlchemy pueda resolver las relaciones
from .modules.gallery.models import Folder, Image  # noqa: F401
from .shared.models import Setting  # noqa: F401

# Configurar logging para mostrar INFO y superiores en consola
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Configurar nivel de logging para uvicorn (solo errores para evitar spam)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager - inicializa y cierra recursos"""
    # Startup: crear tablas si no existen
    logging.getLogger(__name__).info("Iniciando Mnemos galery API...")
    await init_db()
    logging.getLogger(__name__).info("Base de datos inicializada")
    yield
    # Shutdown
    logging.getLogger(__name__).info("Cerrando conexiones...")
    await close_db()


# Crear aplicación FastAPI
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers de módulos
app.include_router(gallery_router)
app.include_router(normalizer_router)
app.include_router(database_viewer_router)
app.include_router(settings_router)


@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "message": "Mnemos galery API",
        "version": settings.api_version,
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok"
    }

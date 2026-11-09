"""
Conexión única a PostgreSQL
Paso 0.3 - Conexión a Base de Datos (Mínima)
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from typing import AsyncGenerator

from .config import settings

# Base para los modelos SQLAlchemy
Base = declarative_base()

# Asegurar que DATABASE_URL use asyncpg
database_url = settings.database_url
if database_url.startswith("postgresql://") and "postgresql+asyncpg://" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

# Motor asíncrono
engine = create_async_engine(
    database_url,
    echo=False,  # Cambiar a True para debug SQL
    future=True,
    pool_pre_ping=True,  # Verifica conexión antes de usar
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,  # Reciclar conexiones cada hora
    pool_timeout=30,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency para obtener sesión de base de datos
    Uso: async with get_db() as db: ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Inicializa las tablas en la base de datos"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Compatibilidad con bases existentes sin migraciones automáticas:
        # garantiza el esquema mínimo para jerarquía de carpetas/tags.
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS folder_nodes (
                id BIGSERIAL PRIMARY KEY,
                folder_root_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                parent_node_id BIGINT NULL REFERENCES folder_nodes(id) ON DELETE CASCADE,
                rel_path TEXT NOT NULL,
                name TEXT NOT NULL,
                depth INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_folder_nodes_root_rel_path UNIQUE (folder_root_id, rel_path)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_folder_nodes_root_id ON folder_nodes(folder_root_id)",
            "CREATE INDEX IF NOT EXISTS idx_folder_nodes_parent_id ON folder_nodes(parent_node_id)",
            """
            CREATE TABLE IF NOT EXISTS folder_tags (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                color TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS folder_node_tags (
                folder_node_id BIGINT NOT NULL REFERENCES folder_nodes(id) ON DELETE CASCADE,
                tag_id BIGINT NOT NULL REFERENCES folder_tags(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (folder_node_id, tag_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_folder_node_tags_tag_id ON folder_node_tags(tag_id)",
            """
            ALTER TABLE images
            ADD COLUMN IF NOT EXISTS folder_node_id BIGINT NULL
            REFERENCES folder_nodes(id) ON DELETE SET NULL
            """,
            "CREATE INDEX IF NOT EXISTS idx_images_folder_node_id ON images(folder_node_id)",
        ]
        for ddl in ddl_statements:
            await conn.execute(text(ddl))


async def close_db():
    """Cierra la conexión a la base de datos"""
    await engine.dispose()


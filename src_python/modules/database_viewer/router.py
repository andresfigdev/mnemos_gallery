"""
Router para Database Viewer - Endpoints para visualizar tablas de la base de datos
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.database import get_db
from .service import get_all_tables_info, get_table_data
from .models import DatabaseOverview, TableData

router = APIRouter(prefix="/api/database", tags=["database"])


@router.get("/tables", response_model=DatabaseOverview)
async def list_tables(db: AsyncSession = Depends(get_db)):
    """
    Obtiene información de todas las tablas de la base de datos
    """
    try:
        tables = await get_all_tables_info(db)
        print(f"✅ Procesadas {len(tables)} tablas exitosamente")
        if len(tables) == 0:
            print("⚠️ ADVERTENCIA: No se procesó ninguna tabla")
        return DatabaseOverview(
            tables=tables,
            total_tables=len(tables)
        )
    except Exception as e:
        import traceback
        error_detail = f"Error obteniendo tablas: {str(e)}\n{traceback.format_exc()}"
        print(f"❌ {error_detail}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo tablas: {str(e)}")


@router.get("/tables/{table_name}/data", response_model=TableData)
async def get_table_data_endpoint(
    table_name: str,
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(50, ge=1, le=500, description="Tamaño de página"),
    order_by: str = Query(None, description="Columna para ordenar"),
    db: AsyncSession = Depends(get_db)
):
    """
    Obtiene los datos de una tabla específica con paginación
    """
    try:
        return await get_table_data(db, table_name, page, page_size, order_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo datos: {str(e)}")


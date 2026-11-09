"""
Modelos Pydantic para Database Viewer
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel


class ColumnInfo(BaseModel):
    """Información de una columna de tabla"""
    name: str
    type: str
    nullable: bool
    default: Optional[str] = None
    primary_key: bool = False
    foreign_key: Optional[str] = None


class TableInfo(BaseModel):
    """Información de una tabla"""
    name: str
    columns: List[ColumnInfo]
    row_count: int
    description: Optional[str] = None


class TableData(BaseModel):
    """Datos de una tabla con paginación"""
    table_name: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_rows: int
    page: int
    page_size: int
    total_pages: int


class DatabaseOverview(BaseModel):
    """Resumen general de la base de datos"""
    tables: List[TableInfo]
    total_tables: int


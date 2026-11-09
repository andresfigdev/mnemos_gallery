"""
Servicio para obtener información de tablas de la base de datos
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, inspect, MetaData
from sqlalchemy.engine import Result

from .models import TableInfo, ColumnInfo, TableData
from ...shared.database import Base, engine


async def get_all_tables_info(db: AsyncSession) -> List[TableInfo]:
    """
    Obtiene información de todas las tablas de la base de datos usando consultas SQL simples
    """
    tables_info = []
    
    # Obtener todas las tablas usando una query SQL simple
    query = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    result: Result = await db.execute(query)
    rows = result.all()
    table_names = [row[0] for row in rows] if rows else []
    print(f"📊 Tablas encontradas en BD: {table_names} (total: {len(table_names)})")
    
    if not table_names:
        print("⚠️ No se encontraron tablas en la base de datos")
        return tables_info
    
    for table_name in table_names:
        print(f"  → Procesando tabla: {table_name}")
        try:
            # Hacer rollback antes de procesar cada tabla para asegurar transacción limpia
            await db.rollback()
            
            # Obtener información de columnas (query simple sin JOINs)
            columns_query = text("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = :table_name
                ORDER BY ordinal_position
            """)
            columns_result: Result = await db.execute(columns_query, {"table_name": table_name})
            columns_data = columns_result.all()
            
            # Obtener primary keys (query separada)
            pk_query = text("""
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_schema = 'public'
                    AND tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_name = :table_name
            """)
            pk_result: Result = await db.execute(pk_query, {"table_name": table_name})
            pk_rows = pk_result.all()
            pk_columns = {row[0] for row in pk_rows}
            
            # Obtener foreign keys (query separada)
            fk_query = text("""
                SELECT
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                    AND tc.table_name = :table_name
            """)
            fk_result: Result = await db.execute(fk_query, {"table_name": table_name})
            fk_rows = fk_result.all()
            foreign_keys = {row[0]: f"{row[1]}.{row[2]}" for row in fk_rows}
            
            # Construir información de columnas
            columns_info = []
            for col in columns_data:
                col_name, data_type, is_nullable, col_default = col
                is_pk = col_name in pk_columns
                fk_info = foreign_keys.get(col_name)
                
                col_info = ColumnInfo(
                    name=col_name,
                    type=data_type,
                    nullable=is_nullable == 'YES',
                    default=str(col_default) if col_default else None,
                    primary_key=is_pk,
                    foreign_key=fk_info
                )
                columns_info.append(col_info)
            
            # Obtener conteo de filas
            row_count = await get_table_row_count(db, table_name)
            
            # Obtener comentario de la tabla si existe
            description = await get_table_comment(db, table_name)
            
            table_info = TableInfo(
                name=table_name,
                columns=columns_info,
                row_count=row_count,
                description=description
            )
            tables_info.append(table_info)
            print(f"  ✅ Tabla {table_name} procesada correctamente")
        except Exception as e:
            print(f"⚠️ Error procesando tabla {table_name}: {e}")
            # Hacer rollback para limpiar la transacción abortada
            try:
                await db.rollback()
            except:
                pass
            # Continuar con la siguiente tabla
            continue
    
    return tables_info


async def get_table_row_count(db: AsyncSession, table_name: str) -> int:
    """Obtiene el número de filas de una tabla"""
    try:
        # Validar nombre de tabla
        if not table_name.replace('_', '').isalnum():
            return 0
        query = text(f'SELECT COUNT(*) FROM "{table_name}"')
        result: Result = await db.execute(query)
        return result.scalar() or 0
    except Exception as e:
        print(f"⚠️ Error contando filas de {table_name}: {e}")
        return 0


async def get_table_comment(db: AsyncSession, table_name: str) -> Optional[str]:
    """Obtiene el comentario de una tabla si existe"""
    try:
        # Validar nombre de tabla
        if not table_name.replace('_', '').isalnum():
            return None
        query = text("""
            SELECT obj_description('public.' || :table_name::regclass, 'pg_class')
        """)
        result: Result = await db.execute(query, {"table_name": table_name})
        return result.scalar()
    except Exception as e:
        # Si falla, simplemente retornar None (no es crítico)
        return None


async def get_table_data(
    db: AsyncSession,
    table_name: str,
    page: int = 1,
    page_size: int = 50,
    order_by: Optional[str] = None
) -> TableData:
    """
    Obtiene los datos de una tabla con paginación
    """
    # Validar nombre de tabla para prevenir SQL injection
    # Solo permitir nombres de tablas alfanuméricos y guiones bajos
    if not table_name.replace('_', '').isalnum():
        raise ValueError(f"Nombre de tabla inválido: {table_name}")
    
    # Obtener columnas usando SQL
    columns_query = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
            AND table_name = :table_name
        ORDER BY ordinal_position
    """)
    columns_result: Result = await db.execute(columns_query, {"table_name": table_name})
    columns_rows = columns_result.all()
    columns = [row[0] for row in columns_rows] if columns_rows else []
    
    if not columns:
        raise ValueError(f"Tabla '{table_name}' no encontrada")
    
    # Construir query base
    base_query = f'SELECT * FROM "{table_name}"'
    
    # Agregar ORDER BY si se especifica
    if order_by:
        # Validar que order_by sea una columna válida
        if order_by in columns:
            base_query += f' ORDER BY "{order_by}"'
        else:
            # Si no es válida, ordenar por la primera columna
            base_query += f' ORDER BY "{columns[0]}"'
    else:
        # Ordenar por la primera columna por defecto
        base_query += f' ORDER BY "{columns[0]}"'
    
    # Obtener total de filas
    count_query = text(f'SELECT COUNT(*) FROM "{table_name}"')
    count_result: Result = await db.execute(count_query)
    total_rows = count_result.scalar() or 0
    
    # Calcular paginación
    offset = (page - 1) * page_size
    total_pages = (total_rows + page_size - 1) // page_size if total_rows > 0 else 1
    
    # Obtener datos paginados
    paginated_query = text(f"{base_query} LIMIT :limit OFFSET :offset")
    result: Result = await db.execute(
        paginated_query,
        {"limit": page_size, "offset": offset}
    )
    
    # Convertir resultados a diccionarios
    rows = []
    fetched_rows = result.all()
    for row in fetched_rows:
        row_dict = {}
        # row es una tupla, convertir a dict usando los nombres de columnas
        for i, col_name in enumerate(columns):
            value = row[i]
            # Convertir tipos especiales a strings para JSON
            if value is None:
                row_dict[col_name] = None
            elif isinstance(value, (dict, list)):
                row_dict[col_name] = value
            else:
                row_dict[col_name] = str(value)
        rows.append(row_dict)
    
    return TableData(
        table_name=table_name,
        columns=columns,
        rows=rows,
        total_rows=total_rows,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


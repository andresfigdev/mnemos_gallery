"""
Verificación completa del proyecto
Revisa que todo esté funcionando correctamente antes de continuar
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def print_section(title):
    """Imprime un título de sección"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def check_structure():
    """Verifica la estructura de carpetas"""
    print_section("1. Estructura de Carpetas")
    
    required_dirs = [
        "src_python/shared",
        "src_python/modules",
        "src_python/modules/gallery",
        "src_python/modules/metadata_normalizer",
        "tests",
        "scripts"
    ]
    
    all_ok = True
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if full_path.exists():
            print(f"✅ {dir_path}")
        else:
            print(f"❌ {dir_path} - NO EXISTE")
            all_ok = False
    
    return all_ok

def check_files():
    """Verifica archivos críticos"""
    print_section("2. Archivos Críticos")
    
    required_files = [
        "src_python/shared/config.py",
        "src_python/shared/database.py",
        "src_python/shared/event_bus.py",
        "src_python/main.py",
        "requirements.txt",
        ".env.example"
    ]
    
    all_ok = True
    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            size = full_path.stat().st_size
            if size > 0:
                print(f"✅ {file_path} ({size} bytes)")
            else:
                print(f"⚠️  {file_path} - VACÍO")
        else:
            print(f"❌ {file_path} - NO EXISTE")
            all_ok = False
    
    return all_ok

def check_imports():
    """Verifica que los imports funcionen"""
    print_section("3. Verificación de Imports")
    
    all_ok = True
    
    # Test 1: Config
    try:
        from src_python.shared.config import settings
        print("✅ config.py - Import exitoso")
        print(f"   DATABASE_URL: {settings.database_url.split('@')[0]}:***@{settings.database_url.split('@')[1] if '@' in settings.database_url else 'N/A'}")
        print(f"   API_HOST: {settings.api_host}")
        print(f"   API_PORT: {settings.api_port}")
    except Exception as e:
        print(f"❌ config.py - Error: {e}")
        all_ok = False
    
    # Test 2: Database
    try:
        from src_python.shared.database import engine, get_db, Base
        print("✅ database.py - Import exitoso")
        print(f"   Engine: {type(engine).__name__}")
        print(f"   Base: {type(Base).__name__}")
    except Exception as e:
        print(f"❌ database.py - Error: {e}")
        all_ok = False
    
    # Test 3: Event Bus
    try:
        from src_python.shared.event_bus import event_bus, Event, EventType
        print("✅ event_bus.py - Import exitoso")
        print(f"   EventBus: {type(event_bus).__name__}")
        print(f"   EventTypes: {len(list(EventType))} tipos definidos")
    except Exception as e:
        print(f"❌ event_bus.py - Error: {e}")
        all_ok = False
    
    return all_ok

def check_dependencies():
    """Verifica dependencias instaladas"""
    print_section("4. Dependencias Python")
    
    required_packages = {
        'fastapi': 'FastAPI',
        'uvicorn': 'Uvicorn',
        'sqlalchemy': 'SQLAlchemy',
        'asyncpg': 'asyncpg',
        'pydantic': 'Pydantic',
        'pydantic_settings': 'Pydantic Settings',
        'dotenv': 'python-dotenv'
    }
    
    all_ok = True
    for module, name in required_packages.items():
        try:
            __import__(module)
            print(f"✅ {name} instalado")
        except ImportError:
            print(f"❌ {name} NO instalado")
            all_ok = False
    
    return all_ok

def check_env_file():
    """Verifica archivo .env"""
    print_section("5. Archivo .env")
    
    env_path = project_root / ".env"
    
    if env_path.exists():
        print("✅ Archivo .env existe")
        
        # Verificar que tiene DATABASE_URL
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if "DATABASE_URL" in content:
                print("✅ DATABASE_URL encontrada en .env")
                return True
            else:
                print("❌ DATABASE_URL NO encontrada en .env")
                return False
    else:
        print("⚠️  Archivo .env NO existe (usará valores por defecto)")
        return True  # No es crítico si usa defaults

def check_database_connection():
    """Verifica conexión a base de datos"""
    print_section("6. Conexión a Base de Datos")
    
    try:
        import asyncio
        from src_python.shared.database import engine
        from sqlalchemy import text
        
        async def test_connection():
            try:
                async with engine.begin() as conn:
                    result = await conn.execute(text("SELECT version();"))
                    version = result.scalar()
                    print(f"✅ Conexión exitosa")
                    print(f"   PostgreSQL: {version.split(',')[0]}")
                    
                    result = await conn.execute(text("SELECT current_database();"))
                    db_name = result.scalar()
                    print(f"   Base de datos: {db_name}")
                    return True
            except Exception as e:
                print(f"❌ Error de conexión: {e}")
                return False
            finally:
                await engine.dispose()
        
        return asyncio.run(test_connection())
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def check_event_bus():
    """Verifica que el event bus funciona"""
    print_section("7. Event Bus")
    
    try:
        from src_python.shared.event_bus import event_bus, Event, EventType
        
        # Test simple
        event_received = False
        
        def handler(event: Event):
            nonlocal event_received
            event_received = True
        
        event_bus.subscribe(EventType.IMAGE_SCANNED, handler)
        test_event = Event(
            event_type=EventType.IMAGE_SCANNED,
            payload={"test": True}
        )
        event_bus.publish(test_event)
        event_bus.unsubscribe(EventType.IMAGE_SCANNED, handler)
        
        if event_received:
            print("✅ Event Bus funciona correctamente")
            return True
        else:
            print("❌ Event Bus no recibió el evento")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Ejecuta todas las verificaciones"""
    print("\n" + "="*60)
    print("  VERIFICACIÓN COMPLETA DEL PROYECTO")
    print("="*60)
    
    results = []
    
    results.append(("Estructura de carpetas", check_structure()))
    results.append(("Archivos críticos", check_files()))
    results.append(("Imports", check_imports()))
    results.append(("Dependencias", check_dependencies()))
    results.append(("Archivo .env", check_env_file()))
    results.append(("Conexión a BD", check_database_connection()))
    results.append(("Event Bus", check_event_bus()))
    
    # Resumen
    print_section("RESUMEN")
    
    all_ok = True
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
        if not result:
            all_ok = False
    
    print()
    if all_ok:
        print("✅ ¡Todo está funcionando correctamente!")
        print("   Puedes continuar con la siguiente fase del desarrollo.")
    else:
        print("❌ Hay problemas que resolver antes de continuar.")
        print("   Revisa los errores arriba y corrígelos.")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Verificación interrumpida")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


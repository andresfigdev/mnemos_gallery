"""
Script de ayuda para crear el archivo .env
Ejecuta: python create_env.py
"""

import os

def create_env_file():
    """Crea el archivo .env desde el template .env.example"""
    
    env_example_path = ".env.example"
    env_path = ".env"
    
    # Verificar si .env.example existe
    if not os.path.exists(env_example_path):
        print(f"❌ Error: No se encuentra {env_example_path}")
        return False
    
    # Verificar si .env ya existe
    if os.path.exists(env_path):
        response = input(f"⚠️  El archivo {env_path} ya existe. ¿Sobrescribir? (s/n): ")
        if response.lower() != 's':
            print("❌ Operación cancelada")
            return False
    
    # Leer template
    with open(env_example_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pedir valores al usuario
    print("\n📝 Configuración de .env\n")
    print("Presiona Enter para usar valores por defecto\n")
    
    db_user = input("Usuario PostgreSQL [postgres]: ").strip() or "postgres"
    db_password = input("Contraseña PostgreSQL [postgres]: ").strip() or "postgres"
    db_host = input("Host PostgreSQL [localhost]: ").strip() or "localhost"
    db_port = input("Puerto PostgreSQL [5432]: ").strip() or "5432"
    db_name = input("Nombre de BD [ai_suite_db]: ").strip() or "ai_suite_db"
    
    # Reemplazar DATABASE_URL
    database_url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    content = content.replace(
        "DATABASE_URL=postgresql+asyncpg://usuario:contraseña@localhost:5432/ai_suite_db",
        f"DATABASE_URL={database_url}"
    )
    
    # Escribir .env
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Archivo {env_path} creado exitosamente")
    print(f"   DATABASE_URL: postgresql+asyncpg://{db_user}:***@{db_host}:{db_port}/{db_name}")
    return True

if __name__ == "__main__":
    try:
        create_env_file()
    except Exception as e:
        print(f"❌ Error: {e}")


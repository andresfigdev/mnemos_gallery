#!/bin/bash
# Script para iniciar el backend FastAPI
# Uso: ./scripts/start_backend.sh

echo "🚀 Iniciando backend FastAPI..."

# Cambiar al directorio del proyecto
cd "$(dirname "$0")/.."

# Verificar que existe el entorno virtual
if [ ! -d "venv" ]; then
    echo "❌ No se encontró el entorno virtual. Ejecuta primero: python -m venv venv"
    exit 1
fi

# Activar entorno virtual
echo "📦 Activando entorno virtual..."
source venv/bin/activate

# Verificar que uvicorn está instalado
if ! python -c "import uvicorn" 2>/dev/null; then
    echo "❌ uvicorn no está instalado. Instalando..."
    pip install uvicorn[standard]
fi

# Iniciar el servidor
echo "🌐 Iniciando servidor en http://localhost:8005..."
echo "📝 Presiona Ctrl+C para detener el servidor"
echo ""

python -m uvicorn src_python.main:app --reload --host 0.0.0.0 --port 8005


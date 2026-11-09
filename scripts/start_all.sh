#!/bin/bash
# Script para iniciar backend y frontend simultáneamente
# Uso: ./scripts/start_all.sh

echo "🚀 Iniciando Backend y Frontend..."
echo ""

# Cambiar al directorio del proyecto
cd "$(dirname "$0")/.."

# Verificar que existe el entorno virtual
if [ ! -d "venv" ]; then
    echo "❌ No se encontró el entorno virtual. Ejecuta primero: python -m venv venv"
    exit 1
fi

# Verificar que existe src_vue
if [ ! -d "src_vue" ]; then
    echo "❌ No se encontró el directorio src_vue"
    exit 1
fi

echo "📦 Iniciando Backend y Frontend en ventanas separadas..."
echo ""
echo "💡 Se abrirán 2 ventanas de terminal:"
echo "   - Una para el Backend (FastAPI en http://localhost:8005)"
echo "   - Una para el Frontend + Electron (Vite en http://localhost:5173)"
echo ""
echo "⚠️  Para detener los servidores, cierra las ventanas o presiona Ctrl+C en cada una"
echo ""

# Obtener la ruta completa del Python del entorno virtual
VENV_PYTHON="$(pwd)/venv/bin/python"

# Verificar que existe el Python del venv
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ No se encontró Python en el entorno virtual: $VENV_PYTHON"
    exit 1
fi

# Detectar el sistema operativo
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - usar Terminal.app
        osascript -e "tell application \"Terminal\" to do script \"cd '$(pwd)' && echo '🚀 Backend FastAPI iniciando...' && echo '📦 Usando entorno virtual: venv' && echo '🌐 Servidor disponible en: http://localhost:8005' && echo '📝 Presiona Ctrl+C para detener' && echo '' && '$VENV_PYTHON' -m uvicorn src_python.main:app --reload --host 0.0.0.0 --port 8005\""
    sleep 2
    osascript -e "tell application \"Terminal\" to do script \"cd '$(pwd)/src_vue' && echo '🚀 Frontend Vue + Electron iniciando...' && echo '🌐 Servidor disponible en: http://localhost:5173' && echo '📱 Electron se abrirá automáticamente' && echo '📝 Presiona Ctrl+C para detener' && echo '' && npm run dev:electron\""
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - usar gnome-terminal, xterm, o el terminal por defecto
    if command -v gnome-terminal &> /dev/null; then
        gnome-terminal -- bash -c "cd '$(pwd)' && echo '🚀 Backend FastAPI iniciando...' && echo '📦 Usando entorno virtual: venv' && echo '🌐 Servidor disponible en: http://localhost:8005' && echo '📝 Presiona Ctrl+C para detener' && echo '' && '$VENV_PYTHON' -m uvicorn src_python.main:app --reload --host 0.0.0.0 --port 8005; exec bash"
        sleep 2
        gnome-terminal -- bash -c "cd '$(pwd)/src_vue' && echo '🚀 Frontend Vue + Electron iniciando...' && echo '🌐 Servidor disponible en: http://localhost:5173' && echo '📱 Electron se abrirá automáticamente' && echo '📝 Presiona Ctrl+C para detener' && echo '' && npm run dev:electron; exec bash"
    elif command -v xterm &> /dev/null; then
        xterm -e "cd '$(pwd)' && echo '🚀 Backend FastAPI iniciando...' && echo '📦 Usando entorno virtual: venv' && echo '🌐 Servidor disponible en: http://localhost:8005' && echo '📝 Presiona Ctrl+C para detener' && echo '' && '$VENV_PYTHON' -m uvicorn src_python.main:app --reload --host 0.0.0.0 --port 8005" &
        sleep 2
        xterm -e "cd '$(pwd)/src_vue' && echo '🚀 Frontend Vue + Electron iniciando...' && echo '🌐 Servidor disponible en: http://localhost:5173' && echo '📱 Electron se abrirá automáticamente' && echo '📝 Presiona Ctrl+C para detener' && echo '' && npm run dev:electron" &
    else
        echo "⚠️  No se encontró un terminal compatible. Iniciando en segundo plano..."
        cd "$(dirname "$0")/.."
        "$VENV_PYTHON" -m uvicorn src_python.main:app --reload --host 0.0.0.0 --port 8005 &
        BACKEND_PID=$!
        cd src_vue
        npm run dev:electron &
        FRONTEND_PID=$!
        echo "✅ Servidores iniciados en segundo plano"
        echo "   Backend PID: $BACKEND_PID"
        echo "   Frontend PID: $FRONTEND_PID"
        echo "   Para detener: kill $BACKEND_PID $FRONTEND_PID"
    fi
else
    echo "❌ Sistema operativo no soportado: $OSTYPE"
    exit 1
fi

echo "✅ Servidores iniciados en ventanas separadas"
echo ""
echo "⏳ Espera unos segundos para que los servidores se inicien completamente..."


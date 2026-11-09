#!/bin/bash
# Script Bash para crear y configurar entorno virtual (Linux/Mac)
# Ejecutar: chmod +x setup_venv.sh && ./setup_venv.sh

echo "🔧 Configurando Entorno Virtual de Python"
echo ""

# Verificar que Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python3 no está instalado"
    exit 1
fi

echo "✅ Python encontrado: $(python3 --version)"

# Crear entorno virtual
if [ -d "venv" ]; then
    echo "⚠️  El directorio 'venv' ya existe"
    read -p "¿Deseas eliminarlo y crear uno nuevo? (s/n): " response
    if [ "$response" = "s" ]; then
        rm -rf venv
        echo "✅ Directorio venv eliminado"
    else
        echo "ℹ️  Usando entorno virtual existente"
    fi
fi

if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
    echo "✅ Entorno virtual creado"
fi

# Activar entorno virtual
echo ""
echo "🔌 Activando entorno virtual..."
source venv/bin/activate

# Actualizar pip
echo "⬆️  Actualizando pip..."
pip install --upgrade pip

# Instalar dependencias
echo ""
echo "📥 Instalando dependencias desde requirements.txt..."
pip install -r requirements.txt

echo ""
echo "✅ ¡Entorno virtual configurado exitosamente!"
echo ""
echo "📝 Para activar el entorno virtual en el futuro, ejecuta:"
echo "   source venv/bin/activate"
echo ""
echo "📝 Para desactivar, ejecuta:"
echo "   deactivate"


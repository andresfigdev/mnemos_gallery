@echo off
REM Script Batch para crear y configurar entorno virtual (Windows CMD)
REM Ejecutar: setup_venv.bat

echo 🔧 Configurando Entorno Virtual de Python
echo.

REM Verificar que Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Error: Python no está instalado o no está en PATH
    pause
    exit /b 1
)

python --version
echo ✅ Python encontrado
echo.

REM Crear entorno virtual
if exist venv (
    echo ⚠️  El directorio 'venv' ya existe
    set /p response="¿Deseas eliminarlo y crear uno nuevo? (s/n): "
    if /i "%response%"=="s" (
        rmdir /s /q venv
        echo ✅ Directorio venv eliminado
    ) else (
        echo ℹ️  Usando entorno virtual existente
    )
)

if not exist venv (
    echo 📦 Creando entorno virtual...
    python -m venv venv
    echo ✅ Entorno virtual creado
)

REM Activar entorno virtual
echo.
echo 🔌 Activando entorno virtual...
call venv\Scripts\activate.bat

REM Actualizar pip
echo ⬆️  Actualizando pip...
python -m pip install --upgrade pip

REM Instalar dependencias
echo.
echo 📥 Instalando dependencias desde requirements.txt...
pip install -r requirements.txt

echo.
echo ✅ ¡Entorno virtual configurado exitosamente!
echo.
echo 📝 Para activar el entorno virtual en el futuro, ejecuta:
echo    venv\Scripts\activate.bat
echo.
echo 📝 Para desactivar, ejecuta:
echo    deactivate
echo.

pause


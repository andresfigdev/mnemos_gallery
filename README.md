# Mnemos galery

Aplicación de escritorio para indexar, visualizar y organizar galerías de imágenes. Incluye árbol de carpetas, miniaturas, metadatos PNG, gestión masiva, organización mediante arrastrar y soltar, dashboard y mantenimiento de nomenclatura.

## Componentes

- `src_vue/`: Vue 3, Vite y Electron.
- `src_python/`: API FastAPI y acceso a PostgreSQL.
- `database/`: migraciones de compatibilidad para jerarquía y nomenclatura.
- `scripts/`: preparación, desarrollo y construcción del instalador.
- `tests/`: pruebas automatizadas del backend.

## Requisitos de desarrollo

- Windows 10/11.
- Python 3.11 o superior.
- Node.js 20 o superior.
- PostgreSQL con una base llamada `ai_suite_db`, o una conexión equivalente configurada en `.env`.

## Preparación

```powershell
Copy-Item .env.example .env
.\scripts\setup_venv.ps1
Set-Location src_vue
npm ci
Set-Location ..
```

Ajusta `DATABASE_URL` en `.env` antes de iniciar la aplicación.

## Desarrollo con Electron

```powershell
.\scripts\start_electron.ps1
```

El script reinicia exclusivamente los procesos pertenecientes a este proyecto, levanta la API en `127.0.0.1:8005`, inicia Vite y abre Electron.

## Pruebas

```powershell
.\venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
Set-Location src_vue
npm run build
```

## Preparar el instalador de Windows

La configuración incluye:

- icono de aplicación e instalador en `src_vue/build/icon.ico`;
- backend empaquetado con PyInstaller;
- inicio y cierre automático del backend desde Electron instalado;
- instalador NSIS generado con electron-builder.

Instala una vez las herramientas de construcción:

```powershell
.\scripts\setup_venv.ps1 -WithBuildTools
Set-Location src_vue
npm ci
Set-Location ..
```

Después genera el instalador:

```powershell
Set-Location src_vue
npm run dist:win
```

El resultado queda en `src_vue/release/` y no se versiona.

### Base de datos en la aplicación instalada

PostgreSQL sigue siendo un requisito externo; no se incluye dentro del instalador. De forma predeterminada se usa:

```text
postgresql+asyncpg://postgres:postgres@localhost:5432/ai_suite_db
```

Para usar otra conexión, copia `.env.example` como `.env` en `%APPDATA%\Mnemos galery\` y ajusta `DATABASE_URL`. Los datos, rutas de imágenes y la base PostgreSQL no se incorporan al instalador ni al repositorio.

## Archivos que no se versionan

Dependencias, entornos virtuales, secretos, builds, instaladores, logs, cachés, datos locales y utilidades históricas están cubiertos por `.gitignore`.

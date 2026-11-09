import { app, BrowserWindow, ipcMain, dialog, session } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import * as http from 'http';
import { ChildProcess, spawn } from 'child_process';

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;
let backendLogFd: number | null = null;

app.setName('Mnemos galery');

function isBackendHealthy(): Promise<boolean> {
  return new Promise((resolve) => {
    const request = http.get('http://127.0.0.1:8005/health', { timeout: 1000 }, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.on('timeout', () => {
      request.destroy();
      resolve(false);
    });
    request.on('error', () => resolve(false));
  });
}

async function waitForBackend(timeoutMs = 30000): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isBackendHealthy()) return;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error('El backend de Mnemos galery no respondió a tiempo. Revisa backend.log en la carpeta de datos de la aplicación.');
}

async function startPackagedBackend(): Promise<void> {
  if (!app.isPackaged || await isBackendHealthy()) return;

  const backendExecutable = path.join(process.resourcesPath, 'backend', 'mnemos-gallery-api.exe');
  if (!fs.existsSync(backendExecutable)) {
    throw new Error(`No se encontró el backend empaquetado: ${backendExecutable}`);
  }

  const userDataPath = app.getPath('userData');
  fs.mkdirSync(userDataPath, { recursive: true });
  backendLogFd = fs.openSync(path.join(userDataPath, 'backend.log'), 'a');
  backendProcess = spawn(backendExecutable, [], {
    cwd: userDataPath,
    windowsHide: true,
    env: {
      ...process.env,
      MNEMOS_CONFIG_DIR: userDataPath,
      API_HOST: '127.0.0.1',
      API_PORT: '8005',
    },
    stdio: ['ignore', backendLogFd, backendLogFd],
  });

  await waitForBackend();
}

function stopPackagedBackend(): void {
  if (backendProcess?.pid) {
    if (process.platform === 'win32') {
      const killer = spawn('taskkill.exe', ['/pid', String(backendProcess.pid), '/t', '/f'], {
        windowsHide: true,
        stdio: 'ignore',
      });
      killer.unref();
    } else {
      backendProcess.kill();
    }
  }
  backendProcess = null;
  if (backendLogFd !== null) {
    try { fs.closeSync(backendLogFd); } catch { /* el proceso puede conservarlo durante el cierre */ }
    backendLogFd = null;
  }
}

// Configurar Content Security Policy
function setupCSP() {
  const csp = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'", // unsafe-inline necesario para Vite en desarrollo
    "style-src 'self' 'unsafe-inline'", // unsafe-inline necesario para estilos inline
    "img-src 'self' data: blob: http: https:",
    "font-src 'self' data:",
    "connect-src 'self' http://localhost:* ws://localhost:* wss://localhost:*",
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'"
  ].join('; ');

  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [csp]
      }
    });
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    frame: true,
    backgroundColor: '#1d232a',
    title: 'Mnemos galery',
    icon: path.join(__dirname, '../build/icon.ico'),
  });

  // En desarrollo, cargar desde Vite dev server
  if (!app.isPackaged) {
    await mainWindow.loadURL('http://127.0.0.1:5175');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    // En producción, cargar el build
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ============================================
// IPC Handlers
// ============================================

// Selector de carpetas nativo
ipcMain.handle('dialog:selectFolder', async () => {
  if (!mainWindow) return null;
  
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Seleccionar carpeta de imágenes'
  });
  
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  
  return result.filePaths[0];
});

// Selector de archivos (imágenes)
ipcMain.handle('dialog:selectImages', async () => {
  if (!mainWindow) return [];
  
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'multiSelections'],
    title: 'Seleccionar imágenes',
    filters: [
      { name: 'Imágenes', extensions: ['png', 'jpg', 'jpeg', 'webp', 'gif'] }
    ]
  });
  
  if (result.canceled) {
    return [];
  }
  
  return result.filePaths;
});

// Obtener información de la app
ipcMain.handle('app:getInfo', () => {
  return {
    name: app.getName(),
    version: app.getVersion(),
    isPackaged: app.isPackaged,
    platform: process.platform,
  };
});

// ============================================
// App Lifecycle
// ============================================

app.whenReady().then(async () => {
  // Configurar CSP antes de crear ventanas
  setupCSP();

  try {
    await startPackagedBackend();
    await createWindow();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    dialog.showErrorBox('Mnemos galery no pudo iniciar', message);
    app.quit();
    return;
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopPackagedBackend();
});

// Manejar errores no capturados
process.on('uncaughtException', (error) => {
  console.error('Uncaught Exception:', error);
  dialog.showErrorBox('Error', error.message);
});

process.on('unhandledRejection', (reason) => {
  console.error('Unhandled Rejection:', reason);
});

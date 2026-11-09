const { contextBridge, ipcRenderer } = require('electron');

// API expuesta al renderer (frontend)
const electronAPI = {
  // Selector de carpetas nativo
  selectFolder: (): Promise<string | null> => {
    return ipcRenderer.invoke('dialog:selectFolder');
  },
  
  // Selector de imágenes
  selectImages: (): Promise<string[]> => {
    return ipcRenderer.invoke('dialog:selectImages');
  },
  
  // Info de la app
  getAppInfo: (): Promise<{
    name: string;
    version: string;
    isPackaged: boolean;
    platform: string;
  }> => {
    return ipcRenderer.invoke('app:getInfo');
  },
  
  // Verificar si estamos en Electron
  isElectron: true,
};

// Exponer la API de forma segura
contextBridge.exposeInMainWorld('electronAPI', electronAPI);

console.log('✅ Preload script loaded - electronAPI exposed');

// Tipos para la API de Electron expuesta via preload

export interface ElectronAPI {
  selectFolder: () => Promise<string | null>;
  selectImages: () => Promise<string[]>;
  getAppInfo: () => Promise<{
    name: string;
    version: string;
    isPackaged: boolean;
    platform: string;
  }>;
  isElectron: boolean;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export {};


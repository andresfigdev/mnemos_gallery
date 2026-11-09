// Utilidades para interactuar con Electron

/**
 * Verifica si la aplicación está corriendo en Electron
 */
export function isElectron(): boolean {
  return !!(window.electronAPI?.isElectron);
}

/**
 * Abre el diálogo nativo para seleccionar una carpeta
 * @returns La ruta de la carpeta seleccionada o null si se canceló
 */
export async function selectFolder(): Promise<string | null> {
  if (!isElectron()) {
    console.warn('selectFolder: No estamos en Electron, usando prompt');
    const path = prompt('Ingresa la ruta de la carpeta:');
    return path || null;
  }
  
  return window.electronAPI!.selectFolder();
}

/**
 * Abre el diálogo nativo para seleccionar imágenes
 * @returns Array de rutas de las imágenes seleccionadas
 */
export async function selectImages(): Promise<string[]> {
  if (!isElectron()) {
    console.warn('selectImages: No estamos en Electron');
    return [];
  }
  
  return window.electronAPI!.selectImages();
}

/**
 * Obtiene información de la aplicación
 */
export async function getAppInfo() {
  if (!isElectron()) {
    return {
      name: 'Mnemos galery',
      version: '1.0.0',
      isPackaged: false,
      platform: 'web',
    };
  }
  
  return window.electronAPI!.getAppInfo();
}


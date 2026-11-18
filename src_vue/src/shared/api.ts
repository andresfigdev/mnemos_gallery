/**
 * API Client Base
 * Paso 7.2 - Cliente axios configurado para comunicarse con el backend
 */

import axios, { AxiosInstance, AxiosError } from 'axios'

// Detectar si estamos en Electron
const isElectron = !!(window.electronAPI?.isElectron)

// Configurar baseURL: en Electron usamos la URL directa, en navegador usamos el proxy
export const apiBaseURL = isElectron
  ? 'http://localhost:8005/api'  // URL directa para Electron
  : '/api'                        // Proxy de Vite para navegador

export function getApiResourceUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${apiBaseURL.replace(/\/$/, '')}${normalizedPath}`
}

// Crear instancia de axios configurada
const apiClient: AxiosInstance = axios.create({
  baseURL: apiBaseURL,
  timeout: 300000, // 5 minutos (300 segundos) - necesario para escanear carpetas grandes con muchas imágenes
  headers: {
    'Content-Type': 'application/json',
  },
})

// Interceptor para manejar errores
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Manejar errores de red
    if (error.code === 'ECONNABORTED') {
      console.error('Timeout: La petición tardó demasiado')
    } else if (error.response) {
      // El servidor respondió con un código de estado fuera del rango 2xx
      console.error('Error de respuesta:', error.response.status, error.response.data)
    } else if (error.request) {
      // La petición fue hecha pero no se recibió respuesta
      console.error('Error de red: No se recibió respuesta del servidor')
    } else {
      // Algo pasó al configurar la petición
      console.error('Error:', error.message)
    }
    return Promise.reject(error)
  }
)

// Función helper para verificar el health del backend
export async function checkHealth(): Promise<{ status: string }> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error) {
    throw error
  }
}

export default apiClient


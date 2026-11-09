/**
 * API client para Settings
 */

import apiClient from '../../shared/api'
import type { AxiosResponse } from 'axios'

export interface Setting {
  key: string
  value: string | null
  description: string | null
}

export interface ImagePaths {
  trash_path: string | null
  img_sorted_path: string | null
}

export interface ImagePathsUpdate {
  trash_path?: string | null
  img_sorted_path?: string | null
}

export interface MasterImgPath {
  img_master_path: string | null
}

/**
 * Lista todos los settings
 */
export async function listSettings(): Promise<Setting[]> {
  const response: AxiosResponse<Setting[]> = await apiClient.get('/settings')
  return response.data
}

/**
 * Obtiene un setting por clave
 */
export async function getSetting(key: string): Promise<Setting> {
  const response: AxiosResponse<Setting> = await apiClient.get(`/settings/${key}`)
  return response.data
}

/**
 * Actualiza o crea un setting
 */
export async function updateSetting(key: string, value: string | null, description?: string | null): Promise<Setting> {
  const response: AxiosResponse<Setting> = await apiClient.put(`/settings/${key}`, {
    value,
    description
  })
  return response.data
}

/**
 * Elimina un setting
 */
export async function deleteSetting(key: string): Promise<{ message: string; deleted: boolean }> {
  const response: AxiosResponse<{ message: string; deleted: boolean }> = await apiClient.delete(`/settings/${key}`)
  return response.data
}

/**
 * Obtiene las rutas de imágenes configuradas (papelera e IMG ordenadas)
 */
export async function getImagePaths(): Promise<ImagePaths> {
  const response: AxiosResponse<ImagePaths> = await apiClient.get('/settings/paths/images')
  return response.data
}

/**
 * Actualiza las rutas de imágenes
 */
export async function updateImagePaths(paths: ImagePathsUpdate): Promise<ImagePaths> {
  const response: AxiosResponse<ImagePaths> = await apiClient.put('/settings/paths/images', paths)
  return response.data
}

export async function getMasterImgPath(): Promise<MasterImgPath> {
  const response: AxiosResponse<MasterImgPath> = await apiClient.get('/settings/paths/master-img')
  return response.data
}

export async function updateMasterImgPath(path: string | null): Promise<MasterImgPath> {
  const response: AxiosResponse<MasterImgPath> = await apiClient.put('/settings/paths/master-img', {
    img_master_path: path,
  })
  return response.data
}


/**
 * Gallery API Client
 * Paso 8.1 - Cliente para interactuar con los endpoints de gallery
 */

import apiClient from '@/shared/api'
import type { AxiosResponse } from 'axios'

export interface Folder {
  id: string
  path: string
  name: string
  default_entity_id?: number | null
  enabled: boolean
  last_scan_at: string | null
  created_at: string
  image_count: number
}

export interface LinkedResourceInfo {
  resource_id: number
  nombre: string
  strength?: number | null  // Solo para LoRAs
  strength_model?: number | null  // Solo para LoRAs
}

export interface Image {
  id: number
  guid: string | null  // GUID persistente de la imagen
  folder_id: string
  folder_node_id?: number | null
  entity_id?: number | null
  path: string
  thumb_path: string | null
  size: number
  width: number | null
  height: number | null
  prompt_json: Record<string, any> | null
  workflow_json: Record<string, any> | null
  created_at: string
  is_nsfw?: boolean // Agregado para compatibilidad con análisis
  
  linked_model?: LinkedResourceInfo | null
  linked_loras?: LinkedResourceInfo[]
}

export interface FolderCreate {
  path: string
  name: string
  default_entity_id?: number | null
  enabled?: boolean
}

export interface FolderTag {
  id: number
  name: string
  color?: string | null
}

export interface FolderNode {
  id: number
  folder_root_id: string
  parent_node_id: number | null
  rel_path: string
  name: string
  depth: number
  naming_base?: string | null
  naming_number_width?: number | null
  image_count: number
  tag_ids: number[]
  tags: FolderTag[]
  effective_tag_ids: number[]
  effective_tags: FolderTag[]
  children: FolderNode[]
}

export interface FolderTreeResponse {
  folder_id: string
  nodes: FolderNode[]
}

export interface DashboardNamedCount {
  name: string
  display_name: string
  count: number
  percent: number
  filter?: {
    mode: string
    value: string
  } | null
}

export interface DashboardFolderCount {
  folder_id: string
  folder_name: string
  display_name: string
  count: number
  percent: number
  filter?: {
    mode: string
    value: string
  } | null
}

export interface DashboardSummary {
  total_images: number
  total_folders: number
  total_subfolders: number
  total_active_tags: number
}

export interface DashboardAIUsage {
  top_checkpoints: DashboardNamedCount[]
  top_loras: DashboardNamedCount[]
  missing_checkpoint_count: number
  missing_lora_count: number
}

export interface DashboardRootVsSubfolder {
  root_images: number
  subfolder_images: number
  root_percent: number
  subfolder_percent: number
}

export interface DashboardDistribution {
  images_by_folder: DashboardFolderCount[]
  images_by_folder_type: DashboardNamedCount[]
  root_vs_subfolder: DashboardRootVsSubfolder
}

export interface DashboardMetrics {
  summary: DashboardSummary
  ai_usage: DashboardAIUsage
  distribution: DashboardDistribution
  generated_at: string
}

export interface ScanFolderRequest {
  folder_id: string
  recursive?: boolean
  create_records?: boolean
}

export interface OrphanedImageInfo {
  id: number
  guid: string | null
  path: string
  folder_id: string
  thumb_path: string | null
  reason?: 'not_exists' | 'not_file' | 'cannot_read' | 'error' | 'unknown'
  error?: string | null
}

export interface ScanFolderResponse {
  folder_id: string
  folder_path: string
  total_files: number
  image_count: number
  created_count: number
  updated_count: number
  errors: string[]
  orphaned_images: OrphanedImageInfo[]
}

export interface SyncMasterRootItem {
  folder_id: string
  folder_name: string
  folder_path: string
  existed: boolean
  created_count: number
  updated_count: number
  image_count: number
  errors: number
}

export interface SyncMasterFoldersResponse {
  master_path: string
  roots_detected: number
  roots_created: number
  roots_existing: number
  scanned_roots: SyncMasterRootItem[]
  errors: string[]
}

export interface MasterNamingEntry {
  image_id: number
  folder_id: string
  folder_name: string
  old_path: string
  new_path: string
}

export interface MasterNamingResponse {
  master_path: string
  folders_scanned: number
  folder_nodes_scanned: number
  images_scanned: number
  rename_count: number
  unchanged_count: number
  unassigned_count: number
  entries: MasterNamingEntry[]
  entries_truncated: boolean
  renamed_count?: number | null
}

/**
 * Lista todas las carpetas
 */
export async function listFolders(): Promise<Folder[]> {
  const response: AxiosResponse<Folder[]> = await apiClient.get('/gallery/folders')
  return response.data
}

/**
 * Crea una nueva carpeta
 */
export async function createFolder(data: FolderCreate): Promise<Folder> {
  const response: AxiosResponse<Folder> = await apiClient.post('/gallery/folders', data)
  return response.data
}

/**
 * Escanea una carpeta
 */
export async function scanFolder(data: ScanFolderRequest): Promise<ScanFolderResponse> {
  const response: AxiosResponse<ScanFolderResponse> = await apiClient.post('/gallery/folders/scan', data)
  return response.data
}

export async function syncMasterFolders(masterPath?: string): Promise<SyncMasterFoldersResponse> {
  const payload = masterPath ? { master_path: masterPath } : {}
  const response: AxiosResponse<SyncMasterFoldersResponse> = await apiClient.post('/gallery/folders/sync-master', payload)
  return response.data
}

export async function previewMasterMissingNames(): Promise<MasterNamingResponse> {
  const response: AxiosResponse<MasterNamingResponse> = await apiClient.post('/gallery/folders/master-naming/preview')
  return response.data
}

export async function applyMasterMissingNames(): Promise<MasterNamingResponse> {
  const response: AxiosResponse<MasterNamingResponse> = await apiClient.post('/gallery/folders/master-naming/apply')
  return response.data
}

export interface CleanupOrphanedImagesRequest {
  folder_id: string
  image_ids: number[]
}

export interface CleanupOrphanedImagesResponse {
  deleted_count: number
  moved_to_trash_count?: number
  errors: string[]
}

/**
 * Limpia imágenes huérfanas de la base de datos
 */
export async function cleanupOrphanedImages(
  folderId: string,
  data: CleanupOrphanedImagesRequest
): Promise<CleanupOrphanedImagesResponse> {
  const response: AxiosResponse<CleanupOrphanedImagesResponse> = await apiClient.post(
    `/gallery/folders/${folderId}/cleanup-orphaned`,
    data
  )
  return response.data
}

/**
 * Lista imágenes con filtros opcionales
 */
export async function listImages(params?: {
  folder_id?: string
  folder_node_id?: number
  include_descendants?: boolean
  entity_id?: number
  limit?: number
  offset?: number
  search?: string
  missing_checkpoint?: boolean
  missing_lora?: boolean
  checkpoint_name?: string
  lora_name?: string
  folder_type?: string
  include_tag_ids?: number[]
  exclude_tag_ids?: number[]
}): Promise<{ images: Image[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params) {
    if (params.folder_id) searchParams.append('folder_id', params.folder_id)
    if (params.folder_node_id !== undefined) searchParams.append('folder_node_id', String(params.folder_node_id))
    if (params.include_descendants) searchParams.append('include_descendants', 'true')
    if (params.entity_id !== undefined) searchParams.append('entity_id', String(params.entity_id))
    if (params.limit !== undefined) searchParams.append('limit', String(params.limit))
    if (params.offset !== undefined) searchParams.append('offset', String(params.offset))
    if (params.search) searchParams.append('search', params.search)
    if (params.missing_checkpoint) searchParams.append('missing_checkpoint', 'true')
    if (params.missing_lora) searchParams.append('missing_lora', 'true')
    if (params.checkpoint_name) searchParams.append('checkpoint_name', params.checkpoint_name)
    if (params.lora_name) searchParams.append('lora_name', params.lora_name)
    if (params.folder_type) searchParams.append('folder_type', params.folder_type)
    for (const id of params.include_tag_ids || []) {
      searchParams.append('include_tag_ids', String(id))
    }
    for (const id of params.exclude_tag_ids || []) {
      searchParams.append('exclude_tag_ids', String(id))
    }
  }
  const query = searchParams.toString()
  const url = query ? `/gallery/images?${query}` : '/gallery/images'
  const response: AxiosResponse<{ images: Image[]; total: number }> = await apiClient.get(url)
  return response.data
}

export async function getFolderTree(folderId: string): Promise<FolderTreeResponse> {
  const response: AxiosResponse<FolderTreeResponse> = await apiClient.get(`/gallery/folders/${folderId}/tree`)
  return response.data
}

export async function listFolderTags(): Promise<FolderTag[]> {
  const response: AxiosResponse<FolderTag[]> = await apiClient.get('/gallery/tags')
  return response.data
}

export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  const response: AxiosResponse<DashboardMetrics> = await apiClient.get('/gallery/dashboard/metrics')
  return response.data
}

export async function updateFolderNodeTags(
  nodeId: number,
  payload: { tag_ids?: number[]; tags?: string[] }
): Promise<FolderTag[]> {
  const response: AxiosResponse<FolderTag[]> = await apiClient.patch(`/gallery/folder-nodes/${nodeId}/tags`, payload)
  return response.data
}

export async function updateFolderNodeNomenclature(
  folderId: string,
  nodeId: number,
  payload: { naming_base?: string | null; naming_number_width?: number | null }
): Promise<FolderNode> {
  const response: AxiosResponse<FolderNode> = await apiClient.patch(
    `/gallery/folders/${folderId}/nodes/${nodeId}/nomenclature`,
    payload
  )
  return response.data
}

export interface FolderNodeRenameRequest {
  mode: 'all' | 'selected'
  image_ids?: number[]
}

export interface RenamePreviewEntry {
  image_id: number
  old_path: string
  new_path: string | null
  reason: 'unchanged' | 'rename'
  name_class: string | null
}

export interface RenamePreviewResponse {
  folder_id: string
  folder_node_id: number
  next_counter_start: number
  related_count: number
  unrelated_count: number
  unchanged_count: number
  entries: RenamePreviewEntry[]
}

export interface RenameApplyResponse {
  renamed: number
  folder_id: string
  folder_node_id: number
}

export async function previewFolderNodeRename(
  folderId: string,
  nodeId: number,
  body: FolderNodeRenameRequest
): Promise<RenamePreviewResponse> {
  const response: AxiosResponse<RenamePreviewResponse> = await apiClient.post(
    `/gallery/folders/${folderId}/nodes/${nodeId}/rename/preview`,
    body
  )
  return response.data
}

export async function applyFolderNodeRename(
  folderId: string,
  nodeId: number,
  body: FolderNodeRenameRequest
): Promise<RenameApplyResponse> {
  const response: AxiosResponse<RenameApplyResponse> = await apiClient.post(
    `/gallery/folders/${folderId}/nodes/${nodeId}/rename/apply`,
    body
  )
  return response.data
}

/**
 * Obtiene una imagen por su ID
 */
export async function getImage(imageId: number): Promise<Image> {
  const response: AxiosResponse<Image> = await apiClient.get(`/gallery/images/${imageId}`)
  return response.data
}

/**
 * Obtiene la URL del thumbnail de una imagen
 */
export function getThumbnailUrl(imageId: number): string {
  return `/api/gallery/images/${imageId}/thumbnail`
}

/**
 * Obtiene la URL de la imagen completa (no el thumbnail)
 */
export function getFullImageUrl(imageId: number): string {
  return `/api/gallery/images/${imageId}/full`
}

/**
 * Elimina del registro (BD) una carpeta y sus imágenes.
 * No elimina archivos físicos del disco.
 */
export async function deleteFolder(folderId: string): Promise<{ message: string; deleted: boolean }> {
  const response = await apiClient.delete(`/gallery/folders/${folderId}`)
  return response.data
}

export interface DeleteFolderNodeResponse {
  message: string
  deleted: boolean
  deleted_nodes: number
  deleted_images: number
}

/**
 * Elimina del registro (BD) una subcarpeta lógica y su subárbol.
 * No elimina archivos físicos del disco.
 */
export async function deleteFolderNodeRegistration(
  folderId: string,
  nodeId: number
): Promise<DeleteFolderNodeResponse> {
  const response: AxiosResponse<DeleteFolderNodeResponse> = await apiClient.delete(
    `/gallery/folders/${folderId}/nodes/${nodeId}`
  )
  return response.data
}

export async function deleteEmptySourceFolder(
  folderId: string,
  nodeId: number,
): Promise<{ message: string; deleted: boolean; node_id: number }> {
  const response = await apiClient.delete(`/gallery/folders/${folderId}/nodes/${nodeId}/delete-empty`)
  return response.data
}

export interface SourceFolderNodeMoveItem {
  folder_id: string
  node_id: number
}

export async function moveSourceFolderNodes(data: {
  source_nodes: SourceFolderNodeMoveItem[]
  destination_folder_id: string
  destination_node_id: number
}): Promise<{
  message: string
  moved_count: number
  updated_database_images: number
  updated_database_nodes: number
  destination_folder_id: string
  destination_node_id: number
}> {
  const response = await apiClient.post('/gallery/folders/nodes/move', data)
  return response.data
}

/**
 * Activa o desactiva una carpeta
 */
export async function toggleFolder(folderId: string, enabled: boolean): Promise<Folder> {
  const response = await apiClient.patch(`/gallery/folders/${folderId}/toggle`, { enabled })
  return response.data
}

/**
 * Mueve una imagen a la papelera de reciclaje
 */
export interface MoveImageToTrashResponse {
  message: string
  image_id: number
  trash_path: string | null
  missing_original: boolean
  thumbnail_deleted: boolean
}

export async function moveImageToTrash(imageId: number): Promise<MoveImageToTrashResponse> {
  const response: AxiosResponse<MoveImageToTrashResponse> = await apiClient.post(`/gallery/images/${imageId}/move-to-trash`)
  return response.data
}

export interface UpdateMetadataRequest {
  model_name?: string
  loras?: Array<{ name: string; strength?: number; strength_model?: number }>
}

/**
 * Actualiza los metadatos de una imagen (modelo y/o LoRAs)
 */
export async function updateImageMetadata(imageId: number, data: UpdateMetadataRequest): Promise<Image> {
  const response: AxiosResponse<Image> = await apiClient.patch(`/gallery/images/${imageId}/metadata`, data)
  return response.data
}

/**
 * Lista las carpetas dentro de IMG_SORTED_PATH
 */
export async function listSortedFolders(): Promise<string[]> {
  const response: AxiosResponse<string[]> = await apiClient.get('/gallery/sorted-folders')
  return response.data
}

export interface MoveImagesRequest {
  image_ids: number[]
  folder_name: string
}

export interface MoveImagesResponse {
  message: string
  moved_count: number
  skipped_count?: number
  folder_id: string
  folder_name: string
  errors: string[]
}

export interface OrganizerFolder {
  name: string
  path: string
  image_count: number
  total_image_count: number
  has_thumb: boolean
  children: OrganizerFolder[]
}

export interface OrganizerState {
  configured: boolean
  root_path: string | null
  folder_id: string | null
  configuration_error?: string | null
  tree: OrganizerFolder[]
  total_images: number
}

export interface OrganizerMoveResponse {
  message: string
  moved_count: number
  skipped_count: number
  destination_path: string
  tree: OrganizerFolder[]
  total_images: number
}

export async function getOrganizer(): Promise<OrganizerState> {
  const response: AxiosResponse<OrganizerState> = await apiClient.get('/gallery/organizer')
  return response.data
}

export async function createOrganizerFolder(data: {
  name: string
  parent_path?: string
}): Promise<{ created_path: string; tree: OrganizerFolder[]; total_images: number }> {
  const response = await apiClient.post('/gallery/organizer/folders', data)
  return response.data
}

export interface OrganizerFolderRenameResponse {
  message: string
  old_path: string
  new_path: string
  renamed_image_count: number
  tree: OrganizerFolder[]
  total_images: number
}

export async function renameOrganizerFolder(data: {
  path: string
  new_name: string
}): Promise<OrganizerFolderRenameResponse> {
  const response: AxiosResponse<OrganizerFolderRenameResponse> = await apiClient.patch(
    '/gallery/organizer/folders',
    data,
  )
  return response.data
}

export interface OrganizerFoldersMoveResponse {
  message: string
  moved_count: number
  moved_paths: Record<string, string>
  updated_database_images: number
  updated_database_nodes: number
  tree: OrganizerFolder[]
  total_images: number
}

export async function moveOrganizerFolders(data: {
  source_paths: string[]
  destination_path: string
}): Promise<OrganizerFoldersMoveResponse> {
  const response: AxiosResponse<OrganizerFoldersMoveResponse> = await apiClient.post(
    '/gallery/organizer/folders/move',
    data,
  )
  return response.data
}

export async function moveSourceFoldersToOrganizer(data: {
  source_nodes: SourceFolderNodeMoveItem[]
  destination_path: string
}): Promise<{
  message: string
  moved_count: number
  updated_database_images: number
  updated_database_nodes: number
  destination_path: string
  tree: OrganizerFolder[]
  total_images: number
}> {
  const response = await apiClient.post('/gallery/organizer/source-folders/move', data)
  return response.data
}

export async function moveImagesWithOrganizer(data: {
  image_ids: number[]
  destination_path: string
}): Promise<OrganizerMoveResponse> {
  const response: AxiosResponse<OrganizerMoveResponse> = await apiClient.post('/gallery/organizer/move', data)
  return response.data
}

/**
 * Mueve imágenes a una carpeta dentro de IMG_SORTED_PATH
 */
export async function moveImagesToSortedFolder(data: MoveImagesRequest): Promise<MoveImagesResponse> {
  const response: AxiosResponse<MoveImagesResponse> = await apiClient.post('/gallery/images/move-to-sorted-folder', data)
  return response.data
}

/**
 * Abre una carpeta en el explorador de archivos del sistema
 */
export async function openFolderInExplorer(path: string): Promise<{ message: string }> {
  const response: AxiosResponse<{ message: string }> = await apiClient.post(`/gallery/folders/open?path=${encodeURIComponent(path)}`)
  return response.data
}


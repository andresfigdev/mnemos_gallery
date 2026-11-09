<template>
  <div class="image-grid-container">
    <div class="images-header">
      <div class="images-topbar">
        <h2>Imágenes</h2>
        <div class="images-controls">
          <select v-model="localSelectedFolderId" @change="handleFolderSelectChange" class="select">
            <option value="">Todas las carpetas</option>
            <option 
              v-for="folder in enabledFolders" 
              :key="folder.id" 
              :value="folder.id"
            >
              {{ folder.name }} ({{ folder.image_count }})
            </option>
          </select>
          <button @click="loadImages(true)" class="btn btn-sm btn-primary" :disabled="loading">
            <RefreshCw :size="16" />
            Actualizar
          </button>
          <div ref="filtersPopoverRef" class="filters-popover-anchor">
            <button
              class="btn btn-sm btn-ghost filter-toggle-btn"
              :class="{ 'btn-active': showTagPanel }"
              @click="showTagPanel = !showTagPanel"
            >
              Filtros
            </button>
            <div v-if="showTagPanel" class="filters-popover">
              <div class="filters-popover-header">
                <span class="filters-title">Filtros activos</span>
                <button
                  class="filters-clear-btn"
                  :disabled="!includeTagIds.length && !excludeTagIds.length"
                  @click="clearTagFilters"
                >
                  Limpiar
                </button>
              </div>
              <div class="filters-divider" />

              <div class="filter-block">
                <span class="filter-block-title">Incluir</span>
                <div v-if="includedTags.length" class="filter-chip-list">
                  <button
                    v-for="tag in includedTags"
                    :key="`active-include-${tag.id}`"
                    class="filter-chip filter-chip-include active"
                    @click="removeIncludeTag(tag.id)"
                  >
                    {{ tag.name }} <span class="chip-close">×</span>
                  </button>
                </div>
                <div v-else class="filter-empty">Sin filtros de inclusión</div>
                <div class="filter-chip-list add-row">
                  <button
                    v-for="tag in includeAvailableTags"
                    :key="`add-include-${tag.id}`"
                    class="filter-chip filter-chip-include add"
                    @click="toggleIncludeTag(tag.id)"
                  >
                    + {{ tag.name }}
                  </button>
                </div>
              </div>

              <div class="filter-block">
                <span class="filter-block-title">Excluir</span>
                <div v-if="excludedTags.length" class="filter-chip-list">
                  <button
                    v-for="tag in excludedTags"
                    :key="`active-exclude-${tag.id}`"
                    class="filter-chip filter-chip-exclude active"
                    @click="removeExcludeTag(tag.id)"
                  >
                    {{ tag.name }} <span class="chip-close">×</span>
                  </button>
                </div>
                <div v-else class="filter-empty">Sin filtros de exclusión</div>
                <div class="filter-chip-list add-row">
                  <button
                    v-for="tag in excludeAvailableTags"
                    :key="`add-exclude-${tag.id}`"
                    class="filter-chip filter-chip-exclude add"
                    @click="toggleExcludeTag(tag.id)"
                  >
                    + {{ tag.name }}
                  </button>
                </div>
              </div>
            </div>
          </div>
          <button
            type="button"
            class="btn btn-sm btn-ghost btn-square folder-panel-toggle-btn"
            title="Mostrar u ocultar panel de carpeta"
            :disabled="!localSelectedFolderId"
            @click="onToggleFolderPanel"
          >
            <span
              class="folder-panel-toggle-chevron-wrap"
              :class="{ 'folder-panel-toggle-chevron-wrap--open': folderPanelOpen }"
              aria-hidden="true"
            >
              <ChevronLeft :size="18" class="folder-panel-toggle-chevron" />
            </span>
          </button>
        </div>
      </div>
    </div>

    <div class="images-content-scroll">
      <div v-if="loading && images.length === 0" class="text-center text-sm opacity-70 py-4">
        Cargando imágenes...
      </div>

      <div v-else-if="error" class="alert alert-error">
        <p>❌ Error: {{ error }}</p>
        <button @click="loadImages(true)" class="btn btn-sm btn-ghost mt-2">Reintentar</button>
      </div>

      <div v-else-if="images.length === 0" class="text-center text-sm opacity-70 py-4">
        No hay imágenes. Selecciona una carpeta y escanéala para ver las imágenes.
      </div>

      <template v-else>
        <div v-if="renamePickingMode" class="rename-pick-toolbar">
          <span class="text-sm opacity-80">{{ renamePickedIds.length }} seleccionadas</span>
          <button type="button" class="btn btn-xs btn-outline" @click="selectAllVisibleForRename">
            Seleccionar visibles
          </button>
          <button type="button" class="btn btn-xs btn-ghost" @click="clearRenamePicks">Limpiar</button>
        </div>
        <div class="images-grid">
          <ImageCard
            v-for="image in images"
            :key="image.id"
            :image="image"
            :pickable="renamePickingMode"
            :picked="renamePickedSet.has(image.id)"
            @showDetails="handleShowDetails"
            @expandImage="handleExpandImage"
            @imageMoved="handleImageMoved"
            @toggle-pick="toggleRenamePick"
          />
        </div>
      </template>

      <div v-if="hasMoreImages && !loadingMore" class="text-center py-4">
        <button @click="loadMoreImages" class="btn btn-sm btn-ghost">
          Cargar más ({{ total - offset }} restantes)
        </button>
      </div>
      <div v-else-if="loadingMore" class="text-center text-sm opacity-70 py-4">
        Cargando más imágenes...
      </div>
    </div>

    <!-- Image Viewer -->
    <ImageViewer ref="imageViewerRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { ChevronLeft, RefreshCw } from 'lucide-vue-next'
import * as galleryApi from '../api'
import type { Image, Folder, FolderTag } from '../api'
import ImageCard from './ImageCard.vue'
import ImageViewer from './ImageViewer.vue'
import type { ImageViewerData } from './ImageViewer.vue'

const props = defineProps<{
  selectedFolderId?: string
  selectedFolderNodeId?: number | null
  refreshTrigger?: number
  dashboardImageFilters?: {
    missing_checkpoint?: boolean
    missing_lora?: boolean
    checkpoint_name?: string
    lora_name?: string
    folder_type?: string
    token: number
  }
  folderPanelOpen?: boolean
  renamePickingMode?: boolean
  renamePickedIds?: number[]
}>()

const emit = defineEmits<{
  (e: 'showDetails', imageId: number): void
  (e: 'toggleFolderPanel'): void
  (e: 'update:renamePickedIds', ids: number[]): void
}>()

const folderPanelOpen = computed(() => props.folderPanelOpen ?? false)
const renamePickingMode = computed(() => props.renamePickingMode ?? false)
const renamePickedIds = computed(() => props.renamePickedIds ?? [])
const renamePickedSet = computed(() => new Set(renamePickedIds.value))

function toggleRenamePick(imageId: number) {
  const cur = new Set(renamePickedIds.value)
  if (cur.has(imageId)) cur.delete(imageId)
  else cur.add(imageId)
  emit('update:renamePickedIds', [...cur])
}

function selectAllVisibleForRename() {
  const cur = new Set(renamePickedIds.value)
  for (const img of images.value) cur.add(img.id)
  emit('update:renamePickedIds', [...cur])
}

function clearRenamePicks() {
  emit('update:renamePickedIds', [])
}

watch(renamePickingMode, (v) => {
  if (!v) emit('update:renamePickedIds', [])
})

const images = ref<Image[]>([])
const folders = ref<Folder[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const error = ref<string | null>(null)
const localSelectedFolderId = ref<string>(props.selectedFolderId || '')
const localSelectedFolderNodeId = ref<number | null>(props.selectedFolderNodeId ?? null)
const total = ref(0)
const offset = ref(0)
const limit = 50
const imageViewerRef = ref<InstanceType<typeof ImageViewer> | null>(null)
const allFolderTags = ref<FolderTag[]>([])
const TAG_FILTERS_SESSION_KEY = 'gallery:imageGrid:tagFilters'

const loadPersistedTagFilters = (): { include: number[]; exclude: number[] } => {
  if (typeof window === 'undefined') return { include: [], exclude: [] }
  try {
    const raw = window.sessionStorage.getItem(TAG_FILTERS_SESSION_KEY)
    if (!raw) return { include: [], exclude: [] }
    const parsed = JSON.parse(raw) as { include?: unknown; exclude?: unknown }
    const include = Array.isArray(parsed.include)
      ? parsed.include.filter((v): v is number => typeof v === 'number')
      : []
    const exclude = Array.isArray(parsed.exclude)
      ? parsed.exclude.filter((v): v is number => typeof v === 'number')
      : []
    return { include, exclude }
  } catch {
    return { include: [], exclude: [] }
  }
}

const persistedTagFilters = loadPersistedTagFilters()
const includeTagIds = ref<number[]>(persistedTagFilters.include)
const excludeTagIds = ref<number[]>(persistedTagFilters.exclude)
const showTagPanel = ref(false)
const filtersPopoverRef = ref<HTMLElement | null>(null)

function onToggleFolderPanel() {
  showTagPanel.value = false
  emit('toggleFolderPanel')
}

const hasMoreImages = computed(() => offset.value < total.value)
const includedTags = computed(() => allFolderTags.value.filter(tag => includeTagIds.value.includes(tag.id)))
const excludedTags = computed(() => allFolderTags.value.filter(tag => excludeTagIds.value.includes(tag.id)))
const includeAvailableTags = computed(() => allFolderTags.value.filter(tag => !includeTagIds.value.includes(tag.id)))
const excludeAvailableTags = computed(() => allFolderTags.value.filter(tag => !excludeTagIds.value.includes(tag.id)))

// Solo mostrar carpetas habilitadas en el dropdown
const enabledFolders = computed(() => folders.value.filter(f => f.enabled))

// Sincronizar selección externa de forma atómica para evitar combinaciones inválidas
watch(
  () => [props.selectedFolderId, props.selectedFolderNodeId] as const,
  ([newFolderId, newNodeId]) => {
    const normalizedFolderId = newFolderId || ''
    const normalizedNodeId = newNodeId ?? null
    const folderChanged = normalizedFolderId !== localSelectedFolderId.value
    const nodeChanged = normalizedNodeId !== localSelectedFolderNodeId.value
    if (!folderChanged && !nodeChanged) return
    localSelectedFolderId.value = normalizedFolderId
    localSelectedFolderNodeId.value = normalizedNodeId
    loadImages(true)
  },
  { immediate: true }
)

// Watch para refrescar cuando cambia el trigger
watch(() => props.refreshTrigger, () => {
  loadFolders()
  loadImages(true)
})

watch(
  () => props.dashboardImageFilters?.token,
  () => {
    loadImages(true)
  }
)

const loadFolders = async () => {
  try {
    folders.value = await galleryApi.listFolders()
  } catch (err) {
    console.error('Error al cargar carpetas para filtro:', err)
  }
}

const loadFolderTags = async () => {
  try {
    allFolderTags.value = await galleryApi.listFolderTags()
  } catch (err) {
    console.warn('No se pudieron cargar tags de carpeta', err)
  }
}

const loadImages = async (reset = true) => {
  if (reset) {
    offset.value = 0
    images.value = []
  }

  const currentLoadingRef = reset ? loading : loadingMore
  currentLoadingRef.value = true
  error.value = null

  try {
    const params: any = {
      limit,
      offset: offset.value
    }

    if (localSelectedFolderId.value) {
      params.folder_id = localSelectedFolderId.value
    }
    if (localSelectedFolderNodeId.value !== null) {
      params.folder_node_id = localSelectedFolderNodeId.value
    }
    if (includeTagIds.value.length > 0) {
      params.include_tag_ids = includeTagIds.value
    }
    if (excludeTagIds.value.length > 0) {
      params.exclude_tag_ids = excludeTagIds.value
    }
    if (props.dashboardImageFilters?.missing_checkpoint) {
      params.missing_checkpoint = true
    }
    if (props.dashboardImageFilters?.missing_lora) {
      params.missing_lora = true
    }
    if (props.dashboardImageFilters?.checkpoint_name) {
      params.checkpoint_name = props.dashboardImageFilters.checkpoint_name
    }
    if (props.dashboardImageFilters?.lora_name) {
      params.lora_name = props.dashboardImageFilters.lora_name
    }
    if (props.dashboardImageFilters?.folder_type) {
      params.folder_type = props.dashboardImageFilters.folder_type
    }

    const result = await galleryApi.listImages(params)
    
    if (reset) {
      images.value = result.images
    } else {
      images.value.push(...result.images)
    }
    
    total.value = result.total
    offset.value += result.images.length
  } catch (err: any) {
    if (err.code === 'ECONNREFUSED' || err.message?.includes('ECONNREFUSED') || !err.response) {
      error.value = 'No se pudo conectar al backend. Asegúrate de que el servidor esté corriendo en http://localhost:8005'
    } else {
      error.value = err.response?.data?.detail || err.message || 'Error al cargar imágenes'
    }
    console.error('Error al cargar imágenes:', err)
  } finally {
    currentLoadingRef.value = false
  }
}

const loadMoreImages = () => {
  if (!loadingMore.value && hasMoreImages.value) {
    loadImages(false)
  }
}

const handleShowDetails = (imageId: number) => {
  emit('showDetails', imageId)
}

const handleExpandImage = (imageId: number) => {
  // Encontrar el índice de la imagen clickeada
  const imageIndex = images.value.findIndex(img => img.id === imageId)
  if (imageIndex === -1) return
  
  // Convertir todas las imágenes al formato del visor
  const viewerImages: ImageViewerData[] = images.value.map(img => ({
    id: img.id,
    path: img.path
  }))
  
  // Abrir el visor en la imagen clickeada
  imageViewerRef.value?.open(viewerImages, imageIndex)
}

const handleImageMoved = (imageId: number) => {
  // Remover la imagen de la lista actual sin recargar todo
  const index = images.value.findIndex(img => img.id === imageId)
  if (index !== -1) {
    images.value.splice(index, 1)
    total.value = Math.max(0, total.value - 1)
    offset.value = Math.max(0, offset.value - 1)
  }
}

const handleFolderSelectChange = () => {
  localSelectedFolderNodeId.value = null
  loadImages(true)
}

const toggleIncludeTag = (tagId: number) => {
  if (includeTagIds.value.includes(tagId)) {
    includeTagIds.value = includeTagIds.value.filter(id => id !== tagId)
  } else {
    includeTagIds.value = [...includeTagIds.value, tagId]
    excludeTagIds.value = excludeTagIds.value.filter(id => id !== tagId)
  }
  loadImages(true)
}

const toggleExcludeTag = (tagId: number) => {
  if (excludeTagIds.value.includes(tagId)) {
    excludeTagIds.value = excludeTagIds.value.filter(id => id !== tagId)
  } else {
    excludeTagIds.value = [...excludeTagIds.value, tagId]
    includeTagIds.value = includeTagIds.value.filter(id => id !== tagId)
  }
  loadImages(true)
}

const clearTagFilters = () => {
  includeTagIds.value = []
  excludeTagIds.value = []
  loadImages(true)
}

const removeIncludeTag = (tagId: number) => {
  includeTagIds.value = includeTagIds.value.filter(id => id !== tagId)
  loadImages(true)
}

const removeExcludeTag = (tagId: number) => {
  excludeTagIds.value = excludeTagIds.value.filter(id => id !== tagId)
  loadImages(true)
}

// Exponer método refresh para ser llamado desde el padre
const refresh = () => {
  loadFolders()
  loadImages(true)
}

defineExpose({
  refresh
})

onMounted(() => {
  document.addEventListener('mousedown', handleOutsideFiltersClick)
  loadFolders()
  loadFolderTags()
  loadImages()
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleOutsideFiltersClick)
})

const handleOutsideFiltersClick = (event: MouseEvent) => {
  if (!showTagPanel.value) return
  const target = event.target as Node | null
  if (!target) return
  if (filtersPopoverRef.value?.contains(target)) return
  showTagPanel.value = false
}

const persistTagFilters = () => {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(
    TAG_FILTERS_SESSION_KEY,
    JSON.stringify({
      include: includeTagIds.value,
      exclude: excludeTagIds.value,
    })
  )
}

watch([includeTagIds, excludeTagIds], () => {
  persistTagFilters()
}, { deep: true })
</script>

<style scoped>
.image-grid-container {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.images-header {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  width: 100%;
  align-items: stretch;
  justify-content: flex-start;
  margin-bottom: 0.8rem;
  background: transparent;
  padding: 0;
}

.images-content-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 0.15rem;
}

.rename-pick-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.25rem 0.6rem;
  border-bottom: 1px solid var(--border-base-300);
  margin-bottom: 0.35rem;
}

.images-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 34px;
  width: 100%;
}

.folder-panel-toggle-btn {
  flex-shrink: 0;
}

.folder-panel-toggle-chevron-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.32s cubic-bezier(0.34, 1.25, 0.64, 1);
  transform: rotate(0deg);
}

.folder-panel-toggle-chevron-wrap--open {
  transform: rotate(180deg);
}

.folder-panel-toggle-chevron {
  display: block;
}

.images-topbar h2 {
  margin: 0;
}

.images-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
}

.filter-toggle-btn {
  min-width: 84px;
}

.filters-popover-anchor {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.filters-popover {
  position: absolute;
  top: calc(100% + 0.5rem);
  right: 0;
  width: min(300px, calc(100vw - 2rem));
  z-index: 40;
  border: 1px solid rgba(120, 132, 156, 0.25);
  border-radius: 0.75rem;
  background: linear-gradient(180deg, rgba(19, 24, 37, 0.98), rgba(15, 20, 31, 0.98));
  box-shadow: 0 18px 32px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(64, 43, 110, 0.2) inset;
  padding: 0.72rem 0.78rem 0.76rem;
  animation: tagPanelFadeIn 0.15s ease-out;
  display: flex;
  flex-direction: column;
  gap: 0.68rem;
  max-height: min(60vh, 460px);
  overflow-y: auto;
}

.filters-popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.filters-title {
  font-size: 0.84rem;
  font-weight: 650;
  letter-spacing: 0.01em;
  color: #eceff7;
}

.filters-clear-btn {
  border: none;
  background: transparent;
  color: #b7bfd1;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  padding: 0;
  transition: color 0.14s ease;
}

.filters-clear-btn:hover:not(:disabled) {
  color: #dac8ff;
}

.filters-clear-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.filters-divider {
  height: 1px;
  background: linear-gradient(90deg, rgba(117, 126, 147, 0.05), rgba(117, 126, 147, 0.35), rgba(117, 126, 147, 0.05));
}

.filter-block {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.filter-block-title {
  font-size: 0.72rem;
  font-weight: 600;
  color: #cbd3e4;
  letter-spacing: 0.02em;
}

.filter-empty {
  font-size: 0.7rem;
  color: #8f9ab2;
}

.filter-chip-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.filter-chip {
  border: 1px solid transparent;
  border-radius: 999px;
  background: rgba(38, 48, 66, 0.42);
  color: #d5dced;
  font-size: 0.72rem;
  padding: 0.23rem 0.56rem;
  line-height: 1.2;
  cursor: pointer;
  transition: all 0.15s ease;
}

.filter-chip:hover {
  border-color: rgba(172, 184, 205, 0.42);
  background: rgba(51, 63, 84, 0.6);
}

.filter-chip-include.active {
  border-color: rgba(160, 132, 255, 0.55);
  background: rgba(108, 67, 214, 0.28);
  color: #f1eaff;
}

.filter-chip-exclude.active {
  border-color: rgba(206, 135, 173, 0.5);
  background: rgba(120, 58, 88, 0.32);
  color: #ffe6f3;
}

.filter-chip.add {
  border-color: rgba(126, 138, 162, 0.35);
  background: rgba(30, 38, 54, 0.38);
  color: #c5cede;
}

.chip-close {
  margin-left: 0.24rem;
  font-size: 0.76rem;
  opacity: 0.82;
}

.add-row {
  margin-top: 0.08rem;
}

@media (max-width: 1100px) {
  .filters-popover {
    width: min(286px, calc(100vw - 1.5rem));
  }
}

@keyframes tagPanelFadeIn {
  from {
    opacity: 0;
    transform: translateY(-3px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

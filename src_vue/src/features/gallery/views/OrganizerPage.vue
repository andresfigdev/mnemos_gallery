<template>
  <section class="organizer-page">
    <div class="organizer-workspace">
      <main class="organizer-source-panel">
        <div v-if="notice" class="organizer-notice" :class="`organizer-notice--${notice.type}`">
          <CheckCircle2 v-if="notice.type === 'success'" :size="17" />
          <AlertTriangle v-else-if="notice.type === 'warning'" :size="17" />
          <AlertCircle v-else :size="17" />
          <span>{{ notice.message }}</span>
          <button type="button" @click="notice = null"><X :size="15" /></button>
        </div>

        <div class="organizer-panel-heading">
          <div>
            <h2>Imágenes de origen</h2>
            <span v-if="hasSource">{{ total }} disponibles · seleccionada desde el panel izquierdo</span>
            <span v-else>Elige una carpeta para comenzar</span>
          </div>
          <div class="organizer-selection-actions">
            <span v-if="selectedIds.size" class="organizer-selected-pill">
              {{ selectedIds.size }} seleccionada{{ selectedIds.size === 1 ? '' : 's' }}
            </span>
            <button v-if="images.length" type="button" @click="selectAllLoaded">
              {{ allLoadedSelected ? 'Quitar selección' : 'Seleccionar visibles' }}
            </button>
          </div>
        </div>

        <div class="organizer-images-scroll">
          <div v-if="loading && images.length === 0" class="organizer-state">
            <LoaderCircle :size="32" class="is-spinning" />
            <p>Cargando imágenes...</p>
          </div>
          <div v-else-if="!hasSource" class="organizer-state">
            <Images :size="44" />
            <h3>Selecciona la carpeta de origen</h3>
            <p>Verás sus imágenes aquí sin alterar la galería principal.</p>
          </div>
          <div v-else-if="images.length === 0" class="organizer-state">
            <ImageOff :size="44" />
            <h3>No hay imágenes</h3>
            <p>Selecciona otra carpeta desde el panel izquierdo.</p>
          </div>
          <div v-else class="organizer-image-grid">
            <article
              v-for="(image, index) in images"
              :key="image.id"
              class="organizer-image-card"
              :class="{ 'organizer-image-card--selected': selectedIds.has(image.id) }"
              draggable="true"
              @click="toggleSelection(image.id)"
              @dblclick.stop="openViewer(index)"
              @dragstart="startDrag($event, image.id)"
              @dragend="draggingIds = []"
            >
              <div class="organizer-image-preview">
                <img :src="getThumbnailUrl(image.id)" :alt="fileName(image.path)" loading="lazy" />
                <div class="organizer-check" aria-hidden="true">
                  <Check v-if="selectedIds.has(image.id)" :size="14" />
                </div>
                <button type="button" class="organizer-view-button" title="Ampliar" @click.stop="openViewer(index)">
                  <Maximize2 :size="15" />
                </button>
                <button
                  type="button"
                  class="organizer-delete-button"
                  title="Mover a papelera"
                  :disabled="deletingIds.has(image.id)"
                  @click.stop="deleteImage(image)"
                >
                  <LoaderCircle v-if="deletingIds.has(image.id)" :size="14" class="is-spinning" />
                  <Trash2 v-else :size="15" />
                </button>
              </div>
              <div class="organizer-image-meta">
                <strong :title="fileName(image.path)">{{ fileName(image.path) }}</strong>
                <span>{{ image.width || '?' }} × {{ image.height || '?' }}</span>
              </div>
            </article>
          </div>

          <div v-if="images.length < total" class="organizer-load-more">
            <button type="button" :disabled="loadingMore" @click="loadMore">
              <LoaderCircle v-if="loadingMore" :size="15" class="is-spinning" />
              Cargar más · {{ total - images.length }} restantes
            </button>
          </div>
        </div>
      </main>

      <aside class="organizer-destination-panel">
        <div v-if="organizer.configured" class="organizer-folder-search">
          <Search :size="15" />
          <input
            v-model="folderSearch"
            type="search"
            placeholder="Buscar carpeta ordenada..."
            aria-label="Buscar carpeta ordenada"
          />
          <button v-if="folderSearch" type="button" title="Limpiar búsqueda" @click="folderSearch = ''">
            <X :size="14" />
          </button>
        </div>

        <form v-if="createFormOpen" class="organizer-create-form" @submit.prevent="createFolder">
          <div>
            <span>Crear en</span>
            <strong>{{ createParentPath || 'Raíz de carpeta ordenada' }}</strong>
          </div>
          <input ref="createInputRef" v-model="newFolderName" maxlength="120" placeholder="Nombre de la carpeta" />
          <div class="organizer-create-actions">
            <button type="button" @click="closeCreateFolder">Cancelar</button>
            <button type="submit" class="is-primary" :disabled="creatingFolder || !newFolderName.trim()">
              {{ creatingFolder ? 'Creando...' : 'Crear' }}
            </button>
          </div>
        </form>

        <form v-if="renameFormOpen" class="organizer-create-form organizer-rename-form" @submit.prevent="renameFolder">
          <div>
            <span>Cambiar nombre de</span>
            <strong>{{ renamePath }}</strong>
          </div>
          <input
            ref="renameInputRef"
            v-model="renameFolderName"
            maxlength="120"
            placeholder="Nuevo nombre"
          />
          <p class="organizer-form-hint">
            Las imágenes de esta carpeta se renombrarán con el nuevo prefijo y correlativo. Las subcarpetas conservan sus propios nombres.
          </p>
          <div class="organizer-create-actions">
            <button type="button" @click="closeRenameFolder">Cancelar</button>
            <button type="submit" class="is-primary" :disabled="renamingFolder || !renameFolderName.trim()">
              {{ renamingFolder ? 'Renombrando...' : 'Cambiar nombre' }}
            </button>
          </div>
        </form>

        <div class="organizer-tree-scroll">
          <div v-if="organizer.configured && organizer.tree.length" class="organizer-tree-toolbar">
            <button type="button" title="Expandir todas las carpetas ordenadas" @click="setOrderedFoldersExpanded(true)">
              <ChevronsDown :size="14" />
              Todo
            </button>
            <button type="button" title="Contraer todas las carpetas ordenadas" @click="setOrderedFoldersExpanded(false)">
              <ChevronsUp :size="14" />
              Nada
            </button>
          </div>
          <div v-if="loadingOrganizer" class="organizer-state organizer-state--small">
            <LoaderCircle :size="26" class="is-spinning" />
            <p>Cargando estructura...</p>
          </div>
          <div v-else-if="!organizer.configured" class="organizer-state organizer-state--small">
            <FolderCog :size="42" />
            <h3>Falta la carpeta ordenada</h3>
            <p>{{ organizer.configuration_error || 'Configura “Ruta de Imágenes Ordenadas” en Settings para activar esta vista.' }}</p>
          </div>
          <div v-else-if="organizer.tree.length === 0" class="organizer-empty-destination" @dragover.prevent>
            <FolderTree :size="42" />
            <h3>Crea tu primera carpeta</h3>
            <p>Por ejemplo: Personajes, Generales o Prototipos.</p>
            <button type="button" @click="openCreateFolder('')">Crear carpeta</button>
          </div>
          <div v-else-if="visibleOrganizerTree.length === 0" class="organizer-state organizer-state--small">
            <Search :size="36" />
            <h3>Sin coincidencias</h3>
            <p>No hay carpetas ordenadas que coincidan con “{{ folderSearch }}”.</p>
          </div>
          <div v-else class="organizer-tree">
            <OrganizerFolderNode
              v-for="node in visibleOrganizerTree"
              :key="node.path"
              :node="node"
              :depth="0"
              :selected-path="selectedDestinationPath"
              :expand-all="orderedFoldersExpanded"
              :expansion-token="orderedFoldersExpansionToken"
              @select="handleOrderedFolderSelect"
              @create-child="openCreateFolder"
              @rename-folder="openRenameFolder"
              @drop-images="dropImages"
              @drop-source-folders="moveSourceFoldersToDestination"
            />
          </div>
        </div>

        <div class="organizer-drop-help" :class="{ 'organizer-drop-help--active': draggingIds.length > 0 }">
          <MoveRight :size="18" />
          <span v-if="draggingIds.length">
            Arrastra {{ draggingIds.length }} imagen{{ draggingIds.length === 1 ? '' : 'es' }} sobre una carpeta
          </span>
          <span v-else>Las imágenes se renombran automáticamente: carpeta_01, carpeta_02…</span>
        </div>
      </aside>
    </div>

    <div v-if="moving || movingSourceFolders" class="organizer-moving-overlay">
      <div>
        <LoaderCircle :size="28" class="is-spinning" />
        <strong>{{ movingSourceFolders ? 'Moviendo carpetas originales' : 'Organizando imágenes' }}</strong>
        <span>{{ movingSourceFolders ? 'Cortando y pegando la estructura completa…' : 'Moviendo archivos y miniaturas de forma segura…' }}</span>
      </div>
    </div>

    <ImageViewer ref="imageViewerRef" />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronsDown,
  ChevronsUp,
  FolderCog,
  FolderTree,
  ImageOff,
  Images,
  LoaderCircle,
  Maximize2,
  MoveRight,
  Search,
  Trash2,
  X,
} from 'lucide-vue-next'
import * as galleryApi from '../api'
import type { Image, OrganizerFolder, OrganizerState, SourceFolderNodeMoveItem } from '../api'
import ImageViewer from '../components/ImageViewer.vue'
import OrganizerFolderNode from '../components/OrganizerFolderNode.vue'
import { getSetting } from '../../settings/api'

const props = defineProps<{
  selectedFolderId?: string
  selectedFolderNodeId?: number | null
  refreshTrigger?: number
}>()

const PAGE_SIZE = 100
const getThumbnailUrl = galleryApi.getThumbnailUrl

const images = ref<Image[]>([])
const total = ref(0)
const selectedIds = ref<Set<number>>(new Set())
const draggingIds = ref<number[]>([])
const folderSearch = ref('')
const selectedDestinationPath = ref('')
const orderedFoldersExpanded = ref(true)
const orderedFoldersExpansionToken = ref(0)
const loadingOrganizer = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const moving = ref(false)
const movingSourceFolders = ref(false)
const deletingIds = ref<Set<number>>(new Set())
const shouldConfirmTrashMove = ref(true)
const createFormOpen = ref(false)
const createParentPath = ref('')
const newFolderName = ref('')
const creatingFolder = ref(false)
const createInputRef = ref<HTMLInputElement | null>(null)
const renameFormOpen = ref(false)
const renamePath = ref('')
const renameFolderName = ref('')
const renamingFolder = ref(false)
const renameInputRef = ref<HTMLInputElement | null>(null)
const imageViewerRef = ref<InstanceType<typeof ImageViewer> | null>(null)
const notice = ref<{ type: 'success' | 'warning' | 'error'; message: string } | null>(null)
const organizer = ref<OrganizerState>({
  configured: false,
  root_path: null,
  folder_id: null,
  configuration_error: null,
  tree: [],
  total_images: 0,
})

const hasSource = computed(() => Boolean(props.selectedFolderId))

const allLoadedSelected = computed(
  () => images.value.length > 0 && images.value.every(image => selectedIds.value.has(image.id))
)

function filterOrganizerFolders(nodes: OrganizerFolder[], term: string): OrganizerFolder[] {
  return nodes.flatMap((node) => {
    const children = filterOrganizerFolders(node.children, term)
    const matches = node.name.toLocaleLowerCase().includes(term)
      || node.path.toLocaleLowerCase().includes(term)
    return matches || children.length
      ? [{ ...node, children }]
      : []
  })
}

const visibleOrganizerTree = computed(() => {
  const term = folderSearch.value.trim().toLocaleLowerCase()
  return term ? filterOrganizerFolders(organizer.value.tree, term) : organizer.value.tree
})

function apiError(error: any, fallback: string): string {
  return error?.response?.data?.detail || error?.message || fallback
}

function showNotice(type: 'success' | 'warning' | 'error', message: string) {
  notice.value = { type, message }
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() || path
}

async function loadOrganizer() {
  loadingOrganizer.value = true
  try {
    organizer.value = await galleryApi.getOrganizer()
  } catch (error) {
    showNotice('error', apiError(error, 'No se pudo cargar la carpeta ordenada.'))
  } finally {
    loadingOrganizer.value = false
  }
}

async function loadImages(reset = true) {
  if (!props.selectedFolderId) {
    images.value = []
    total.value = 0
    selectedIds.value = new Set()
    return
  }
  const state = reset ? loading : loadingMore
  state.value = true
  try {
    const response = await galleryApi.listImages({
      folder_id: props.selectedFolderId,
      folder_node_id: props.selectedFolderNodeId ?? undefined,
      include_descendants: true,
      limit: PAGE_SIZE,
      offset: reset ? 0 : images.value.length,
    })
    images.value = reset ? response.images : [...images.value, ...response.images]
    total.value = response.total
    if (reset && selectedIds.value.size) {
      const availableIds = new Set(response.images.map(image => image.id))
      selectedIds.value = new Set(
        [...selectedIds.value].filter(imageId => availableIds.has(imageId)),
      )
    }
  } catch (error) {
    showNotice('error', apiError(error, 'No se pudieron cargar las imágenes.'))
  } finally {
    state.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadOrganizer(), loadImages(true), loadConfirmSetting()])
}

async function loadConfirmSetting() {
  try {
    const setting = await getSetting('confirm_trash_move')
    shouldConfirmTrashMove.value =
      setting.value === null
      || setting.value === undefined
      || setting.value.toLowerCase() === 'true'
  } catch (error: any) {
    shouldConfirmTrashMove.value = true
    if (error.response?.status !== 404) {
      console.error('No se pudo cargar la preferencia de confirmación de papelera:', error)
    }
  }
}

async function deleteImage(image: Image) {
  if (deletingIds.value.has(image.id)) return
  if (
    shouldConfirmTrashMove.value
    && !window.confirm(`¿Mover “${fileName(image.path)}” a la papelera?`)
  ) return

  deletingIds.value = new Set([...deletingIds.value, image.id])
  try {
    const response = await galleryApi.moveImageToTrash(image.id)
    showNotice(response.missing_original ? 'warning' : 'success', response.message)
    const nextSelection = new Set(selectedIds.value)
    nextSelection.delete(image.id)
    selectedIds.value = nextSelection
    await loadImages(true)
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
  } catch (error) {
    showNotice('error', apiError(error, 'No se pudo mover la imagen a la papelera.'))
  } finally {
    const next = new Set(deletingIds.value)
    next.delete(image.id)
    deletingIds.value = next
  }
}

function loadMore() {
  loadImages(false)
}

function toggleSelection(imageId: number) {
  const next = new Set(selectedIds.value)
  next.has(imageId) ? next.delete(imageId) : next.add(imageId)
  selectedIds.value = next
}

function selectAllLoaded() {
  selectedIds.value = allLoadedSelected.value
    ? new Set()
    : new Set(images.value.map(image => image.id))
}

function setOrderedFoldersExpanded(expanded: boolean) {
  orderedFoldersExpanded.value = expanded
  orderedFoldersExpansionToken.value += 1
}

function startDrag(event: DragEvent, imageId: number) {
  if (!selectedIds.value.has(imageId)) {
    const nextSelection = new Set(selectedIds.value)
    nextSelection.add(imageId)
    selectedIds.value = nextSelection
  }
  draggingIds.value = [...selectedIds.value]
  event.dataTransfer?.setData('application/x-mnemos-images', JSON.stringify(draggingIds.value))
  event.dataTransfer?.setData('text/plain', `${draggingIds.value.length} imágenes`)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

async function dropImages(destinationPath: string) {
  const ids = draggingIds.value.length ? [...draggingIds.value] : [...selectedIds.value]
  draggingIds.value = []
  if (!ids.length || moving.value) return
  moving.value = true
  selectedDestinationPath.value = destinationPath
  try {
    const response = await galleryApi.moveImagesWithOrganizer({
      image_ids: ids,
      destination_path: destinationPath,
    })
    organizer.value.tree = response.tree
    organizer.value.total_images = response.total_images
    selectedIds.value = new Set()
    showNotice('success', response.message)
    await loadImages(true)
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
  } catch (error) {
    showNotice('error', apiError(error, 'No se pudieron mover las imágenes.'))
  } finally {
    moving.value = false
  }
}

function handleOrderedFolderSelect(path: string) {
  selectedDestinationPath.value = path
}

async function moveSourceFoldersToDestination(payload: {
  sourceNodes: SourceFolderNodeMoveItem[]
  destinationPath: string
}) {
  if (!payload.sourceNodes.length || movingSourceFolders.value) return
  movingSourceFolders.value = true
  selectedDestinationPath.value = payload.destinationPath
  try {
    const response = await galleryApi.moveSourceFoldersToOrganizer({
      source_nodes: payload.sourceNodes,
      destination_path: payload.destinationPath,
    })
    organizer.value.tree = response.tree
    organizer.value.total_images = response.total_images
    showNotice('success', response.message)
    images.value = []
    total.value = 0
    selectedIds.value = new Set()
    window.dispatchEvent(new CustomEvent('sourceFolderSelectionInvalidated'))
    window.dispatchEvent(new CustomEvent('sourceFoldersMovedToOrganizer'))
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
  } catch (error) {
    showNotice('error', apiError(error, 'No se pudieron mover las carpetas originales.'))
  } finally {
    movingSourceFolders.value = false
  }
}

function openCreateFolder(parentPath: string) {
  closeRenameFolder()
  createParentPath.value = parentPath
  newFolderName.value = ''
  createFormOpen.value = true
  nextTick(() => createInputRef.value?.focus())
}

function openRootFolderForm() {
  if (!organizer.value.configured) {
    showNotice('error', organizer.value.configuration_error || 'Configura la carpeta ordenada en Settings antes de crear carpetas.')
    return
  }
  openCreateFolder('')
}

function openRenameFolder(node: OrganizerFolder) {
  closeCreateFolder()
  renamePath.value = node.path
  renameFolderName.value = node.name
  renameFormOpen.value = true
  nextTick(() => {
    renameInputRef.value?.focus()
    renameInputRef.value?.select()
  })
}

function closeRenameFolder() {
  renameFormOpen.value = false
  renamePath.value = ''
  renameFolderName.value = ''
}

async function renameFolder() {
  const newName = renameFolderName.value.trim()
  if (!newName || !renamePath.value || renamingFolder.value) return
  renamingFolder.value = true
  const previousPath = renamePath.value
  try {
    const response = await galleryApi.renameOrganizerFolder({
      path: previousPath,
      new_name: newName,
    })
    organizer.value.tree = response.tree
    organizer.value.total_images = response.total_images
    if (
      selectedDestinationPath.value === previousPath
      || selectedDestinationPath.value.startsWith(`${previousPath}/`)
    ) {
      selectedDestinationPath.value = response.new_path
        + selectedDestinationPath.value.slice(previousPath.length)
    }
    closeRenameFolder()
    showNotice('success', response.message)
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
  } catch (error) {
    showNotice('error', apiError(error, 'No se pudo cambiar el nombre de la carpeta.'))
  } finally {
    renamingFolder.value = false
  }
}

function closeCreateFolder() {
  createFormOpen.value = false
  newFolderName.value = ''
}

async function createFolder() {
  const name = newFolderName.value.trim()
  if (!name || creatingFolder.value) return
  creatingFolder.value = true
  try {
    const response = await galleryApi.createOrganizerFolder({
      name,
      parent_path: createParentPath.value,
    })
    organizer.value.tree = response.tree
    organizer.value.total_images = response.total_images
    selectedDestinationPath.value = response.created_path
    closeCreateFolder()
    showNotice('success', `Carpeta “${name}” creada.`)
  } catch (error) {
    showNotice('error', apiError(error, 'No se pudo crear la carpeta.'))
  } finally {
    creatingFolder.value = false
  }
}

function openViewer(index: number) {
  imageViewerRef.value?.open(
    images.value.map(image => ({ id: image.id, path: image.path })),
    index,
  )
}

watch(
  () => [props.selectedFolderId, props.selectedFolderNodeId] as const,
  async () => {
    selectedIds.value = new Set()
    await loadImages(true)
  },
)
watch(() => props.refreshTrigger, () => loadImages(true))
watch(folderSearch, (value, previous) => {
  if (value.trim() && !previous.trim()) setOrderedFoldersExpanded(true)
})

onMounted(() => {
  window.addEventListener('organizerCreateRootFolder', openRootFolderForm)
  refreshAll()
})

onUnmounted(() => {
  window.removeEventListener('organizerCreateRootFolder', openRootFolderForm)
})
</script>

<style scoped>
.organizer-page {
  position: relative;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at 80% -20%, rgba(124, 58, 237, 0.12), transparent 34%),
    var(--bg-base-100);
  color: #e5e7eb;
}

.organizer-panel-heading span {
  color: #8490a5;
  font-size: 12px;
}

.organizer-create-form input {
  height: 36px;
  border: 1px solid #303747;
  border-radius: 8px;
  padding: 0 10px;
  background: #141824;
  color: #f8fafc;
  outline: none;
}

.organizer-create-form input:focus {
  border-color: #8b5cf6;
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.13);
}

.organizer-notice {
  margin: 10px 18px 0;
  padding: 9px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid;
  border-radius: 9px;
  font-size: 12px;
}

.organizer-notice--success {
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(34, 197, 94, 0.09);
  color: #bbf7d0;
}

.organizer-notice--error {
  border-color: rgba(248, 113, 113, 0.35);
  background: rgba(239, 68, 68, 0.09);
  color: #fecaca;
}

.organizer-notice--warning {
  border-color: rgba(245, 158, 11, 0.38);
  background: rgba(245, 158, 11, 0.1);
  color: #fde68a;
}

.organizer-notice span {
  flex: 1;
}

.organizer-notice button {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.organizer-workspace {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(480px, 1fr) minmax(310px, 390px);
}

.organizer-source-panel,
.organizer-destination-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.organizer-destination-panel {
  border-left: 1px solid var(--border-base-300);
  background: rgba(13, 16, 24, 0.7);
}

.organizer-panel-heading {
  min-height: 64px;
  padding: 13px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(42, 48, 64, 0.72);
}

.organizer-panel-heading h2 {
  margin-bottom: 2px;
  font-size: 15px;
}

.organizer-selection-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.organizer-selection-actions button,
.organizer-create-actions button,
.organizer-empty-destination button,
.organizer-load-more button {
  border: 1px solid #303747;
  border-radius: 7px;
  padding: 6px 9px;
  background: #171b27;
  color: #cbd5e1;
  font-size: 11px;
  cursor: pointer;
}

.organizer-selected-pill {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(139, 92, 246, 0.18);
  color: #c4b5fd !important;
  font-weight: 650;
}

.organizer-images-scroll,
.organizer-tree-scroll {
  min-height: 0;
  flex: 1;
  overflow: auto;
}

.organizer-images-scroll {
  padding: 14px 18px 20px;
}

.organizer-image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(145px, 1fr));
  gap: 11px;
}

.organizer-image-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #293040;
  border-radius: 10px;
  background: #141824;
  cursor: grab;
  user-select: none;
  transition: 140ms ease;
}

.organizer-image-card:hover {
  border-color: #566076;
  transform: translateY(-1px);
}

.organizer-image-card--selected {
  border-color: #8b5cf6;
  box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.18);
}

.organizer-image-preview {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  background: #0b0e15;
}

.organizer-image-preview img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.organizer-check {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 21px;
  height: 21px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.55);
  border-radius: 6px;
  background: rgba(8, 11, 18, 0.7);
}

.organizer-image-card--selected .organizer-check {
  border-color: #8b5cf6;
  background: #8b5cf6;
  color: white;
}

.organizer-view-button {
  position: absolute;
  top: 8px;
  right: 42px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 7px;
  background: rgba(8, 11, 18, 0.76);
  color: white;
  cursor: pointer;
  opacity: 0;
  transition: 140ms ease;
}

.organizer-delete-button {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(248, 113, 113, 0.28);
  border-radius: 7px;
  background: rgba(8, 11, 18, 0.76);
  color: #fca5a5;
  cursor: pointer;
  opacity: 0;
  transition: 140ms ease;
}

.organizer-image-card:hover .organizer-delete-button {
  opacity: 1;
}

.organizer-image-card:hover .organizer-view-button {
  opacity: 1;
}

.organizer-image-meta {
  padding: 9px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.organizer-image-meta strong {
  overflow: hidden;
  color: #e8ecf4;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.organizer-image-meta span {
  color: #78849a;
  font-size: 10px;
}

.organizer-state,
.organizer-empty-destination {
  min-height: 310px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 9px;
  color: #64748b;
  text-align: center;
}

.organizer-state h3,
.organizer-empty-destination h3 {
  color: #cbd5e1;
  font-size: 14px;
}

.organizer-state p,
.organizer-empty-destination p {
  max-width: 300px;
  color: #7f8ba0;
  font-size: 12px;
  line-height: 1.5;
}

.organizer-state--small {
  min-height: 240px;
  padding: 28px;
}

.organizer-load-more {
  padding: 18px 0 2px;
  text-align: center;
}

.organizer-load-more button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.organizer-folder-search {
  margin: 10px 11px 0;
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  border: 1px solid #303747;
  border-radius: 7px;
  background: #141824;
  color: #7f8ba0;
}

.organizer-folder-search:focus-within {
  border-color: #8b5cf6;
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12);
}

.organizer-folder-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: #e5e7eb;
  font-size: 11px;
}

.organizer-folder-search input::placeholder {
  color: #6f7b90;
}

.organizer-folder-search input::-webkit-search-cancel-button {
  display: none;
}

.organizer-folder-search button {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
}

.organizer-folder-search button:hover {
  background: rgba(148, 163, 184, 0.1);
  color: #e2e8f0;
}

.organizer-create-form {
  margin: 10px 13px 0;
  padding: 11px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  border: 1px solid rgba(139, 92, 246, 0.34);
  border-radius: 9px;
  background: rgba(139, 92, 246, 0.07);
}

.organizer-create-form > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 10px;
}

.organizer-create-form span {
  color: #7f8ba0;
}

.organizer-create-form strong {
  overflow: hidden;
  color: #c4b5fd;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.organizer-form-hint {
  color: #8d98ab;
  font-size: 10px;
  line-height: 1.45;
}

.organizer-create-actions {
  display: flex;
  justify-content: flex-end;
  gap: 7px;
}

.organizer-create-actions .is-primary {
  border-color: #8b5cf6;
  background: #7c3aed;
  color: white;
}

.organizer-tree-scroll {
  padding: 10px 11px;
}

.organizer-tree-toolbar {
  position: sticky;
  top: -10px;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: -2px 0 8px;
  padding: 8px 1px 7px;
  border-bottom: 1px solid rgba(42, 48, 64, 0.82);
  background: #0e1119;
}

.organizer-tree-toolbar button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid #303747;
  border-radius: 7px;
  padding: 5px 8px;
  background: #171b27;
  color: #cbd5e1;
  font-size: 10px;
  font-weight: 650;
  cursor: pointer;
}

.organizer-tree-toolbar button:hover {
  border-color: rgba(139, 92, 246, 0.55);
  background: rgba(139, 92, 246, 0.14);
  color: #ede9fe;
}

.organizer-empty-destination {
  min-height: 260px;
  padding: 24px;
}

.organizer-empty-destination button {
  border-color: rgba(139, 92, 246, 0.4);
  color: #c4b5fd;
}

.organizer-drop-help {
  min-height: 48px;
  padding: 9px 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-top: 1px solid #252b39;
  color: #7f8ba0;
  font-size: 10px;
  line-height: 1.35;
}

.organizer-drop-help--active {
  background: rgba(34, 197, 94, 0.07);
  color: #86efac;
}

.organizer-moving-overlay {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(7, 9, 14, 0.68);
  backdrop-filter: blur(3px);
}

.organizer-moving-overlay > div {
  min-width: 280px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  border: 1px solid #343b4c;
  border-radius: 12px;
  background: #151925;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
}

.organizer-moving-overlay strong {
  font-size: 14px;
}

.organizer-moving-overlay span {
  color: #8d98ab;
  font-size: 11px;
}

.is-spinning {
  animation: organizer-spin 0.9s linear infinite;
}

@keyframes organizer-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 1050px) {
  .organizer-workspace {
    grid-template-columns: minmax(420px, 1fr) 320px;
  }

  .organizer-image-grid {
    grid-template-columns: repeat(auto-fill, minmax(125px, 1fr));
  }
}
</style>

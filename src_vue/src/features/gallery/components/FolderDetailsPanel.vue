<template>
  <div class="folder-details-embedded">
    <div class="folder-panel-header">
      <h2 class="folder-panel-title">Carpeta</h2>
      <button type="button" class="btn btn-ghost btn-sm btn-circle" title="Ocultar panel" @click="emit('close')">
        <X :size="20" />
      </button>
    </div>

    <div class="folder-panel-body">
      <div v-if="loading" class="folder-panel-loading">
        <span class="loading loading-spinner loading-lg" />
      </div>
      <div v-else-if="error" class="alert alert-error folder-panel-alert">
        <AlertCircle :size="20" />
        <span>{{ error }}</span>
      </div>
      <template v-else-if="folder && currentNode">
        <div class="folder-panel-content">
          <div class="folder-tabs" role="tablist" aria-label="Secciones del panel de carpeta">
            <button
              type="button"
              class="folder-tab"
              :class="{ 'folder-tab--active': activeTab === 'summary' }"
              @click="activeTab = 'summary'"
            >
              Resumen
            </button>
            <button
              type="button"
              class="folder-tab"
              :class="{ 'folder-tab--active': activeTab === 'tags' }"
              @click="activeTab = 'tags'"
            >
              Tags
            </button>
            <button
              type="button"
              class="folder-tab"
              :class="{ 'folder-tab--active': activeTab === 'actions' }"
              @click="activeTab = 'actions'"
            >
              Acciones
            </button>
          </div>

        <header class="folder-panel-hero">
          <h3 class="folder-hero-title">{{ displayTitle }}</h3>
          <p v-if="subtitle" class="folder-hero-sub">{{ subtitle }}</p>
        </header>

        <section v-if="activeTab === 'summary'" class="folder-section">
          <h4 class="folder-section-title">Ruta</h4>
          <p class="folder-path mono">{{ diskPath }}</p>
          <div class="folder-summary-block">
            <h4 class="folder-section-title">Resumen</h4>
            <ul class="folder-summary-list">
              <li>{{ imageTotal }} imágenes</li>
              <li>{{ ownTagCount }} tags</li>
              <li>{{ inheritanceLabel }}</li>
              <li>Nomenclatura actual: <span class="mono">{{ nomenclatureSummary }}</span></li>
              <li>Última sincronización: {{ lastScanLabel }}</li>
            </ul>
          </div>
        </section>

        <section v-if="activeTab === 'tags'" class="folder-section">
          <h4 class="folder-section-title">Tags</h4>
          <p v-if="currentNode" class="folder-tag-inherit folder-muted">
            Heredados (solo lectura): {{ getInheritedTagNames(currentNode).join(', ') || 'ninguno' }}
          </p>
          <div class="folder-tag-chips">
            <span v-for="t in currentNode.tags || []" :key="t.id" class="folder-tag-chip">{{ t.name }}</span>
            <span v-if="!currentNode.tags?.length" class="folder-muted">Sin tags propios</span>
          </div>
          <div class="folder-actions-row">
            <button type="button" class="btn btn-xs btn-ghost" :disabled="!currentNode" @click="openTagEditor">+ Agregar tag</button>
            <button type="button" class="btn btn-xs btn-ghost" :disabled="!currentNode" @click="openTagEditor">Editar tags</button>
          </div>

          <div v-if="tagEditorOpen && currentNode" class="tree-node-editor integrated-editor" @click.stop>
            <div class="tree-node-editor-title">Editar tags del nodo</div>
            <div class="tree-node-editor-sub">
              Heredados: {{ getInheritedTagNames(currentNode).join(', ') || 'sin tags' }}
            </div>

            <div v-if="tagDraft.length > 0" class="tree-node-draft-list">
              <span v-for="tag in tagDraft" :key="`${currentNode.id}-${tag}`" class="tree-node-draft-tag">
                {{ tag }}
                <button type="button" @click.stop="removeDraftTag(tag)">×</button>
              </span>
            </div>

            <div class="tree-node-editor-add">
              <input
                v-model="newTagInputValue"
                type="text"
                class="input input-xs input-bordered w-full"
                placeholder="nuevo tag..."
                @keyup.enter="addDraftTagFromInput"
              />
              <button type="button" class="btn btn-xs btn-ghost" @click.stop="addDraftTagFromInput">+</button>
            </div>

            <div v-if="availableTags.length > 0" class="tree-node-suggestions">
              <button
                v-for="tag in availableTags"
                :key="`panel-suggestion-${currentNode.id}-${tag.id}`"
                type="button"
                class="btn btn-ghost btn-xs"
                @click.stop="addDraftTag(tag.name)"
              >
                {{ tag.name }}
              </button>
            </div>

            <div class="tree-node-editor-actions">
              <button type="button" class="btn btn-xs btn-ghost" @click.stop="closeTagEditor">Cancelar</button>
              <button type="button" class="btn btn-xs btn-primary" :disabled="savingTags" @click.stop="saveNodeTags">
                {{ savingTags ? 'Guardando...' : 'Guardar' }}
              </button>
            </div>
          </div>
        </section>

        <section v-if="activeTab === 'actions'" class="folder-section">
          <h4 class="folder-section-title">Nomenclatura de archivos</h4>
          <p class="folder-muted folder-nom-hint">
            Define nombre base y ancho del número (ej. base <span class="mono">Alice</span> y 4 →
            <span class="mono">Alice_0001</span>). Sin esto, el renombrado no está disponible.
          </p>
          <div class="folder-nom-fields">
            <label class="folder-nom-label">
              <span>Nombre base</span>
              <input v-model="namingBaseDraft" type="text" class="input input-bordered input-sm w-full mono" autocomplete="off" />
            </label>
            <label class="folder-nom-label">
              <span>Dígitos del índice</span>
              <input
                v-model="namingWidthDraft"
                type="number"
                min="1"
                max="12"
                class="input input-bordered input-sm w-full"
                autocomplete="off"
              />
            </label>
          </div>
          <div class="folder-actions-row folder-nom-actions">
            <button type="button" class="btn btn-xs btn-primary" :disabled="savingNomenclature" @click="handleSaveNomenclature">
              Guardar nomenclatura
            </button>
            <button
              type="button"
              class="btn btn-xs btn-ghost"
              :disabled="savingNomenclature || !hasNomenclatureConfigured"
              @click="handleClearNomenclature"
            >
              Quitar
            </button>
          </div>

          <div class="folder-actions-stack">
            <button type="button" class="btn btn-sm btn-outline w-full justify-start" :disabled="openingFolder" @click="handleOpenInExplorer">
              <FolderOpen :size="16" />
              Abrir carpeta
            </button>
            <button type="button" class="btn btn-sm btn-outline w-full justify-start" :disabled="scanning" @click="handleRefreshScan">
              <RefreshCw :size="16" :class="{ 'animate-spin': scanning }" />
              Refrescar
            </button>
            <button
              type="button"
              class="btn btn-sm btn-outline w-full justify-start"
              :disabled="!hasNomenclatureConfigured"
              @click="toggleRenameFlow"
            >
              {{ showRenameFlow ? 'Ocultar renombrado' : 'Renombrar imágenes' }}
            </button>
            <button type="button" class="btn btn-sm btn-outline w-full justify-start" disabled title="Próximamente">Mover imágenes</button>
          </div>

          <RenameImagesDialog
            v-if="showRenameFlow && hasNomenclatureConfigured"
            class="folder-rename-embedded"
            :folder-id="folder.id"
            :folder-node-id="currentNode.id"
            :picked-image-ids="renamePickedIds"
            @start-picking="emit('update:renamePickingMode', true)"
            @stop-picking="emit('update:renamePickingMode', false)"
            @applied="handleRenameApplied"
            @close="closeRenameFlow"
          />

          <div class="folder-danger-zone">
            <h4 class="folder-section-title">Zona peligrosa</h4>
            <button
              v-if="isRootNode"
              type="button"
              class="btn btn-sm btn-error btn-outline w-full"
              :disabled="deleting"
              @click="handleDeleteFolder"
            >
              Quitar carpeta del registro
            </button>
            <button
              v-else
              type="button"
              class="btn btn-sm btn-error btn-outline w-full"
              :disabled="deleting"
              @click="handleDeleteCurrentNode"
            >
              Quitar subcarpeta del registro
            </button>
            <p class="folder-muted folder-danger-hint">No se eliminan archivos físicos del disco; solo registros de la base de datos.</p>
          </div>
        </section>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { X, AlertCircle, FolderOpen, RefreshCw } from 'lucide-vue-next'
import RenameImagesDialog from './RenameImagesDialog.vue'
import {
  listFolders,
  getFolderTree,
  listImages,
  scanFolder,
  deleteFolder,
  deleteFolderNodeRegistration,
  openFolderInExplorer,
  updateFolderNodeNomenclature,
  listFolderTags,
  updateFolderNodeTags,
  type Folder,
  type FolderNode,
  type FolderTag,
} from '../api'

const props = defineProps<{
  folderId: string
  folderNodeId: number | null
  renamePickedIds?: number[]
}>()

const emit = defineEmits<{
  close: []
  'update:renamePickingMode': [value: boolean]
  'update:renamePickedIds': [ids: number[]]
  renameApplied: []
}>()

const loading = ref(false)
const error = ref<string | null>(null)
const folder = ref<Folder | null>(null)
const currentNode = ref<FolderNode | null>(null)
const imageTotal = ref(0)
const scanning = ref(false)
const openingFolder = ref(false)
const deleting = ref(false)
const namingBaseDraft = ref('')
const namingWidthDraft = ref('')
const savingNomenclature = ref(false)
const activeTab = ref<'summary' | 'tags' | 'actions'>('summary')
const showRenameFlow = ref(false)

const availableTags = ref<FolderTag[]>([])
const tagEditorOpen = ref(false)
const tagDraft = ref<string[]>([])
const newTagInputValue = ref('')
const savingTags = ref(false)

const renamePickedIds = computed(() => props.renamePickedIds ?? [])

function getRootNode(nodes: FolderNode[]): FolderNode | null {
  if (!nodes.length) return null
  const exact = nodes.find((n) => n.rel_path === '')
  return exact || nodes[0] || null
}

function findNodeById(nodes: FolderNode[], id: number): FolderNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    if (n.children?.length) {
      const inner = findNodeById(n.children, id)
      if (inner) return inner
    }
  }
  return null
}

function joinDiskPath(rootPath: string, relPath: string): string {
  if (!relPath) return rootPath
  const sep = rootPath.includes('\\') ? '\\' : '/'
  const tail = relPath
    .replace(/^\//, '')
    .split('/')
    .join(sep)
    .split('\\')
    .join(sep)
  return rootPath.replace(/[/\\]+$/, '') + sep + tail
}

const displayTitle = computed(() => {
  if (!currentNode.value || !folder.value) return ''
  const isLogicalRoot = currentNode.value.rel_path === ''
  return isLogicalRoot ? folder.value.name : currentNode.value.name
})

const subtitle = computed(() => {
  if (!currentNode.value || !folder.value) return ''
  if (currentNode.value.rel_path === '') return ''
  return `Subcarpeta de ${folder.value.name}`
})

const diskPath = computed(() => {
  if (!folder.value || !currentNode.value) return ''
  return joinDiskPath(folder.value.path, currentNode.value.rel_path || '')
})

const ownTagCount = computed(() => currentNode.value?.tags?.length ?? currentNode.value?.tag_ids?.length ?? 0)

const inheritanceActive = computed(() => {
  const n = currentNode.value
  if (!n) return false
  const own = [...(n.tag_ids || [])].sort((a, b) => a - b).join(',')
  const eff = [...(n.effective_tag_ids || [])].sort((a, b) => a - b).join(',')
  return own !== eff
})

const inheritanceLabel = computed(() => (inheritanceActive.value ? 'Herencia activa' : 'Sin herencia de tags'))

const nomenclatureSummary = computed(() => {
  const n = currentNode.value
  if (!n) return '—'
  const base = (n.naming_base || '').trim()
  const w = n.naming_number_width
  if (!base || w == null) return '—'
  const sample = `${base}_${String(1).padStart(w, '0')}`
  return `${base} · ${w} dígitos (ej. ${sample})`
})

const hasNomenclatureConfigured = computed(() => {
  const n = currentNode.value
  if (!n) return false
  const base = (n.naming_base || '').trim()
  const w = n.naming_number_width
  return Boolean(base && w != null && w >= 1)
})

function syncNomenclatureDrafts() {
  const n = currentNode.value
  if (!n) {
    namingBaseDraft.value = ''
    namingWidthDraft.value = ''
    return
  }
  namingBaseDraft.value = (n.naming_base || '').trim()
  namingWidthDraft.value = n.naming_number_width != null ? String(n.naming_number_width) : ''
}

watch(currentNode, syncNomenclatureDrafts, { immediate: true })

watch(activeTab, (tab) => {
  if (tab !== 'actions' && showRenameFlow.value) {
    closeRenameFlow()
  }
  if (tab !== 'tags') {
    closeTagEditor()
  }
})

const lastScanLabel = computed(() => {
  const raw = folder.value?.last_scan_at
  if (!raw) return '—'
  try {
    return new Date(raw).toLocaleString()
  } catch {
    return raw
  }
})

const isRootNode = computed(() => {
  const n = currentNode.value
  return !!n && n.rel_path === ''
})

function getInheritedTagNames(node: FolderNode | null): string[] {
  if (!node) return []
  const own = new Set((node.tags || []).map((t) => t.name.toLowerCase()))
  return (node.effective_tags || [])
    .map((t) => t.name)
    .filter((name) => !own.has(name.toLowerCase()))
}

async function loadAvailableTags() {
  try {
    availableTags.value = await listFolderTags()
  } catch (e) {
    console.warn('No se pudieron cargar tags disponibles', e)
  }
}

function openTagEditor() {
  const n = currentNode.value
  if (!n) return
  tagEditorOpen.value = true
  tagDraft.value = [...(n.tags || []).map((t) => t.name)]
  newTagInputValue.value = ''
}

function closeTagEditor() {
  tagEditorOpen.value = false
}

function addDraftTag(tagName: string) {
  const normalized = tagName.trim().toLowerCase()
  if (!normalized) return
  const current = tagDraft.value
  if (current.includes(normalized)) return
  tagDraft.value = [...current, normalized]
}

function removeDraftTag(tagName: string) {
  tagDraft.value = tagDraft.value.filter((t) => t !== tagName)
}

function addDraftTagFromInput() {
  const value = newTagInputValue.value.trim()
  if (!value) return
  addDraftTag(value)
  newTagInputValue.value = ''
}

async function saveNodeTags() {
  const n = currentNode.value
  if (!n) return
  savingTags.value = true
  try {
    const tags = tagDraft.value.map((t) => t.trim()).filter(Boolean)
    await updateFolderNodeTags(n.id, { tags })
    closeTagEditor()
    await loadAvailableTags()
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    await loadPanelData()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    alert(err.response?.data?.detail || err.message || 'No se pudieron guardar los tags.')
  } finally {
    savingTags.value = false
  }
}

function toggleRenameFlow() {
  showRenameFlow.value = !showRenameFlow.value
  if (!showRenameFlow.value) {
    emit('update:renamePickingMode', false)
  }
}

function closeRenameFlow() {
  showRenameFlow.value = false
  emit('update:renamePickingMode', false)
}

function handleRenameApplied() {
  showRenameFlow.value = false
  emit('update:renamePickingMode', false)
  emit('update:renamePickedIds', [])
  emit('renameApplied')
  window.dispatchEvent(new CustomEvent('galleryRefresh'))
  window.dispatchEvent(new CustomEvent('refreshFolders'))
}

async function loadPanelData() {
  closeTagEditor()
  loading.value = true
  error.value = null
  folder.value = null
  currentNode.value = null
  imageTotal.value = 0

  const data = { folderId: props.folderId, folderNodeId: props.folderNodeId }

  try {
    const folders = await listFolders()
    const f = folders.find((x) => x.id === data.folderId)
    if (!f) {
      error.value = 'Carpeta no encontrada'
      return
    }
    folder.value = f

    const tree = await getFolderTree(data.folderId)
    const roots = tree.nodes || []

    const root = getRootNode(roots)
    let node: FolderNode | null = null
    if (data.folderNodeId == null && root) {
      node = root
    } else if (data.folderNodeId != null) {
      node = findNodeById(roots, data.folderNodeId)
    }
    if (!node) {
      error.value = 'Nodo de carpeta no encontrado'
      return
    }
    currentNode.value = node

    const imgParams: { folder_id: string; folder_node_id?: number; limit: number; offset: number } = {
      folder_id: data.folderId,
      limit: 1,
      offset: 0,
    }
    if (data.folderNodeId != null) {
      imgParams.folder_node_id = data.folderNodeId
    }
    const imgRes = await listImages(imgParams)
    imageTotal.value = imgRes.total

    await loadAvailableTags()
  } catch (e: any) {
    console.error(e)
    error.value = e?.response?.data?.detail || e?.message || 'Error al cargar datos de la carpeta'
  } finally {
    loading.value = false
  }
}

function handleEscape(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

watch(
  () => [props.folderId, props.folderNodeId] as const,
  () => {
    closeTagEditor()
    if (props.folderId) loadPanelData()
  },
  { immediate: true }
)

onMounted(() => {
  document.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleEscape)
})

async function handleOpenInExplorer() {
  if (!diskPath.value) return
  openingFolder.value = true
  try {
    await openFolderInExplorer(diskPath.value)
  } catch (e: any) {
    console.error(e)
    alert(e?.response?.data?.detail || e?.message || 'No se pudo abrir la carpeta')
  } finally {
    openingFolder.value = false
  }
}

async function handleRefreshScan() {
  if (!folder.value) return
  scanning.value = true
  try {
    await scanFolder({
      folder_id: folder.value.id,
      recursive: true,
      create_records: true,
    })
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
    await loadPanelData()
  } catch (e: any) {
    console.error(e)
    alert(e?.response?.data?.detail || e?.message || 'Error al escanear')
  } finally {
    scanning.value = false
  }
}

async function handleSaveNomenclature() {
  if (!folder.value || !currentNode.value) return
  const base = namingBaseDraft.value.trim()
  const w = parseInt(String(namingWidthDraft.value).trim(), 10)
  if (!base || Number.isNaN(w) || w < 1 || w > 12) {
    alert('Indica nombre base y un ancho numérico entre 1 y 12.')
    return
  }
  savingNomenclature.value = true
  try {
    await updateFolderNodeNomenclature(folder.value.id, currentNode.value.id, {
      naming_base: base,
      naming_number_width: w,
    })
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    await loadPanelData()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    alert(err.response?.data?.detail || err.message || 'Error al guardar')
  } finally {
    savingNomenclature.value = false
  }
}

async function handleClearNomenclature() {
  if (!folder.value || !currentNode.value) return
  savingNomenclature.value = true
  try {
    await updateFolderNodeNomenclature(folder.value.id, currentNode.value.id, {
      naming_base: null,
      naming_number_width: null,
    })
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    await loadPanelData()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    alert(err.response?.data?.detail || err.message || 'Error al quitar nomenclatura')
  } finally {
    savingNomenclature.value = false
  }
}

async function handleDeleteFolder() {
  if (!folder.value || !isRootNode.value) return
  if (!confirm(`¿Quitar la carpeta "${folder.value.name}" del registro de BD y sus imágenes indexadas?`)) return
  deleting.value = true
  try {
    await deleteFolder(folder.value.id)
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
    emit('close')
  } catch (e: any) {
    console.error(e)
    alert(e?.response?.data?.detail || e?.message || 'Error al eliminar')
  } finally {
    deleting.value = false
  }
}

async function handleDeleteCurrentNode() {
  if (!folder.value || !currentNode.value || isRootNode.value) return
  const label = currentNode.value.name || currentNode.value.rel_path || `Nodo ${currentNode.value.id}`
  if (
    !confirm(
      `¿Quitar la subcarpeta "${label}" del registro de BD (incluyendo sus subcarpetas lógicas e imágenes indexadas)?`
    )
  ) {
    return
  }
  deleting.value = true
  try {
    await deleteFolderNodeRegistration(folder.value.id, currentNode.value.id)
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
    emit('close')
  } catch (e: any) {
    console.error(e)
    alert(e?.response?.data?.detail || e?.message || 'Error al quitar subcarpeta del registro')
  } finally {
    deleting.value = false
  }
}

defineExpose({ reload: loadPanelData })
</script>

<style scoped>
.folder-details-embedded {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  width: 320px;
  max-width: 100%;
  background-color: var(--bg-base-100);
  overflow: hidden;
}

.folder-panel-header {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-base-300);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  background-color: var(--bg-base-100);
}

.folder-panel-title {
  font-size: 1rem;
  font-weight: 600;
}

.folder-panel-body {
  padding: 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border-base-300) transparent;
}

.folder-panel-content {
  padding: 1rem 1rem 1.5rem;
}

.folder-tabs {
  display: flex;
  gap: 0.25rem;
  margin-bottom: 0.9rem;
  padding: 0.2rem;
  border: 1px solid var(--border-base-300);
  border-radius: 0.55rem;
  background: var(--bg-base-200);
}

.folder-tab {
  flex: 1;
  border: none;
  background: transparent;
  color: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  padding: 0.35rem 0.45rem;
  border-radius: 0.4rem;
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.folder-tab:hover {
  background: var(--bg-base-300);
}

.folder-tab--active {
  background: var(--bg-base-100);
  border: 1px solid var(--border-base-300);
}

.folder-panel-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 12rem;
}

.folder-panel-alert {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.folder-panel-hero {
  margin-bottom: 0.9rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-base-300);
}

.folder-hero-title {
  font-size: 1.05rem;
  font-weight: 600;
  line-height: 1.3;
}

.folder-hero-sub {
  font-size: 0.8rem;
  opacity: 0.75;
  margin-top: 0.25rem;
}

.folder-section {
  margin-bottom: 0.95rem;
  padding: 0.15rem 0;
}

.folder-section + .folder-section {
  border-top: 1px solid var(--border-base-300);
  padding-top: 0.85rem;
}

.folder-section-muted {
  opacity: 0.9;
}

.folder-section-title {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.8;
  margin-bottom: 0.5rem;
}

.folder-path {
  font-size: 0.78rem;
  word-break: break-all;
  line-height: 1.45;
}

.mono {
  font-family: ui-monospace, monospace;
}

.folder-summary-list,
.folder-advanced-list {
  margin: 0;
  padding-left: 1rem;
  font-size: 0.85rem;
  line-height: 1.5;
}

.folder-summary-block {
  margin-top: 0.55rem;
}

.folder-tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.folder-tag-chip {
  font-size: 0.75rem;
  padding: 0.15rem 0.45rem;
  border-radius: 9999px;
  background: rgba(139, 92, 246, 0.18);
  border: 1px solid rgba(139, 92, 246, 0.35);
}

.folder-muted {
  font-size: 0.8rem;
  opacity: 0.65;
}

.folder-actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.folder-actions-stack {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.folder-actions-stack :deep(.btn) {
  justify-content: flex-start;
}

.folder-danger-zone {
  border-top-color: rgba(239, 68, 68, 0.35);
  padding-top: 0.95rem;
  margin-top: 0.85rem;
}

.folder-rename-embedded {
  margin-top: 0.7rem;
}

.folder-danger-hint {
  margin: 0;
  font-size: 0.8rem;
}

.folder-nom-hint {
  font-size: 0.78rem;
  line-height: 1.45;
  margin: 0 0 0.5rem;
}

.folder-nom-fields {
  display: grid;
  grid-template-columns: 1fr 120px;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.folder-nom-label {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  opacity: 0.85;
}

.folder-nom-actions {
  margin-top: 0.25rem;
  margin-bottom: 0.75rem;
}

@media (max-width: 430px) {
  .folder-nom-fields {
    grid-template-columns: 1fr;
  }
}

.folder-tag-inherit {
  font-size: 0.72rem;
  line-height: 1.35;
  margin: 0 0 0.45rem;
}

.tree-node-editor {
  margin-top: 0.54rem;
  margin-bottom: 0;
  border: 1px solid rgba(119, 126, 142, 0.32);
  border-radius: 0.62rem;
  padding: 0.52rem 0.56rem;
  background: linear-gradient(180deg, rgba(17, 22, 33, 0.92), rgba(13, 17, 27, 0.92));
  animation: folderPanelTagEditorReveal 0.18s ease-out;
}

.integrated-editor {
  margin-top: 0.54rem;
  margin-bottom: 0;
}

.tree-node-editor-title {
  font-size: 0.72rem;
  font-weight: 610;
  color: #e4eaf8;
}

.tree-node-editor-sub {
  font-size: 0.66rem;
  color: rgba(167, 175, 192, 0.78);
  margin-top: 0.15rem;
  margin-bottom: 0.34rem;
}

.tree-node-draft-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.34rem;
}

.tree-node-draft-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  border: 1px solid rgba(125, 134, 150, 0.48);
  border-radius: 999px;
  font-size: 0.66rem;
  color: #d8dce8;
  padding: 0.12rem 0.42rem;
  background: rgba(29, 35, 48, 0.6);
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease;
}

.tree-node-draft-tag button {
  border: none;
  background: transparent;
  cursor: pointer;
  color: rgba(205, 212, 226, 0.78);
  padding: 0;
  font-size: 0.72rem;
  line-height: 1;
  transition: color 0.15s ease;
}

.tree-node-draft-tag button:hover {
  color: #f6f8fc;
}

.tree-node-editor-add {
  display: flex;
  align-items: center;
  gap: 0.36rem;
  margin-bottom: 0.32rem;
}

.tree-node-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.26rem;
  margin-bottom: 0.35rem;
}

.tree-node-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.32rem;
}

@keyframes folderPanelTagEditorReveal {
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

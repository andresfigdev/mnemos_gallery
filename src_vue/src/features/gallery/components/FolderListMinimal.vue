<template>
  <div id="folders-list-minimal">
    <div v-if="loading && folders.length === 0" class="state-text">Cargando...</div>
    <div v-else-if="error" class="state-error">{{ error }}</div>
    <div v-else-if="enabledFolders.length === 0" class="state-text">No hay carpetas registradas</div>

    <div v-else class="tree-list">
      <div v-if="enabledFolders.length > 0" class="tree-toolbar" role="group" aria-label="Vista del árbol">
        <button type="button" class="tree-bulk-btn" title="Desplegar todas las carpetas y ramas" @click="expandAllTrees">
          <ChevronsDown :size="14" />
          <span class="tree-bulk-label">Todo</span>
        </button>
        <button type="button" class="tree-bulk-btn" title="Plegar todas las carpetas y ramas" @click="collapseAllTrees">
          <ChevronsUp :size="14" />
          <span class="tree-bulk-label">Nada</span>
        </button>
      </div>
      <div v-if="props.editable && selectedMoveNodeCount" class="tree-move-summary">
        <span>{{ selectedMoveNodeCount }} carpeta{{ selectedMoveNodeCount === 1 ? '' : 's' }} · arrástrala{{ selectedMoveNodeCount === 1 ? '' : 's' }} al lado derecho</span>
        <div>
          <button type="button" @click="selectedMoveNodes = {}">Limpiar</button>
        </div>
      </div>

      <div v-for="folder in enabledFolders" :key="folder.id" class="tree-group">
        <div
          class="tree-root-line"
          :class="{ 'tree-line-move-selected': props.editable && isRootMoveSelected(folder.id) }"
          :draggable="props.editable && Boolean(getRootNode(folder.id))"
          @dragstart.stop="handleRootMoveDragStart($event, folder.id)"
          @dragend.stop="handleMoveDragEnd"
        >
          <button
            v-if="folderHasSubTree(folder.id)"
            type="button"
            class="tree-twiggle"
            :aria-expanded="isFolderTreeExpanded(folder.id)"
            :title="isFolderTreeExpanded(folder.id) ? 'Ocultar subcarpetas' : 'Mostrar subcarpetas'"
            @click.stop="toggleFolderTreeExpanded(folder.id)"
          >
            {{ isFolderTreeExpanded(folder.id) ? '▾' : '▸' }}
          </button>
          <span v-else class="tree-twiggle-spacer" aria-hidden="true" />

          <button
            v-if="props.editable && getRootNode(folder.id)"
            type="button"
            class="tree-move-select"
            :class="{ selected: isRootMoveSelected(folder.id) }"
            :title="isRootMoveSelected(folder.id) ? 'Quitar de la selección' : 'Seleccionar carpeta para mover'"
            @click.stop="toggleRootMove(folder.id)"
          >
            <Check v-if="isRootMoveSelected(folder.id)" :size="11" />
          </button>

          <button
            type="button"
            class="tree-row tree-root-row"
            :class="{ selected: selectedFolderId === folder.id && selectedTreeNodeId === getRootNodeId(folder.id) }"
            :title="props.editable ? 'Seleccionar; también puedes arrastrar esta carpeta al árbol ordenado' : 'Seleccionar carpeta'"
            @click="selectFolderRoot(folder.id)"
          >
            <Folder :size="15" class="tree-icon root" />
            <span class="tree-name">{{ folder.name }}</span>
          </button>
          <button
            v-if="props.editable && getRootNode(folder.id)"
            type="button"
            class="tree-delete-empty"
            :disabled="deletingNodeIds.has(getRootNodeId(folder.id) ?? -1)"
            :title="`Mover ${folder.name} a la papelera si no contiene imágenes originales`"
            @click.stop="deleteRootFolder(folder.id)"
          >
            <LoaderCircle v-if="deletingNodeIds.has(getRootNodeId(folder.id) ?? -1)" :size="13" class="is-spinning" />
            <Trash2 v-else :size="13" />
          </button>
        </div>

        <div
          v-for="item in getVisibleChildNodes(folder.id)"
          :key="`${folder.id}-node-${item.node.id}`"
          class="tree-child-line"
          :class="{
            'tree-line-move-selected': props.editable && isMoveNodeSelected(folder.id, item.node.id),
          }"
          :style="{ paddingLeft: `${1.5 + item.depth * 0.95}rem` }"
          :draggable="props.editable"
          @dragstart.stop="handleMoveDragStart($event, folder.id, item.node)"
          @dragend.stop="handleMoveDragEnd"
        >
          <button
            v-if="(item.node.children || []).length > 0"
            type="button"
            class="tree-twiggle"
            :aria-expanded="isNodeExpanded(item.node.id)"
            :title="isNodeExpanded(item.node.id) ? 'Contraer' : 'Expandir'"
            @click.stop="toggleTreeNode(item.node.id)"
          >
            {{ isNodeExpanded(item.node.id) ? '▾' : '▸' }}
          </button>
          <span v-else class="tree-twiggle-spacer" aria-hidden="true" />

          <button
            v-if="props.editable"
            type="button"
            class="tree-move-select"
            :class="{ selected: isMoveNodeSelected(folder.id, item.node.id) }"
            :title="isMoveNodeSelected(folder.id, item.node.id) ? 'Quitar de la selección' : 'Seleccionar carpeta para mover'"
            @click.stop="toggleMoveNode(folder.id, item.node)"
          >
            <Check v-if="isMoveNodeSelected(folder.id, item.node.id)" :size="11" />
          </button>

          <button
            type="button"
            class="tree-row tree-child-row"
            :class="{ selected: selectedTreeNodeId === item.node.id }"
            @click="selectFolderNode(folder.id, item.node.id)"
          >
            <FolderOpen :size="14" class="tree-icon child" />
            <span class="tree-name">{{ item.node.name }}</span>
          </button>
          <button
            v-if="props.editable"
            type="button"
            class="tree-delete-empty"
            :disabled="deletingNodeIds.has(item.node.id)"
            :title="`Eliminar la rama vacía ${item.node.name}`"
            @click.stop="deleteEmptyNode(folder.id, item.node)"
          >
            <LoaderCircle v-if="deletingNodeIds.has(item.node.id)" :size="13" class="is-spinning" />
            <Trash2 v-else :size="13" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Check, ChevronsDown, ChevronsUp, Folder, FolderOpen, LoaderCircle, Trash2 } from 'lucide-vue-next'
import {
  deleteEmptySourceFolder,
  getFolderTree,
  listFolders,
  type SourceFolderNodeMoveItem,
  type Folder as FolderType,
  type FolderNode,
  type FolderTreeResponse,
} from '../api'
import { getImagePaths, getSetting } from '../../settings/api'

const props = withDefaults(defineProps<{
  editable?: boolean
}>(), {
  editable: false,
})

const emit = defineEmits<{
  folderSelected: [selection: { folderId: string; folderNodeId: number | null }]
  folderScanned: [folderId: string]
  folderDeleted: [folderId: string]
  folderToggled: [folderId: string]
}>()

const folders = ref<FolderType[]>([])
const folderTrees = ref<Record<string, FolderTreeResponse>>({})
const loading = ref(false)
const error = ref<string | null>(null)
const selectedFolderId = ref<string | null>(null)
const selectedTreeNodeId = ref<number | null>(null)
const deletingNodeIds = ref<Set<number>>(new Set())
const selectedMoveNodes = ref<Record<string, SourceFolderNodeMoveItem>>({})
const organizerFolderPath = ref('')
const showOrderedFolderInOrganizer = ref(false)
/** false = solo fila raíz de esa carpeta; true/undefined = hijos visibles */
const folderChildrenExpanded = ref<Record<string, boolean>>({})
/** Por nodo: false = ramas hijas ocultas; true/undefined = expandido */
const expandedNodeState = ref<Record<number, boolean>>({})

const isFolderTreeExpanded = (folderId: string) => folderChildrenExpanded.value[folderId] !== false

const isNodeExpanded = (nodeId: number) => expandedNodeState.value[nodeId] !== false
const selectedMoveNodeCount = computed(() => Object.keys(selectedMoveNodes.value).length)

const nodeMoveKey = (folderId: string, nodeId: number) => `${folderId}:${nodeId}`

const isMoveNodeSelected = (folderId: string, nodeId: number) =>
  Boolean(selectedMoveNodes.value[nodeMoveKey(folderId, nodeId)])

const isRootMoveSelected = (folderId: string) => {
  const root = getRootNode(folderId)
  return root ? isMoveNodeSelected(folderId, root.id) : false
}

function toggleFolderTreeExpanded(folderId: string) {
  folderChildrenExpanded.value = {
    ...folderChildrenExpanded.value,
    [folderId]: !isFolderTreeExpanded(folderId),
  }
}

function toggleTreeNode(nodeId: number) {
  expandedNodeState.value = {
    ...expandedNodeState.value,
    [nodeId]: !isNodeExpanded(nodeId),
  }
}

function folderHasSubTree(folderId: string): boolean {
  const roots = folderTrees.value[folderId]?.nodes || []
  for (const r of roots) {
    if ((r.children || []).length > 0) return true
  }
  return false
}

function collectFolderNodeIds(nodes: FolderNode[]): number[] {
  const ids: number[] = []
  const walkCollect = (n: FolderNode) => {
    ids.push(n.id)
    for (const c of n.children || []) walkCollect(c)
  }
  for (const n of nodes) walkCollect(n)
  return ids
}

const normalizeFolderPath = (value: string) => value.replace(/\\/g, '/').replace(/\/+$/, '').toLocaleLowerCase()

const isOrganizerDestinationPath = (value: string): boolean => {
  if (!organizerFolderPath.value) return false
  if (props.editable && showOrderedFolderInOrganizer.value) return false

  const candidatePath = normalizeFolderPath(value)
  const destinationPath = normalizeFolderPath(organizerFolderPath.value)
  return candidatePath === destinationPath || candidatePath.startsWith(`${destinationPath}/`)
}

const enabledFolders = computed(() => {
  return folders.value.filter((folder) => {
    if (!folder.enabled) return false
    const lowerName = folder.name?.toLowerCase() || ''
    const lowerPath = folder.path?.toLowerCase() || ''
    const isTrash =
      lowerName.includes('papelera') ||
      lowerName.includes('trash') ||
      lowerPath.includes('papelera') ||
      lowerPath.includes('trash')
    if (isTrash) return false
    if (isOrganizerDestinationPath(folder.path)) return false
    return true
  })
})

async function loadOrganizerSourceVisibility() {
  try {
    const paths = await getImagePaths()
    organizerFolderPath.value = paths.img_sorted_path || ''
  } catch {
    organizerFolderPath.value = ''
  }
  try {
    const setting = await getSetting('show_ordered_folder_in_organizer')
    showOrderedFolderInOrganizer.value = setting.value?.toLowerCase() === 'true'
  } catch (err: any) {
    if (err.response?.status === 404) showOrderedFolderInOrganizer.value = false
  }
}

const getRootNode = (folderId: string): FolderNode | null => {
  const roots = folderTrees.value[folderId]?.nodes || []
  if (roots.length === 0) return null
  const exactRoot = roots.find((node) => node.rel_path === '')
  return exactRoot || roots[0] || null
}

const getRootNodeId = (folderId: string): number | null => {
  const root = getRootNode(folderId)
  return root ? root.id : null
}

type VisibleTreeNode = { node: FolderNode; depth: number }
const getVisibleChildNodes = (folderId: string): VisibleTreeNode[] => {
  if (!isFolderTreeExpanded(folderId)) return []

  const roots = folderTrees.value[folderId]?.nodes || []
  const folderRootPath = folders.value.find(folder => folder.id === folderId)?.path || ''
  const output: VisibleTreeNode[] = []

  const walk = (node: FolderNode, depth: number) => {
    if (node.rel_path.split(/[\\/]/).some(segment => segment.toLocaleLowerCase() === 'thumb')) return
    const nodePath = node.rel_path
      ? `${folderRootPath}/${node.rel_path}`
      : folderRootPath
    if (isOrganizerDestinationPath(nodePath)) return
    output.push({ node, depth })
    if (!isNodeExpanded(node.id)) return
    for (const child of node.children || []) {
      walk(child, depth + 1)
    }
  }

  for (const root of roots) {
    for (const child of root.children || []) {
      walk(child, 0)
    }
  }

  return output
}

function expandAllTrees() {
  const nextFolders: Record<string, boolean> = { ...folderChildrenExpanded.value }
  const nextNodes: Record<number, boolean> = { ...expandedNodeState.value }
  for (const f of enabledFolders.value) {
    nextFolders[f.id] = true
    const roots = folderTrees.value[f.id]?.nodes || []
    for (const id of collectFolderNodeIds(roots)) {
      nextNodes[id] = true
    }
  }
  folderChildrenExpanded.value = nextFolders
  expandedNodeState.value = nextNodes
}

function collapseAllTrees() {
  const nextFolders: Record<string, boolean> = { ...folderChildrenExpanded.value }
  const nextNodes: Record<number, boolean> = { ...expandedNodeState.value }
  for (const f of enabledFolders.value) {
    nextFolders[f.id] = false
    const roots = folderTrees.value[f.id]?.nodes || []
    for (const id of collectFolderNodeIds(roots)) {
      nextNodes[id] = false
    }
  }
  folderChildrenExpanded.value = nextFolders
  expandedNodeState.value = nextNodes
}

const selectFolderRoot = (folderId: string) => {
  const rootNodeId = getRootNodeId(folderId)
  selectedFolderId.value = folderId
  selectedTreeNodeId.value = rootNodeId
  emit('folderSelected', { folderId, folderNodeId: rootNodeId })
}

const selectFolderNode = (folderId: string, nodeId: number) => {
  selectedFolderId.value = folderId
  selectedTreeNodeId.value = nodeId
  emit('folderSelected', { folderId, folderNodeId: nodeId })
}

const toggleMoveNode = (folderId: string, node: FolderNode) => {
  const key = nodeMoveKey(folderId, node.id)
  const next = { ...selectedMoveNodes.value }
  if (next[key]) delete next[key]
  else next[key] = { folder_id: folderId, node_id: node.id }
  selectedMoveNodes.value = next
}

const toggleRootMove = (folderId: string) => {
  const root = getRootNode(folderId)
  if (root) toggleMoveNode(folderId, root)
}

const handleMoveDragStart = (event: DragEvent, folderId: string, node: FolderNode) => {
  if (!props.editable) {
    event.preventDefault()
    return
  }
  const key = nodeMoveKey(folderId, node.id)
  const sources = selectedMoveNodes.value[key]
    ? Object.values(selectedMoveNodes.value)
    : [{ folder_id: folderId, node_id: node.id }]
  selectedMoveNodes.value = Object.fromEntries(
    sources.map(source => [nodeMoveKey(source.folder_id, source.node_id), source]),
  )
  event.dataTransfer?.setData('application/x-mnemos-source-folders', JSON.stringify(sources))
  event.dataTransfer?.setData('text/plain', `${sources.length} carpeta${sources.length === 1 ? '' : 's'}`)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

const handleRootMoveDragStart = (event: DragEvent, folderId: string) => {
  const root = getRootNode(folderId)
  if (!root) {
    event.preventDefault()
    return
  }
  handleMoveDragStart(event, folderId, root)
}

const handleMoveDragEnd = () => {
}

const deleteEmptyNode = async (folderId: string, node: FolderNode) => {
  if (!props.editable) return
  if (deletingNodeIds.value.has(node.id)) return
  deletingNodeIds.value = new Set([...deletingNodeIds.value, node.id])
  const wasSelected = selectedFolderId.value === folderId && selectedTreeNodeId.value === node.id
  try {
    await deleteEmptySourceFolder(folderId, node.id)
    await loadFolders()
    if (wasSelected) {
      if (enabledFolders.value.some(folder => folder.id === folderId)) selectFolderRoot(folderId)
      else {
        selectedFolderId.value = null
        selectedTreeNodeId.value = null
      }
    }
    emit('folderDeleted', folderId)
    window.dispatchEvent(new CustomEvent('sourceFolderSelectionInvalidated', {
      detail: { folderId },
    }))
  } catch (err: any) {
    window.alert(err.response?.data?.detail || err.message || 'No se pudo eliminar la carpeta vacía.')
  } finally {
    const next = new Set(deletingNodeIds.value)
    next.delete(node.id)
    deletingNodeIds.value = next
  }
}

const deleteRootFolder = (folderId: string) => {
  const root = getRootNode(folderId)
  if (root) deleteEmptyNode(folderId, root)
}

const handleSourceFoldersMoved = () => {
  selectedMoveNodes.value = {}
  loadFolders()
}

const handleOrganizerSourceVisibilityChanged = (event: Event) => {
  const enabled = (event as CustomEvent<{ enabled?: boolean }>).detail?.enabled
  showOrderedFolderInOrganizer.value = enabled === true
}

watch(() => props.editable, (editable) => {
  if (!editable) selectedMoveNodes.value = {}
})

const loadFolderTrees = async () => {
  const trees: Record<string, FolderTreeResponse> = {}
  for (const folder of enabledFolders.value) {
    try {
      trees[folder.id] = await getFolderTree(folder.id)
    } catch (loadTreeError) {
      console.warn(`No se pudo cargar árbol para carpeta ${folder.id}`, loadTreeError)
    }
  }
  folderTrees.value = trees
}

const loadFolders = async () => {
  loading.value = true
  error.value = null
  try {
    folders.value = await listFolders()
    await loadFolderTrees()
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || 'Error al cargar carpetas'
  } finally {
    loading.value = false
  }
}

defineExpose({
  refresh: async () => {
    await loadOrganizerSourceVisibility()
    await loadFolders()
  },
})

onMounted(async () => {
  window.addEventListener('sourceFoldersMovedToOrganizer', handleSourceFoldersMoved)
  window.addEventListener('organizerSourceVisibilityChanged', handleOrganizerSourceVisibilityChanged)
  await loadOrganizerSourceVisibility()
  await loadFolders()
})

onUnmounted(() => {
  window.removeEventListener('sourceFoldersMovedToOrganizer', handleSourceFoldersMoved)
  window.removeEventListener('organizerSourceVisibilityChanged', handleOrganizerSourceVisibilityChanged)
})
</script>

<style scoped>
#folders-list-minimal {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.state-text {
  font-size: 0.82rem;
  color: var(--text-base);
  opacity: 0.9;
  padding: 0.5rem 0.25rem;
}

.state-error {
  font-size: 0.8rem;
  color: #ffb4b4;
  border: 1px solid rgba(149, 77, 77, 0.52);
  background: rgba(136, 58, 58, 0.2);
  border-radius: 0.55rem;
  padding: 0.55rem 0.6rem;
}

.tree-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tree-toolbar {
  position: sticky;
  top: -0.75rem;
  z-index: 8;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding: 0.65rem 0.1rem 0.45rem;
  margin-bottom: 0.2rem;
  border-bottom: 1px solid color-mix(in oklab, var(--border-base-300) 82%, transparent);
  background: var(--bg-base-100);
}

.tree-move-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
  padding: 0.35rem 0.45rem;
  border: 1px solid rgba(96, 165, 250, 0.38);
  border-radius: 0.45rem;
  background: rgba(59, 130, 246, 0.1);
  color: #bfdbfe;
  font-size: 0.68rem;
}

.tree-move-summary button {
  border: 0;
  border-radius: 0.35rem;
  padding: 0.2rem 0.35rem;
  background: rgba(96, 165, 250, 0.16);
  color: #dbeafe;
  cursor: pointer;
}

.tree-bulk-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  padding: 0.22rem 0.45rem 0.22rem 0.38rem;
  border-radius: 0.45rem;
  border: 1px solid color-mix(in oklab, var(--border-base-300) 85%, transparent);
  background: color-mix(in oklab, var(--bg-base-200) 70%, transparent);
  color: var(--text-base);
  font-size: 0.68rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}

.tree-bulk-label {
  line-height: 1;
  opacity: 0.92;
}

.tree-bulk-btn:hover {
  background: rgba(139, 92, 246, 0.14);
  border-color: rgba(139, 92, 246, 0.35);
  color: var(--text-base-content);
}

.tree-bulk-btn:active {
  transform: scale(0.98);
}

.tree-root-line,
.tree-child-line {
  display: flex;
  align-items: stretch;
  gap: 0.08rem;
  width: 100%;
  min-width: 0;
  border-radius: 0.5rem;
  transition: background-color 0.14s ease, box-shadow 0.14s ease;
}

.tree-root-line[draggable="true"],
.tree-child-line {
  cursor: grab;
}

.tree-root-line[draggable="true"]:active,
.tree-child-line:active {
  cursor: grabbing;
}

.tree-line-move-selected {
  background: rgba(59, 130, 246, 0.1);
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.5);
}

.tree-line-drop-over {
  background: rgba(34, 197, 94, 0.16);
  box-shadow: inset 0 0 0 1px rgba(74, 222, 128, 0.78);
}

.tree-twiggle {
  flex: 0 0 1.35rem;
  width: 1.35rem;
  min-width: 1.35rem;
  align-self: stretch;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 0.35rem;
  background: transparent;
  color: var(--text-base);
  opacity: 0.75;
  font-size: 0.65rem;
  line-height: 1;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    opacity 0.15s ease;
}

.tree-twiggle:hover {
  opacity: 1;
  background: rgba(139, 92, 246, 0.12);
}

.tree-twiggle-spacer {
  flex: 0 0 1.35rem;
  width: 1.35rem;
  min-width: 1.35rem;
}

.tree-move-select {
  flex: 0 0 1.15rem;
  width: 1.15rem;
  min-width: 1.15rem;
  height: 1.15rem;
  align-self: center;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid #4b5568;
  border-radius: 0.32rem;
  background: rgba(8, 11, 18, 0.52);
  color: white;
  cursor: pointer;
}

.tree-move-select.selected {
  border-color: #60a5fa;
  background: #2563eb;
}

.tree-root-line .tree-row,
.tree-child-line .tree-row {
  flex: 1;
  min-width: 0;
}

.tree-group {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.tree-row {
  width: 100%;
  border: none;
  background: transparent;
  color: var(--text-base-content);
  border-radius: 0.5rem;
  padding: 0.35rem 0.45rem;
  display: flex;
  align-items: center;
  gap: 0.42rem;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.tree-row:hover {
  background: rgba(139, 92, 246, 0.1);
}

.tree-row.selected {
  background: rgba(139, 92, 246, 0.16);
  outline: 1px solid rgba(139, 92, 246, 0.4);
}

.tree-root-row {
  font-size: 0.86rem;
  font-weight: 560;
}

.tree-child-row {
  font-size: 0.82rem;
  font-weight: 460;
  color: var(--text-base);
}

.tree-delete-empty {
  width: 1.8rem;
  min-width: 1.8rem;
  align-self: stretch;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 0.42rem;
  background: transparent;
  color: #a7b0c0;
  cursor: pointer;
  opacity: 0.55;
  transition: 140ms ease;
}

.tree-root-line:hover .tree-delete-empty,
.tree-child-line:hover .tree-delete-empty,
.tree-delete-empty:focus-visible {
  opacity: 1;
}

.tree-delete-empty:hover {
  background: rgba(239, 68, 68, 0.14);
  color: #fca5a5;
}

.tree-delete-empty:disabled {
  cursor: wait;
  opacity: 0.7;
}

.is-spinning {
  animation: tree-spin 0.9s linear infinite;
}

@keyframes tree-spin {
  to { transform: rotate(360deg); }
}

.tree-icon.root {
  color: #cbb6ff;
}

.tree-icon.child {
  color: #a38adf;
}

.tree-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-drop-label {
  flex: 0 0 auto;
  margin-left: auto;
  padding: 0.12rem 0.35rem;
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.2);
  color: #bbf7d0;
  font-size: 0.58rem;
  font-weight: 700;
}
</style>

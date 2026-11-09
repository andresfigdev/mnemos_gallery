<template>
  <div class="organizer-tree-node">
    <div
      class="organizer-folder-row"
      :class="{
        'organizer-folder-row--active': selectedPath === node.path,
        'organizer-folder-row--over': dragOver,
      }"
      :style="{ paddingLeft: `${depth * 14 + 8}px` }"
      @click="emit('select', node.path)"
      @dragenter.prevent.stop="handleDragEnter"
      @dragover.prevent.stop="handleDragOver"
      @dragleave.stop="handleDragLeave"
      @drop.prevent.stop="handleDrop"
    >
      <button
        type="button"
        class="organizer-tree-chevron"
        :class="{ 'is-hidden': node.children.length === 0 }"
        @click.stop="expanded = !expanded"
      >
        <ChevronRight :size="15" :class="{ 'is-expanded': expanded }" />
      </button>
      <FolderOpen v-if="expanded" :size="17" class="organizer-folder-icon" />
      <Folder v-else :size="17" class="organizer-folder-icon" />
      <span class="organizer-folder-name" :title="node.path">{{ node.name }}</span>
      <span v-if="dragOver" class="organizer-drop-label">
        {{ dragKind === 'source-folders' ? 'Mover carpetas aquí' : 'Soltar aquí' }}
      </span>
      <span v-else class="organizer-folder-count" :title="`${node.total_image_count} imágenes en esta rama`">
        {{ node.total_image_count }}
      </span>
      <button
        type="button"
        class="organizer-rename-folder"
        :title="`Cambiar nombre de ${node.name}`"
        @click.stop="emit('rename-folder', node)"
      >
        <Pencil :size="13" />
      </button>
      <button
        type="button"
        class="organizer-add-child"
        :title="`Crear subcarpeta en ${node.name}`"
        @click.stop="emit('create-child', node.path)"
      >
        <Plus :size="14" />
      </button>
    </div>

    <div v-if="expanded && node.children.length" class="organizer-tree-children">
      <OrganizerFolderNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
        :selected-path="selectedPath"
        :expand-all="expandAll"
        :expansion-token="expansionToken"
        @select="emit('select', $event)"
        @create-child="emit('create-child', $event)"
        @rename-folder="emit('rename-folder', $event)"
        @drop-images="emit('drop-images', $event)"
        @drop-source-folders="emit('drop-source-folders', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ChevronRight, Folder, FolderOpen, Pencil, Plus } from 'lucide-vue-next'
import type { OrganizerFolder, SourceFolderNodeMoveItem } from '../api'

defineOptions({ name: 'OrganizerFolderNode' })

const props = defineProps<{
  node: OrganizerFolder
  depth: number
  selectedPath: string
  expandAll: boolean
  expansionToken: number
}>()

const emit = defineEmits<{
  select: [path: string]
  'create-child': [path: string]
  'rename-folder': [node: OrganizerFolder]
  'drop-images': [path: string]
  'drop-source-folders': [payload: { sourceNodes: SourceFolderNodeMoveItem[]; destinationPath: string }]
}>()

// Los nodos que se montan después de usar Todo/Nada deben heredar ese estado.
const expanded = ref(props.expandAll)
const dragOver = ref(false)
const dragEnterDepth = ref(0)
const dragKind = ref<'images' | 'source-folders' | null>(null)

watch(
  () => props.expansionToken,
  () => {
    expanded.value = props.expandAll
  },
)

function handleDragEnter(event: DragEvent) {
  dragEnterDepth.value += 1
  dragOver.value = true
  dragKind.value = event.dataTransfer?.types.includes('application/x-mnemos-source-folders')
    ? 'source-folders'
    : 'images'
}

function handleDragOver(event: DragEvent) {
  dragOver.value = true
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleDragLeave() {
  dragEnterDepth.value = Math.max(0, dragEnterDepth.value - 1)
  if (dragEnterDepth.value === 0) {
    dragOver.value = false
    dragKind.value = null
  }
}

function handleDrop(event: DragEvent) {
  const hasSourceFolders = Boolean(
    event.dataTransfer?.types.includes('application/x-mnemos-source-folders'),
  )
  const hasImages = Boolean(event.dataTransfer?.types.includes('application/x-mnemos-images'))
  dragEnterDepth.value = 0
  dragOver.value = false
  dragKind.value = null
  if (hasSourceFolders) {
    try {
      const parsed = JSON.parse(
        event.dataTransfer?.getData('application/x-mnemos-source-folders') || '[]',
      )
      if (Array.isArray(parsed)) {
        const sourceNodes = parsed.filter(
          item => item && typeof item.folder_id === 'string' && Number.isInteger(item.node_id),
        )
        if (sourceNodes.length) {
          emit('drop-source-folders', { sourceNodes, destinationPath: props.node.path })
        }
      }
    } catch {
      // El arrastre no contiene carpetas originales válidas.
    }
    return
  }
  if (!hasImages) return
  emit('drop-images', props.node.path)
}
</script>

<style scoped>
.organizer-tree-node {
  min-width: 0;
}

.organizer-folder-row {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding-right: 7px;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  color: #cbd5e1;
  transition: 140ms ease;
}

.organizer-folder-row:hover {
  background: rgba(148, 163, 184, 0.08);
  color: #f8fafc;
}

.organizer-folder-row--active {
  background: rgba(139, 92, 246, 0.14);
  border-color: rgba(139, 92, 246, 0.42);
  color: #fff;
}

.organizer-folder-row--over {
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(74, 222, 128, 0.9);
  box-shadow:
    inset 0 0 0 1px rgba(34, 197, 94, 0.28),
    0 0 0 2px rgba(34, 197, 94, 0.08);
}

.organizer-tree-chevron,
.organizer-rename-folder,
.organizer-add-child {
  border: 0;
  background: transparent;
  color: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.organizer-tree-chevron {
  width: 16px;
  height: 22px;
  flex: 0 0 16px;
}

.organizer-tree-chevron.is-hidden {
  visibility: hidden;
}

.organizer-tree-chevron svg {
  transition: transform 140ms ease;
}

.organizer-tree-chevron svg.is-expanded {
  transform: rotate(90deg);
}

.organizer-folder-icon {
  color: #a78bfa;
  flex: 0 0 auto;
}

.organizer-folder-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 560;
}

.organizer-folder-count {
  min-width: 24px;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.1);
  color: #94a3b8;
  font-size: 11px;
  text-align: center;
}

.organizer-drop-label {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.2);
  color: #bbf7d0;
  font-size: 10px;
  font-weight: 700;
}

.organizer-rename-folder,
.organizer-add-child {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  opacity: 0;
}

.organizer-folder-row:hover .organizer-rename-folder,
.organizer-folder-row:hover .organizer-add-child,
.organizer-folder-row--active .organizer-rename-folder,
.organizer-folder-row--active .organizer-add-child {
  opacity: 1;
}

.organizer-rename-folder:hover,
.organizer-add-child:hover {
  background: rgba(139, 92, 246, 0.22);
}
</style>

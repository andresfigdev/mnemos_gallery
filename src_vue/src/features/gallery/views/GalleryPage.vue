<template>
  <div class="gallery-page">
    <div class="gallery-split">
      <div class="gallery-split-main">
        <ImageGrid
          ref="imageGridRef"
          :selected-folder-id="selectedFolderId"
          :selected-folder-node-id="selectedFolderNodeId"
          :refresh-trigger="refreshTrigger"
          :dashboard-image-filters="dashboardImageFilters"
          :folder-panel-open="folderPanelOpen"
          v-model:rename-picked-ids="renamePickIds"
          :rename-picking-mode="renamePickMode"
          @show-details="handleShowImageDetails"
          @toggle-folder-panel="folderPanelOpen = !folderPanelOpen"
        />
      </div>
      <div
        class="gallery-folder-rail"
        :class="{ 'gallery-folder-rail--open': folderPanelOpen }"
      >
        <FolderDetailsPanel
          v-if="selectedFolderId && folderPanelOpen"
          :key="`${selectedFolderId}-${selectedFolderNodeId ?? 'root'}`"
          :folder-id="selectedFolderId"
          :folder-node-id="selectedFolderNodeId ?? null"
          :rename-picked-ids="renamePickIds"
          @close="folderPanelOpen = false"
          @update:rename-picking-mode="renamePickMode = $event"
          @update:rename-picked-ids="renamePickIds = $event"
          @rename-applied="onRenameApplied"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import ImageGrid from '../components/ImageGrid.vue'
import FolderDetailsPanel from '../components/FolderDetailsPanel.vue'
import { usePanelStore } from '../../../stores/panelStore'

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
}>()

const imageGridRef = ref<InstanceType<typeof ImageGrid> | null>(null)
const folderPanelOpen = ref(false)
const renamePickMode = ref(false)
const renamePickIds = ref<number[]>([])
const { openPanel } = usePanelStore()

function onRenameApplied() {
  renamePickMode.value = false
  renamePickIds.value = []
  imageGridRef.value?.refresh()
  window.dispatchEvent(new CustomEvent('galleryRefresh'))
  window.dispatchEvent(new CustomEvent('refreshFolders'))
}

watch(
  () => props.selectedFolderId,
  (id) => {
    if (!id) folderPanelOpen.value = false
  }
)

watch(
  () => props.refreshTrigger,
  () => {
    if (imageGridRef.value) {
      imageGridRef.value.refresh()
    }
  }
)

const handleShowImageDetails = (imageId: number) => {
  openPanel('image-details', { imageId })
}
</script>

<style scoped>
.gallery-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.gallery-split {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  flex-direction: row;
}

.gallery-split-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.gallery-folder-rail {
  flex-shrink: 0;
  width: 0;
  min-width: 0;
  overflow: hidden;
  border-left: none;
  background-color: var(--bg-base-100);
  transition:
    width 0.3s ease,
    min-width 0.3s ease,
    border-color 0.3s ease;
}

.gallery-folder-rail--open {
  width: 320px;
  min-width: 320px;
  border-left: 1px solid var(--border-base-300);
}
</style>

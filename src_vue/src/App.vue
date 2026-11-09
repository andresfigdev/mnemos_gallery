<template>
  <div id="layout">
    <!-- Panel izquierdo: Sidebar con carpetas -->
    <div id="left">
      <Sidebar 
        ref="sidebarRef"
        :organizer-mode="currentRoute === '/organizer'"
        @folder-selected="handleFolderSelected"
        @refresh-images="handleRefreshImages"
      />
    </div>

    <!-- Panel central: Header + Contenido -->
    <div id="center">
      <MainHeader 
        :current-route="currentRoute" 
        @navigate="handleNavigate"
        @toggle-sidebar="handleToggleSidebar"
        @organizer-new-folder="handleOrganizerNewFolder"
      />
      <main id="app-content">
        <GalleryPage 
          v-if="currentRoute === '/images'" 
          ref="galleryPageRef"
          :selected-folder-id="selectedFolderId"
          :selected-folder-node-id="selectedFolderNodeId"
          :refresh-trigger="refreshTrigger"
          :dashboard-image-filters="dashboardImageFilters"
        />
        <DashboardPage
          v-else-if="currentRoute === '/dashboard'"
          @open-images="handleOpenImagesFromDashboard"
        />
        <BulkManagementPage v-else-if="currentRoute === '/manage'" />
        <OrganizerPage
          v-else-if="currentRoute === '/organizer'"
          :selected-folder-id="selectedFolderId"
          :selected-folder-node-id="selectedFolderNodeId"
          :refresh-trigger="refreshTrigger"
        />
        <SettingsPage v-else-if="currentRoute === '/settings'" />
        <DatabaseViewerPage v-else-if="currentRoute === '/database'" />
        <PlaceholderPage v-else :title="getPageTitle(currentRoute)" />
      </main>
    </div>
  </div>

  <!-- Panel lateral global (detalle de imagen) -->
  <ImageDetailsPanel />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import MainHeader from './components/MainHeader.vue'
import GalleryPage from './features/gallery/views/GalleryPage.vue'
import BulkManagementPage from './features/gallery/views/BulkManagementPage.vue'
import OrganizerPage from './features/gallery/views/OrganizerPage.vue'
import DashboardPage from './features/dashboard/views/DashboardPage.vue'
import SettingsPage from './features/settings/views/SettingsPage.vue'
import DatabaseViewerPage from './features/database/views/DatabaseViewerPage.vue'
import PlaceholderPage from './components/PlaceholderPage.vue'
import ImageDetailsPanel from './features/gallery/components/ImageDetailsPanel.vue'

const currentRoute = ref('/images')
const selectedFolderId = ref<string>('')
const selectedFolderNodeId = ref<number | null>(null)
const refreshTrigger = ref(0)
const dashboardImageFilters = ref<{
  missing_checkpoint?: boolean
  missing_lora?: boolean
  checkpoint_name?: string
  lora_name?: string
  folder_type?: string
  token: number
}>({ token: 0 })
const galleryPageRef = ref<InstanceType<typeof GalleryPage> | null>(null)
const sidebarRef = ref<InstanceType<typeof Sidebar> | null>(null)

function handleFolderSelected(selection: { folderId: string; folderNodeId: number | null }) {
  const keepOrganizerOpen = currentRoute.value === '/organizer'
  selectedFolderId.value = selection.folderId
  selectedFolderNodeId.value = selection.folderNodeId
  dashboardImageFilters.value = { token: Date.now() }
  if (!keepOrganizerOpen) currentRoute.value = '/images'
}

function handleRefreshImages() {
  refreshTrigger.value++
}

function handleNavigate(path: string) {
  currentRoute.value = path
}

function handleOpenImagesFromDashboard(payload: {
  missing_checkpoint?: boolean
  missing_lora?: boolean
  checkpoint_name?: string
  lora_name?: string
  folder_type?: string
  folder_id?: string
}) {
  if (payload.folder_id) {
    selectedFolderId.value = payload.folder_id
    selectedFolderNodeId.value = null
    dashboardImageFilters.value = { token: Date.now() }
  } else {
    selectedFolderId.value = ''
    selectedFolderNodeId.value = null
    dashboardImageFilters.value = {
      missing_checkpoint: payload.missing_checkpoint,
      missing_lora: payload.missing_lora,
      checkpoint_name: payload.checkpoint_name,
      lora_name: payload.lora_name,
      folder_type: payload.folder_type,
      token: Date.now(),
    }
  }
  currentRoute.value = '/images'
  refreshTrigger.value++
}

function handleToggleSidebar() {
}

function handleOrganizerNewFolder() {
  window.dispatchEvent(new CustomEvent('organizerCreateRootFolder'))
}

function getPageTitle(path: string): string {
  const titles: Record<string, string> = {
    '/database': 'Visor de Base de Datos',
    '/manage': 'Gestión Masiva',
    '/organizer': 'Organizador visual',
    '/dashboard': 'Dashboard',
    '/settings': 'Settings'
  }
  return titles[path] || 'Página'
}

function handleRefreshFolders() {
  if (sidebarRef.value) {
    sidebarRef.value.refreshFolders()
  }
}

function handleGalleryRefresh() {
  refreshTrigger.value++
}

function handleSourceFolderSelectionInvalidated(event: Event) {
  const folderId = (event as CustomEvent<{ folderId?: string }>).detail?.folderId
  if (folderId && selectedFolderId.value !== folderId) return
  selectedFolderId.value = ''
  selectedFolderNodeId.value = null
  refreshTrigger.value++
}

onMounted(() => {
  window.addEventListener('refreshFolders', handleRefreshFolders)
  window.addEventListener('galleryRefresh', handleGalleryRefresh)
  window.addEventListener('sourceFolderSelectionInvalidated', handleSourceFolderSelectionInvalidated)
})

onUnmounted(() => {
  window.removeEventListener('refreshFolders', handleRefreshFolders)
  window.removeEventListener('galleryRefresh', handleGalleryRefresh)
  window.removeEventListener('sourceFolderSelectionInvalidated', handleSourceFolderSelectionInvalidated)
})
</script>

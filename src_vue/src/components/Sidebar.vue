<template>
  <aside id="sidebar">
    <!-- Header con título y botón Agregar -->
    <div class="sidebar-header">
      <div class="sidebar-header-title">
        <FolderIcon :size="16" />
        <span>Carpetas</span>
      </div>
      <button 
        @click="handleAddFolder" 
        class="btn btn-xs btn-neutral" 
        title="Agregar carpeta"
        :disabled="showAddFolderForm"
      >
        <FolderPlusIcon :size="16" />
        <span>Agregar</span>
      </button>
    </div>

    <!-- Formulario para agregar carpeta (colapsable) -->
    <div v-if="showAddFolderForm" class="add-folder-form">
      <div class="form-group">
        <label class="form-label">Ruta de la carpeta *</label>
        <div class="input-with-button">
          <input 
            v-model="newFolderPath" 
            type="text" 
            class="input" 
            placeholder="C:\ruta\a\carpeta"
            @keyup.enter="handleCreateAndScan"
          />
          <button 
            @click="handleBrowseFolder" 
            class="btn btn-xs btn-ghost browse-btn"
            title="Explorar..."
          >
            <FolderOpenIcon :size="16" />
          </button>
        </div>
        <span class="form-hint">
          {{ isElectronApp ? 'Click en el icono para explorar' : 'Ingresa la ruta manualmente' }}
        </span>
      </div>
      <div class="form-group">
        <label class="form-label">Nombre (opcional)</label>
        <input 
          v-model="newFolderName" 
          type="text" 
          class="input" 
          placeholder="Mi Carpeta"
        />
      </div>
      <div class="form-actions">
        <button 
          @click="handleCreateAndScan" 
          class="btn btn-xs btn-primary"
          :disabled="!newFolderPath || creating"
        >
          <FolderPlusIcon :size="14" />
          {{ creating ? 'Agregando...' : 'Agregar Carpeta' }}
        </button>
        <button 
          @click="cancelAddFolder" 
          class="btn btn-xs btn-ghost"
          :disabled="creating"
        >
          Cancelar
        </button>
      </div>
      <div v-if="formError" class="form-error">{{ formError }}</div>
      <div v-if="formSuccess" class="form-success">
        {{ formSuccess }}
        <!-- Barra de progreso sutil mientras se escanea -->
        <div v-if="scanning" class="progress-container">
          <div class="progress-bar-indeterminate"></div>
        </div>
      </div>
    </div>

    <!-- Lista de carpetas -->
    <div class="sidebar-content">
      <FolderListMinimal
        ref="folderListRef" 
        :editable="organizerMode"
        @folder-selected="handleFolderSelected"
        @folder-scanned="handleFolderScanned"
        @folder-deleted="handleFolderDeleted"
        @folder-toggled="handleFolderToggled"
      />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Folder as FolderIcon, FolderPlus as FolderPlusIcon, FolderOpen as FolderOpenIcon, Trash2 as TrashIcon } from 'lucide-vue-next'
import FolderListMinimal from '../features/gallery/components/FolderListMinimal.vue'
import { createFolder, scanFolder, listFolders } from '../features/gallery/api'
import { getImagePaths } from '../features/settings/api'
import { isElectron, selectFolder } from '../utils/electron'

defineProps<{
  organizerMode?: boolean
}>()

const folderListRef = ref<InstanceType<typeof FolderListMinimal> | null>(null)

const emit = defineEmits<{
  folderSelected: [selection: { folderId: string; folderNodeId: number | null }]
  refreshImages: []
}>()

// Exponer método para refrescar carpetas desde fuera
defineExpose({
  refreshFolders: () => {
    if (folderListRef.value) {
      folderListRef.value.refresh()
    }
  }
})

// Estado del formulario
const showAddFolderForm = ref(false)
const newFolderPath = ref('')
const newFolderName = ref('')
const creating = ref(false)
const scanning = ref(false)
const formError = ref<string | null>(null)
const formSuccess = ref<string | null>(null)
const isElectronApp = ref(false)
const loadingTrash = ref(false)

onMounted(() => {
  isElectronApp.value = isElectron()
})

async function handleViewTrash() {
  if (loadingTrash.value) return
  
  loadingTrash.value = true
  try {
    // Obtener ruta de papelera
    const imagePaths = await getImagePaths()
    if (!imagePaths.trash_path) {
      alert('Ruta de papelera no configurada. Configúrala en Settings.')
      return
    }
    
    // Buscar si existe la carpeta de papelera en la DB
    const folders = await listFolders()
    let trashFolder = folders.find(f => f.path === imagePaths.trash_path)
    
    // Si no existe, crearla
    if (!trashFolder) {
      trashFolder = await createFolder({
        path: imagePaths.trash_path,
        name: 'Papelera',
        enabled: true
      })
      
      // Escanear la carpeta para agregar imágenes
      await scanFolder({
        folder_id: trashFolder.id,
        recursive: false,
        create_records: true
      })
      
      // Recargar lista
      if (folderListRef.value) {
        await folderListRef.value.refresh()
      }
    }
    
    // Seleccionar la carpeta de papelera
    if (trashFolder) {
      handleFolderSelected({ folderId: trashFolder.id, folderNodeId: null })
    }
  } catch (err: any) {
    console.error('Error accediendo a papelera:', err)
    alert(err.response?.data?.detail || 'Error al acceder a la papelera')
  } finally {
    loadingTrash.value = false
  }
}

function handleAddFolder() {
  showAddFolderForm.value = true
}

function handleFolderSelected(selection: { folderId: string; folderNodeId: number | null }) {
  emit('folderSelected', selection)
}

function handleFolderScanned(folderId: string) {
  // Emitir evento para refrescar la grilla de imágenes
  emit('refreshImages')
}

function handleFolderDeleted(folderId: string) {
  // Emitir evento para refrescar la grilla de imágenes
  emit('refreshImages')
}

function handleFolderToggled(folderId: string) {
  // Emitir evento para refrescar la grilla de imágenes cuando se activa/desactiva
  emit('refreshImages')
}

async function handleBrowseFolder() {
  const path = await selectFolder()
  if (path) {
    newFolderPath.value = path
    // Auto-generar nombre desde la ruta
    if (!newFolderName.value) {
      const parts = path.split(/[/\\]/)
      newFolderName.value = parts[parts.length - 1] || ''
    }
  }
}

function cancelAddFolder() {
  showAddFolderForm.value = false
  newFolderPath.value = ''
  newFolderName.value = ''
  formError.value = null
  formSuccess.value = null
  scanning.value = false
}

async function handleCreateAndScan() {
  if (!newFolderPath.value) return
  
  creating.value = true
  formError.value = null
  formSuccess.value = null
  
  try {
    // Crear carpeta
    const folder = await createFolder({
      path: newFolderPath.value,
      name: newFolderName.value || undefined,
      enabled: true
    })
    
    formSuccess.value = 'Carpeta agregada, escaneando...'
    scanning.value = true
    
    try {
      // Escanear carpeta automáticamente
      await scanFolder({
        folder_id: folder.id,
        recursive: true,
        create_records: true
      })
      
      formSuccess.value = 'Carpeta agregada y escaneada correctamente'
    } finally {
      scanning.value = false
    }
    
    // Recargar lista de carpetas
    if (folderListRef.value) {
      await folderListRef.value.refresh()
    }
    
    // Emitir evento para refrescar la grilla de imágenes
    emit('refreshImages')
    
    // Limpiar formulario después de un momento
    setTimeout(() => {
      cancelAddFolder()
    }, 1500)
    
  } catch (err: any) {
    formError.value = err.response?.data?.detail || err.message || 'Error al crear/escanear carpeta'
    console.error('Error:', err)
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.add-folder-form {
  padding: 0.75rem;
  border-bottom: 1px solid var(--border-base-300);
  background-color: var(--bg-base-200);
}

.form-group {
  margin-bottom: 0.75rem;
}

.form-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 500;
  margin-bottom: 0.25rem;
  color: var(--text-base);
}

.form-hint {
  display: block;
  font-size: 0.625rem;
  opacity: 0.6;
  margin-top: 0.25rem;
}

.input-with-button {
  display: flex;
  gap: 0.25rem;
}

.input-with-button .input {
  flex: 1;
}

.browse-btn {
  flex-shrink: 0;
  padding: 0.5rem;
}

.form-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.form-error {
  margin-top: 0.5rem;
  padding: 0.5rem;
  font-size: 0.75rem;
  color: #fca5a5;
  background-color: rgba(239, 68, 68, 0.1);
  border-radius: 0.25rem;
}

.form-success {
  margin-top: 0.5rem;
  padding: 0.5rem;
  font-size: 0.75rem;
  color: #86efac;
  background-color: rgba(34, 197, 94, 0.1);
  border-radius: 0.25rem;
}

.progress-container {
  margin-top: 0.5rem;
  height: 4px;
  background-color: rgba(34, 197, 94, 0.2);
  border-radius: 2px;
  overflow: hidden;
  position: relative;
}

.progress-bar-indeterminate {
  height: 100%;
  background-color: #86efac;
  border-radius: 2px;
  animation: progress-indeterminate 1.5s ease-in-out infinite;
  position: relative;
}

.progress-bar-indeterminate::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  right: 0;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.3),
    transparent
  );
  animation: progress-shimmer 1.5s ease-in-out infinite;
}

@keyframes progress-indeterminate {
  0% {
    width: 30%;
    left: -30%;
  }
  50% {
    width: 60%;
    left: 50%;
  }
  100% {
    width: 30%;
    left: 100%;
  }
}

@keyframes progress-shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}
</style>

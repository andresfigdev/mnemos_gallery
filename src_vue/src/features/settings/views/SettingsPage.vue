<template>
  <div class="settings-page">
    <header class="settings-header">
      <h1>
        <SettingsIcon :size="24" />
        Configuración
      </h1>
      <p class="subtitle">Configura las rutas y preferencias de la aplicación</p>
    </header>

    <section class="settings-section">
      <h2>
        <FolderDownIcon :size="20" />
        Sincronización Masiva IMG
      </h2>
      <p class="section-description">
        Sincroniza automáticamente las carpetas raíz dentro de la carpeta maestra IMG, sin duplicar registros existentes.
      </p>

      <div class="settings-form">
        <div class="form-group">
          <label for="master-img-path">
            <FolderOpenIcon :size="16" />
            Ruta maestra IMG
          </label>
          <div class="input-with-button">
            <input
              id="master-img-path"
              type="text"
              v-model="masterImgPath"
              placeholder="D:\Recursos AI\Registro AI SUITE\IMG"
              :disabled="savingMasterPath || syncingMaster"
            />
            <button
              @click="browseMasterImgPath"
              class="btn-browse"
              :disabled="savingMasterPath || syncingMaster"
              title="Seleccionar carpeta"
            >
              <FolderOpenIcon :size="16" />
            </button>
          </div>
          <span class="hint">Cada subcarpeta directa será una carpeta raíz de galería (Alice, Beta, An, etc.).</span>
        </div>

        <div class="form-actions">
          <button
            @click="saveMasterImgPath"
            class="btn-primary"
            :disabled="savingMasterPath || syncingMaster || !hasMasterPathChanges"
          >
            <SaveIcon v-if="!savingMasterPath" :size="16" />
            <span v-if="savingMasterPath" class="spinner"></span>
            {{ savingMasterPath ? 'Guardando...' : 'Guardar Ruta Maestra' }}
          </button>
          <button
            @click="runMasterSync"
            class="btn-primary"
            :disabled="syncingMaster || !masterImgPath.trim()"
          >
            <span v-if="syncingMaster" class="spinner"></span>
            {{ syncingMaster ? 'Sincronizando...' : 'Sincronizar Carpeta Maestra' }}
          </button>
        </div>

        <span v-if="masterMessage" :class="['save-message', masterMessageType]">
          {{ masterMessage }}
        </span>

        <div v-if="masterSyncResult" class="sync-result">
          <p>
            Detectadas: <strong>{{ masterSyncResult.roots_detected }}</strong> ·
            Nuevas: <strong>{{ masterSyncResult.roots_created }}</strong> ·
            Existentes: <strong>{{ masterSyncResult.roots_existing }}</strong>
          </p>
          <ul>
            <li v-for="root in masterSyncResult.scanned_roots" :key="root.folder_id">
              {{ root.folder_name }} — nuevas: {{ root.created_count }}, actualizadas: {{ root.updated_count }},
              total detectadas: {{ root.image_count }}
            </li>
          </ul>
          <p v-if="masterSyncResult.errors.length > 0" class="sync-errors">
            Errores: {{ masterSyncResult.errors.join(' | ') }}
          </p>
        </div>

        <div class="naming-maintenance">
          <div>
            <strong>Corregir nombres pendientes</strong>
            <p class="hint">
              Revisa toda la ruta maestra. Solo propone cambios para archivos que no usan el nombre de su carpeta seguido de un correlativo.
            </p>
          </div>
          <div class="form-actions compact-actions">
            <button
              @click="previewMissingNames"
              class="btn-primary"
              :disabled="checkingNames || applyingNames || syncingMaster || !masterImgPath.trim()"
            >
              <span v-if="checkingNames" class="spinner"></span>
              {{ checkingNames ? 'Revisando...' : 'Revisar nombres' }}
            </button>
            <button
              v-if="namingPreview && namingPreview.rename_count > 0"
              @click="applyMissingNames"
              class="btn-primary"
              :disabled="checkingNames || applyingNames"
            >
              <span v-if="applyingNames" class="spinner"></span>
              {{ applyingNames ? 'Corrigiendo...' : `Renombrar ${namingPreview.rename_count} imágenes` }}
            </button>
          </div>

          <span v-if="namingMessage" :class="['save-message', namingMessageType]">
            {{ namingMessage }}
          </span>

          <div v-if="namingPreview" class="sync-result">
            <p>
              Revisadas: <strong>{{ namingPreview.images_scanned }}</strong> ·
              Ya correctas: <strong>{{ namingPreview.unchanged_count }}</strong> ·
              Pendientes: <strong>{{ namingPreview.rename_count }}</strong>
            </p>
            <p v-if="namingPreview.unassigned_count > 0" class="sync-errors">
              {{ namingPreview.unassigned_count }} imágenes no están asociadas a una carpeta indexada. Sincroniza la carpeta maestra antes de corregirlas.
            </p>
            <ul v-if="namingPreview.entries.length > 0" class="naming-preview-list">
              <li v-for="entry in namingPreview.entries.slice(0, 10)" :key="entry.image_id">
                {{ entry.old_path }} → {{ entry.new_path }}
              </li>
            </ul>
            <p v-if="namingPreview.rename_count > 10" class="hint">
              Se muestran 10 de {{ namingPreview.rename_count }} cambios.
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- Sección: Rutas de Imágenes -->
    <section class="settings-section">
      <h2>
        <FolderDownIcon :size="20" />
        Rutas de Imágenes
      </h2>
      <p class="section-description">
        Define dónde se almacenarán las imágenes movidas y organizadas
      </p>

      <div class="settings-form">
        <!-- Ruta de Papelera -->
        <div class="form-group">
          <label for="trash-path">
            <FolderOpenIcon :size="16" />
            Ruta de Papelera de Reciclaje
          </label>
          <div class="input-with-button">
            <input 
              id="trash-path"
              type="text" 
              v-model="trashPath" 
              placeholder="C:\Papelera AI"
              :disabled="savingImages"
            />
            <button 
              @click="browseTrash" 
              class="btn-browse"
              :disabled="savingImages"
              title="Seleccionar carpeta"
            >
              <FolderOpenIcon :size="16" />
            </button>
          </div>
          <span class="hint">Carpeta donde se moverán las imágenes eliminadas (no se borran, solo se mueven)</span>
        </div>

        <!-- Ruta de IMG Ordenadas -->
        <div class="form-group">
          <label for="img-sorted-path">
            <FolderOpenIcon :size="16" />
            Ruta para IMG Ordenadas
          </label>
          <div class="input-with-button">
            <input 
              id="img-sorted-path"
              type="text" 
              v-model="imgSortedPath" 
              placeholder="C:\IMG Ordenadas"
              :disabled="savingImages"
            />
            <button 
              @click="browseImgSorted" 
              class="btn-browse"
              :disabled="savingImages"
              title="Seleccionar carpeta"
            >
              <FolderOpenIcon :size="16" />
            </button>
          </div>
          <span class="hint">Opcional. Déjala vacía para desactivar la vista Organizar y usar solo la ruta maestra.</span>
        </div>

        <!-- Botón Guardar -->
        <div class="form-actions">
          <button 
            @click="saveImagePaths" 
            class="btn-primary"
            :disabled="savingImages || !hasImageChanges"
          >
            <SaveIcon v-if="!savingImages" :size="16" />
            <span v-if="savingImages" class="spinner"></span>
            {{ savingImages ? 'Guardando...' : 'Guardar Rutas' }}
          </button>
          
          <span v-if="saveImageMessage" :class="['save-message', saveImageMessageType]">
            {{ saveImageMessage }}
          </span>
        </div>
      </div>
    </section>

    <!-- Sección: Preferencias -->
    <section class="settings-section">
      <h2>
        <SettingsIcon :size="20" />
        Preferencias
      </h2>
      <p class="section-description">
        Configura el comportamiento de la aplicación
      </p>

      <div class="settings-form">
        <!-- Confirmar antes de mover a papelera -->
        <div class="form-group">
          <label style="display: flex; align-items: center; justify-content: space-between; cursor: pointer;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <SettingsIcon :size="16" />
              <span>Preguntar antes de mover a papelera</span>
            </div>
            <input 
              type="checkbox" 
              class="toggle toggle-primary"
              v-model="confirmTrashMove"
              :disabled="savingPreferences"
            />
          </label>
          <span class="hint">Si está activado, se mostrará una confirmación antes de mover imágenes a la papelera</span>
        </div>

        <!-- Cargar imagen real en gestión masiva -->
        <div class="form-group">
          <label class="form-label">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <SettingsIcon :size="16" />
              <span>Cargar imagen real en gestión masiva</span>
            </div>
            <input 
              type="checkbox" 
              class="toggle toggle-primary"
              v-model="loadFullImageInBulk"
              :disabled="savingPreferences"
            />
          </label>
          <span class="hint">Si está activado, se mostrará la imagen real en lugar de la miniatura en la vista de gestión masiva. Puede afectar el rendimiento con muchas imágenes.</span>
        </div>

        <div class="form-group">
          <label class="form-label">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <SettingsIcon :size="16" />
              <span>Mostrar carpeta ordenada como origen en Organizar</span>
            </div>
            <input
              type="checkbox"
              class="toggle toggle-primary"
              v-model="showOrderedFolderInOrganizer"
              :disabled="savingPreferences"
            />
          </label>
          <span class="hint">Permite volver a seleccionar la carpeta de destino desde el panel izquierdo para corregir movimientos. Está desactivado por defecto.</span>
        </div>

        <!-- Botón Guardar -->
        <div class="form-actions">
          <button 
            @click="savePreferences" 
            class="btn-primary"
            :disabled="savingPreferences || !hasPreferenceChanges"
          >
            <SaveIcon v-if="!savingPreferences" :size="16" />
            <span v-if="savingPreferences" class="spinner"></span>
            {{ savingPreferences ? 'Guardando...' : 'Guardar Preferencias' }}
          </button>
          
          <span v-if="savePreferenceMessage" :class="['save-message', savePreferenceMessageType]">
            {{ savePreferenceMessage }}
          </span>
        </div>
      </div>
    </section>

    <!-- Sección: Información del Sistema -->
    <section class="settings-section">
      <h2>
        <InfoIcon :size="20" />
        Información del Sistema
      </h2>
      
      <div class="info-grid">
        <div class="info-item">
          <span class="info-label">Plataforma</span>
          <span class="info-value">{{ appInfo?.platform || 'Web' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Versión</span>
          <span class="info-value">{{ appInfo?.version || '1.0.0' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Modo</span>
          <span class="info-value">{{ appInfo?.isPackaged ? 'Producción' : 'Desarrollo' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Electron</span>
          <span class="info-value">{{ isElectronApp ? 'Sí' : 'No (Navegador)' }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { 
  Settings as SettingsIcon, 
  FolderDown as FolderDownIcon,
  FolderOpen as FolderOpenIcon,
  Save as SaveIcon,
  Info as InfoIcon
} from 'lucide-vue-next'
import { getImagePaths, updateImagePaths, getMasterImgPath, updateMasterImgPath, getSetting, updateSetting, type ImagePaths } from '../api'
import {
  applyMasterMissingNames,
  previewMasterMissingNames,
  syncMasterFolders,
  type MasterNamingResponse,
  type SyncMasterFoldersResponse,
} from '../../gallery/api'
import { selectFolder, isElectron, getAppInfo } from '../../../utils/electron'

// Estado
const appInfo = ref<{ name: string; version: string; isPackaged: boolean; platform: string } | null>(null)
const isElectronApp = ref(false)
const DEFAULT_MASTER_PATH = 'D:\\Recursos AI\\Registro AI SUITE\\IMG'
const masterImgPath = ref(DEFAULT_MASTER_PATH)
const originalMasterImgPath = ref(DEFAULT_MASTER_PATH)
const savingMasterPath = ref(false)
const syncingMaster = ref(false)
const masterMessage = ref<string | null>(null)
const masterMessageType = ref<'success' | 'error'>('success')
const masterSyncResult = ref<SyncMasterFoldersResponse | null>(null)
const checkingNames = ref(false)
const applyingNames = ref(false)
const namingPreview = ref<MasterNamingResponse | null>(null)
const namingMessage = ref<string | null>(null)
const namingMessageType = ref<'success' | 'error'>('success')

// Estado para rutas de imágenes
const trashPath = ref('')
const imgSortedPath = ref('')
const originalImagePaths = ref<ImagePaths>({ trash_path: null, img_sorted_path: null })
const savingImages = ref(false)
const saveImageMessage = ref<string | null>(null)
const saveImageMessageType = ref<'success' | 'error'>('success')

// Estado para preferencias
const confirmTrashMove = ref(true)
const originalConfirmTrashMove = ref(true)
const loadFullImageInBulk = ref(false)
const originalLoadFullImageInBulk = ref(false)
const showOrderedFolderInOrganizer = ref(false)
const originalShowOrderedFolderInOrganizer = ref(false)
const savingPreferences = ref(false)
const savePreferenceMessage = ref<string | null>(null)
const savePreferenceMessageType = ref<'success' | 'error'>('success')

// Computed
const hasMasterPathChanges = computed(() => masterImgPath.value !== originalMasterImgPath.value)

const hasImageChanges = computed(() => {
  return trashPath.value !== (originalImagePaths.value.trash_path || '') ||
         imgSortedPath.value !== (originalImagePaths.value.img_sorted_path || '')
})

const hasPreferenceChanges = computed(() => {
  return confirmTrashMove.value !== originalConfirmTrashMove.value ||
         loadFullImageInBulk.value !== originalLoadFullImageInBulk.value ||
         showOrderedFolderInOrganizer.value !== originalShowOrderedFolderInOrganizer.value
})

// Métodos
async function loadMasterImgPath() {
  try {
    const data = await getMasterImgPath()
    const value = data.img_master_path || DEFAULT_MASTER_PATH
    masterImgPath.value = value
    originalMasterImgPath.value = value
  } catch (err: any) {
    console.error('Error al cargar ruta maestra IMG:', err)
    masterMessage.value = 'Error al cargar ruta maestra'
    masterMessageType.value = 'error'
  }
}

async function browseMasterImgPath() {
  const path = await selectFolder()
  if (path) {
    masterImgPath.value = path
  }
}

async function saveMasterImgPath() {
  savingMasterPath.value = true
  masterMessage.value = null
  try {
    const updated = await updateMasterImgPath(masterImgPath.value || null)
    const value = updated.img_master_path || DEFAULT_MASTER_PATH
    masterImgPath.value = value
    originalMasterImgPath.value = value
    masterMessage.value = '✓ Ruta maestra guardada correctamente'
    masterMessageType.value = 'success'
    setTimeout(() => {
      masterMessage.value = null
    }, 3000)
  } catch (err: any) {
    console.error('Error al guardar ruta maestra IMG:', err)
    masterMessage.value = err.response?.data?.detail || 'Error al guardar ruta maestra'
    masterMessageType.value = 'error'
  } finally {
    savingMasterPath.value = false
  }
}

async function runMasterSync() {
  syncingMaster.value = true
  masterMessage.value = null
  masterSyncResult.value = null
  try {
    const result = await syncMasterFolders(masterImgPath.value)
    masterSyncResult.value = result
    masterMessage.value = '✓ Sincronización masiva completada'
    masterMessageType.value = 'success'
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
  } catch (err: any) {
    console.error('Error al sincronizar carpeta maestra:', err)
    masterMessage.value = err.response?.data?.detail || 'Error en sincronización masiva'
    masterMessageType.value = 'error'
  } finally {
    syncingMaster.value = false
  }
}

async function previewMissingNames() {
  checkingNames.value = true
  namingMessage.value = null
  namingPreview.value = null
  try {
    namingPreview.value = await previewMasterMissingNames()
    namingMessageType.value = 'success'
    namingMessage.value = namingPreview.value.rename_count > 0
      ? `Se encontraron ${namingPreview.value.rename_count} imágenes con nombre pendiente.`
      : '✓ Todas las imágenes indexadas ya tienen la nomenclatura de su carpeta.'
  } catch (err: any) {
    console.error('Error al revisar nomenclatura:', err)
    namingMessageType.value = 'error'
    namingMessage.value = err.response?.data?.detail || 'Error al revisar los nombres'
  } finally {
    checkingNames.value = false
  }
}

async function applyMissingNames() {
  if (!namingPreview.value || namingPreview.value.rename_count < 1) return
  applyingNames.value = true
  namingMessage.value = null
  try {
    const result = await applyMasterMissingNames()
    namingPreview.value = null
    namingMessageType.value = 'success'
    namingMessage.value = `✓ Se renombraron ${result.renamed_count || 0} imágenes. Las que ya estaban correctas no se modificaron.`
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
  } catch (err: any) {
    console.error('Error al corregir nomenclatura:', err)
    namingMessageType.value = 'error'
    namingMessage.value = err.response?.data?.detail || 'Error al corregir los nombres'
  } finally {
    applyingNames.value = false
  }
}

async function loadImagePaths() {
  try {
    const paths = await getImagePaths()
    trashPath.value = paths.trash_path || ''
    imgSortedPath.value = paths.img_sorted_path || ''
    originalImagePaths.value = paths
  } catch (err: any) {
    console.error('Error al cargar rutas de imágenes:', err)
    saveImageMessage.value = 'Error al cargar configuración'
    saveImageMessageType.value = 'error'
  }
}

async function browseTrash() {
  const path = await selectFolder()
  if (path) {
    trashPath.value = path
  }
}

async function browseImgSorted() {
  const path = await selectFolder()
  if (path) {
    imgSortedPath.value = path
  }
}

async function saveImagePaths() {
  savingImages.value = true
  saveImageMessage.value = null
  
  try {
    const updated = await updateImagePaths({
      trash_path: trashPath.value || null,
      img_sorted_path: imgSortedPath.value || null
    })
    
    originalImagePaths.value = updated
    trashPath.value = updated.trash_path || ''
    imgSortedPath.value = updated.img_sorted_path || ''
    
    saveImageMessage.value = '✓ Rutas guardadas correctamente'
    saveImageMessageType.value = 'success'
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    window.dispatchEvent(new CustomEvent('galleryRefresh'))
    
    setTimeout(() => {
      saveImageMessage.value = null
    }, 3000)
  } catch (err: any) {
    console.error('Error al guardar rutas de imágenes:', err)
    saveImageMessage.value = err.response?.data?.detail || 'Error al guardar configuración'
    saveImageMessageType.value = 'error'
  } finally {
    savingImages.value = false
  }
}

async function loadPreferences() {
  try {
    const setting = await getSetting('confirm_trash_move')
    // Si no existe, usar true por defecto
    confirmTrashMove.value = setting.value === null || setting.value === undefined || setting.value.toLowerCase() === 'true'
    originalConfirmTrashMove.value = confirmTrashMove.value
  } catch (err: any) {
    // Si no existe el setting, usar true por defecto
    if (err.response?.status === 404) {
      confirmTrashMove.value = true
      originalConfirmTrashMove.value = true
    } else {
      console.error('Error al cargar preferencias:', err)
    }
  }
  
  try {
    const setting = await getSetting('load_full_image_in_bulk')
    // Si no existe, usar false por defecto
    loadFullImageInBulk.value = setting.value !== null && setting.value !== undefined && setting.value.toLowerCase() === 'true'
    originalLoadFullImageInBulk.value = loadFullImageInBulk.value
  } catch (err: any) {
    // Si no existe el setting, usar false por defecto
    if (err.response?.status === 404) {
      loadFullImageInBulk.value = false
      originalLoadFullImageInBulk.value = false
    } else {
      console.error('Error al cargar preferencia load_full_image_in_bulk:', err)
    }
  }

  try {
    const setting = await getSetting('show_ordered_folder_in_organizer')
    showOrderedFolderInOrganizer.value = setting.value?.toLowerCase() === 'true'
    originalShowOrderedFolderInOrganizer.value = showOrderedFolderInOrganizer.value
  } catch (err: any) {
    if (err.response?.status === 404) {
      showOrderedFolderInOrganizer.value = false
      originalShowOrderedFolderInOrganizer.value = false
    } else {
      console.error('Error al cargar preferencia show_ordered_folder_in_organizer:', err)
    }
  }
}

async function savePreferences() {
  savingPreferences.value = true
  savePreferenceMessage.value = null
  
  try {
    await updateSetting('confirm_trash_move', confirmTrashMove.value.toString(), 'Preguntar antes de mover imágenes a la papelera')
    await updateSetting('load_full_image_in_bulk', loadFullImageInBulk.value.toString(), 'Cargar imagen real en lugar de miniatura en gestión masiva')
    await updateSetting('show_ordered_folder_in_organizer', showOrderedFolderInOrganizer.value.toString(), 'Mostrar la carpeta ordenada como origen en la vista Organizar')
    
    originalConfirmTrashMove.value = confirmTrashMove.value
    originalLoadFullImageInBulk.value = loadFullImageInBulk.value
    originalShowOrderedFolderInOrganizer.value = showOrderedFolderInOrganizer.value
    window.dispatchEvent(new CustomEvent('organizerSourceVisibilityChanged', {
      detail: { enabled: showOrderedFolderInOrganizer.value },
    }))
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    
    savePreferenceMessage.value = '✓ Preferencias guardadas correctamente'
    savePreferenceMessageType.value = 'success'
    
    setTimeout(() => {
      savePreferenceMessage.value = null
    }, 3000)
  } catch (err: any) {
    console.error('Error al guardar preferencias:', err)
    savePreferenceMessage.value = err.response?.data?.detail || 'Error al guardar preferencias'
    savePreferenceMessageType.value = 'error'
  } finally {
    savingPreferences.value = false
  }
}

onMounted(async () => {
  isElectronApp.value = isElectron()
  appInfo.value = await getAppInfo()
  await loadMasterImgPath()
  await loadImagePaths()
  await loadPreferences()
})
</script>

<style scoped>
.settings-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
}

.settings-header {
  margin-bottom: 2rem;
}

.settings-header h1 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0 0 0.5rem 0;
  color: var(--text-color);
}

.subtitle {
  color: var(--text-color);
  opacity: 0.7;
  margin: 0;
  font-size: 0.9rem;
}

.settings-section {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.5rem;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.settings-section h2 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 0.5rem 0;
  color: var(--text-color);
}

.section-description {
  color: var(--text-color);
  opacity: 0.7;
  font-size: 0.85rem;
  margin: 0 0 1.5rem 0;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--text-color);
}

.input-with-button {
  display: flex;
  gap: 0.5rem;
}

.input-with-button input {
  flex: 1;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--input-border);
  border-radius: 0.375rem;
  background: var(--input-bg);
  color: var(--text-color);
  font-size: 0.9rem;
}

.input-with-button input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(66, 153, 225, 0.2);
}

.input-with-button input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-browse {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 0.75rem;
  border: 1px solid var(--card-border);
  border-radius: 0.375rem;
  background: var(--card-bg);
  color: var(--text-color);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-browse:hover:not(:disabled) {
  background: var(--card-border);
}

.btn-browse:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hint {
  font-size: 0.8rem;
  color: var(--text-color);
  opacity: 0.6;
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

.btn-primary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1.25rem;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--button-hover-bg);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.save-message {
  font-size: 0.875rem;
  font-weight: 500;
}

.save-message.success {
  color: var(--success-color);
}

.save-message.error {
  color: var(--error-color);
}

.sync-result {
  padding: 0.65rem 0.8rem;
  border-radius: 0.45rem;
  border: 1px solid var(--border-color);
  background: var(--input-bg);
  font-size: 0.82rem;
}

.sync-result p {
  margin: 0 0 0.35rem 0;
}

.sync-result ul {
  margin: 0;
  padding-left: 1rem;
}

.sync-errors {
  margin-top: 0.5rem;
  color: var(--error-color);
}

.naming-maintenance {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

.naming-maintenance p {
  margin: 0.25rem 0 0;
}

.compact-actions {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
  flex-wrap: wrap;
}

.naming-preview-list {
  max-height: 12rem;
  overflow: auto;
  word-break: break-all;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.info-label {
  font-size: 0.8rem;
  color: var(--text-color);
  opacity: 0.6;
}

.info-value {
  font-size: 0.95rem;
  font-weight: 500;
  color: var(--text-color);
}
</style>


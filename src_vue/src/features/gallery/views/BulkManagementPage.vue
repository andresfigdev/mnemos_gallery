<template>
  <div class="bulk-management-page" style="display: flex; flex-direction: column; height: 100%; overflow: hidden; position: relative;">
    <!-- Header simplificado -->
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 1rem; border-bottom: 1px solid var(--border-base-300); flex-shrink: 0;">
      <div style="display: flex; align-items: center; gap: 0.75rem;">
        <button
          @click="sidebarOpen = !sidebarOpen"
          class="btn btn-sm btn-ghost"
          title="Mostrar/ocultar panel de opciones"
        >
          <ChevronLeft v-if="sidebarOpen" :size="18" :style="{ transform: 'rotate(180deg)' }" />
          <ChevronRight v-else :size="18" />
        </button>
        <h2 style="font-size: 1.125rem; font-weight: 600;">Gestión Masiva de Imágenes</h2>
        <Table :size="20" />
      </div>
      <div style="display: flex; align-items: center; gap: 1rem;">
        <span v-if="selectedImageIds.size > 0" style="font-size: 0.875rem; opacity: 0.95; font-weight: 500; color: #cbb6ff;">
          {{ selectedImageIds.size }} imagen{{ selectedImageIds.size !== 1 ? 'es' : '' }} seleccionada{{ selectedImageIds.size !== 1 ? 's' : '' }}
        </span>
        <span style="font-size: 0.875rem; opacity: 0.7;">
          {{ filteredImages.length }} de {{ total }} imagen{{ total !== 1 ? 'es' : '' }}
        </span>
      </div>
    </div>

    <!-- Contenedor principal: Sidebar + Tabla -->
    <div style="display: flex; flex: 1; overflow: hidden;">
      <!-- Panel lateral izquierdo (colapsable) -->
      <div
        class="sidebar-panel"
        :style="{
          width: sidebarOpen ? '320px' : '0',
          minWidth: sidebarOpen ? '320px' : '0',
          transition: 'width 0.3s ease, min-width 0.3s ease',
          overflow: sidebarOpen ? 'auto' : 'hidden',
          borderRight: sidebarOpen ? '1px solid var(--border-base-300)' : 'none',
          backgroundColor: 'var(--bg-base-100)',
          flexShrink: 0
        }"
      >
        <div v-if="sidebarOpen" style="padding: 1rem; display: flex; flex-direction: column; gap: 1rem;">
          <!-- Búsqueda -->
          <div>
            <label style="font-size: 0.75rem; font-weight: 600; opacity: 0.8; margin-bottom: 0.5rem; display: block;">
              BÚSQUEDA
            </label>
            <div style="position: relative;">
              <input
                v-model="searchFilter"
                type="text"
                placeholder="Buscar por modelo o LoRA..."
                class="input input-bordered input-sm w-full"
                style="padding-left: 2.5rem; font-size: 0.875rem;"
              />
              <Search :size="16" style="position: absolute; left: 0.75rem; top: 50%; transform: translateY(-50%); opacity: 0.5; pointer-events: none;" />
            </div>
            <button
              v-if="searchFilter"
              @click="searchFilter = ''"
              class="btn btn-xs btn-ghost mt-1"
              title="Limpiar búsqueda"
            >
              <X :size="12" />
              Limpiar
            </button>
          </div>

          <!-- Mover a carpeta -->
          <div v-if="selectedImageIds.size > 0">
            <label style="font-size: 0.75rem; font-weight: 600; opacity: 0.8; margin-bottom: 0.5rem; display: block;">
              MOVER A CARPETA
            </label>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
              <select
                v-model="selectedFolderName"
                class="select select-bordered select-sm w-full"
                style="font-size: 0.875rem;"
                :disabled="movingImages || loadingFolders"
              >
                <option value="">-- Seleccionar carpeta --</option>
                <option v-for="folder in sortedFolders" :key="folder" :value="folder">
                  {{ folder }}
                </option>
                <option value="__NEW__">+ Crear nueva carpeta</option>
              </select>
              <input
                v-if="selectedFolderName === '__NEW__'"
                v-model="newFolderName"
                type="text"
                placeholder="Nombre de la nueva carpeta"
                class="input input-bordered input-sm w-full"
                style="font-size: 0.875rem;"
                :disabled="movingImages"
                @keyup.enter="moveImagesToFolder"
              />
              <button
                @click="moveImagesToFolder"
                class="btn btn-sm btn-primary w-full"
                :disabled="movingImages || !canMoveImages || loadingFolders"
              >
                <span v-if="movingImages" class="loading loading-spinner loading-xs"></span>
                <span v-else>Mover</span>
              </button>
              <div v-if="movingImages" style="font-size: 0.75rem; opacity: 0.7; text-align: center;">
                Moviendo imágenes...
              </div>
            </div>
          </div>

          <!-- Asignar Modelo -->
          <div v-if="selectedImageIds.size > 0">
            <label style="font-size: 0.75rem; font-weight: 600; opacity: 0.8; margin-bottom: 0.5rem; display: block;">
              ASIGNAR MODELO
            </label>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
              <datalist id="bulk-model-suggestions">
                <option v-for="name in modelNameSuggestions" :key="name" :value="name" />
              </datalist>
              <input
                v-model="bulkSelectedModel"
                type="text"
                class="input input-bordered input-sm w-full"
                style="font-size: 0.875rem;"
                list="bulk-model-suggestions"
                placeholder="Nombre del checkpoint (.safetensors)"
                :disabled="bulkSavingModel"
              />
              <button
                @click="applyBulkModelToSelected"
                class="btn btn-sm btn-primary w-full"
                :disabled="bulkSavingModel || !bulkSelectedModel"
              >
                <span v-if="bulkSavingModel" class="loading loading-spinner loading-xs"></span>
                <Check v-else :size="14" />
                Guardar
              </button>
              <div v-if="bulkSavingModel" style="font-size: 0.75rem; opacity: 0.7; text-align: center;">
                Actualizando {{ bulkProgressModel.current }} de {{ bulkProgressModel.total }} imágenes...
              </div>
            </div>
          </div>

          <!-- Agregar LoRA -->
          <div v-if="selectedImageIds.size > 0">
            <label style="font-size: 0.75rem; font-weight: 600; opacity: 0.8; margin-bottom: 0.5rem; display: block;">
              AGREGAR LoRA
            </label>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
              <datalist id="bulk-lora-suggestions">
                <option v-for="name in loraNameSuggestions" :key="name" :value="name" />
              </datalist>
              <input
                v-model="bulkSelectedLora"
                type="text"
                class="input input-bordered input-sm w-full"
                style="font-size: 0.875rem;"
                list="bulk-lora-suggestions"
                placeholder="Nombre del LoRA"
                :disabled="bulkSavingLora"
              />
              <button
                @click="applyBulkLoraToSelected"
                class="btn btn-sm btn-primary w-full"
                :disabled="bulkSavingLora || !bulkSelectedLora"
              >
                <span v-if="bulkSavingLora" class="loading loading-spinner loading-xs"></span>
                <Check v-else :size="14" />
                Agregar
              </button>
              <div v-if="bulkSavingLora" style="font-size: 0.75rem; opacity: 0.7; text-align: center;">
                Agregando LoRA a {{ bulkProgressLora.current }} de {{ bulkProgressLora.total }} imágenes...
              </div>
              <div style="font-size: 0.7rem; opacity: 0.75; line-height: 1.4; padding: 0.5rem; background-color: rgba(139, 92, 246, 0.12); border: 1px solid rgba(139, 92, 246, 0.25); border-radius: 0.25rem;">
                💡 Solo agrega LoRAs nuevos. No reemplaza los existentes.
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Contenido principal (Tabla) -->
      <div style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
        <!-- Loading -->
        <div v-if="loading && images.length === 0" style="display: flex; align-items: center; justify-content: center; flex: 1;">
          <div style="display: flex; flex-direction: column; align-items: center; gap: 0.5rem;">
            <span class="loading loading-spinner loading-lg"></span>
            <p style="font-size: 0.875rem; opacity: 0.7;">Cargando imágenes...</p>
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="alert alert-error" style="margin: 1rem;">
          <AlertCircle :size="20" />
          <span>Error: {{ error }}</span>
          <button @click="loadImages" class="btn btn-sm btn-ghost mt-2">Reintentar</button>
        </div>

        <!-- Tabla central -->
        <div 
          v-else 
          ref="tableContainerRef" 
          style="flex: 1; overflow: auto;"
        >
      <div v-if="filteredImages.length === 0" style="display: flex; align-items: center; justify-content: center; height: 100%;">
        <p style="font-size: 0.875rem; opacity: 0.5;">
          {{ searchFilter ? 'No se encontraron imágenes que coincidan con la búsqueda' : 'No hay imágenes para mostrar' }}
        </p>
      </div>
      
      <table v-else class="table table-zebra" style="width: 100%;">
        <thead style="position: sticky; top: 0; background-color: var(--bg-base-100); z-index: 10;">
          <tr>
            <th style="width: 3rem;">
              <input 
                type="checkbox" 
                class="checkbox checkbox-sm" 
                :checked="allSelected"
                :indeterminate="someSelected"
                @change="toggleSelectAll"
                title="Seleccionar todas las imágenes visibles"
              />
            </th>
            <th style="width: 5rem;">Miniatura</th>
            <th>Nombre</th>
            <!-- Columnas ORIGINALES (read-only, del JSON) -->
            <th style="opacity: 0.6;">
              <div style="display: flex; align-items: center; gap: 0.25rem;">
                <span style="font-size: 0.75rem;">Modelo Original</span>
              </div>
            </th>
            <th style="opacity: 0.6;">
              <div style="display: flex; align-items: center; gap: 0.25rem;">
                <span style="font-size: 0.75rem;">LoRAs Originales</span>
              </div>
            </th>
            <!-- Columnas VINCULADAS (editables, desde tablas satélite) -->
            <th>
              <span>Modelo Vinculado</span>
            </th>
            <th>
              <span>LoRAs Vinculados</span>
            </th>
            <th style="width: 8rem;">Resolución</th>
            <th style="width: 7rem;">Tamaño</th>
            <th>Carpeta</th>
          </tr>
        </thead>
        <tbody>
          <tr 
            v-for="(image, index) in filteredImages" 
            :key="image.id"
            :class="{ 'row-selected': selectedImageIds.has(image.id) }"
            style="cursor: pointer;"
            @click="handleRowClick(image.id, index, $event)"
          >
            <td @click.stop>
              <input 
                type="checkbox" 
                class="checkbox checkbox-sm" 
                :checked="selectedImageIds.has(image.id)"
                @change="handleCheckboxChange(image.id, index, $event)"
              />
            </td>
            <td @click.stop>
              <div 
                style="width: 4rem; height: 4rem; background-color: var(--bg-base-300); border: 1px solid var(--border-base-300); border-radius: 0.375rem; overflow: hidden; display: flex; align-items: center; justify-content: center;"
                @click="openImageViewer(image.id)"
              >
                <img 
                  v-if="!imageLoadErrors[image.id]"
                  :src="getThumbnailUrl(image.id)" 
                  :alt="getImageName(image)"
                  style="width: 100%; height: 100%; object-fit: cover; cursor: pointer;"
                  @error="imageLoadErrors[image.id] = true"
                  @click.stop="openImageViewer(image.id)"
                />
                <div v-else style="font-size: 0.75rem; opacity: 0.5;">❌</div>
              </div>
            </td>
            <td>
              <div style="font-weight: 500; font-size: 0.875rem;">{{ getImageName(image) }}</div>
            </td>
            
            <!-- COLUMNA: Modelo Original (read-only, del JSON) -->
            <td>
              <div style="font-size: 0.875rem; opacity: 0.6;">
                {{ getModelName(image) || '-' }}
              </div>
            </td>
            
            <!-- COLUMNA: LoRAs Originales (read-only, del JSON) -->
            <td>
              <div style="display: flex; flex-direction: column; gap: 0.25rem; opacity: 0.6;">
                <template v-if="getLoras(image).length > 0">
                  <div 
                    v-for="(lora, idx) in getLoras(image)" 
                    :key="idx"
                    style="font-size: 0.875rem;"
                  >
                    {{ lora.name }}
                  </div>
                </template>
                <div v-else style="font-size: 0.875rem;">-</div>
              </div>
            </td>
            
            <!-- COLUMNA: Modelo Vinculado (editable) -->
            <td @click.stop>
              <div style="display: flex; flex-direction: column; gap: 0.25rem;">
                <!-- Modo edición individual con DROPDOWN -->
                <div v-if="editingModelId === image.id" style="display: flex; flex-direction: column; gap: 0.5rem; min-width: 15rem;">
                  <datalist :id="'row-model-suggestions-' + image.id">
                    <option v-for="name in modelNameSuggestions" :key="name" :value="name" />
                  </datalist>
                  <input
                    v-model="editingModelValue"
                    type="text"
                    class="input input-sm input-bordered"
                    style="width: 100%; font-size: 0.875rem;"
                    :list="'row-model-suggestions-' + image.id"
                    :disabled="savingMetadata"
                    placeholder="Nombre del modelo"
                  />
                  <div style="display: flex; gap: 0.25rem; justify-content: flex-end;">
                    <button 
                      @click="cancelModelEdit" 
                      class="btn btn-xs btn-ghost"
                      :disabled="savingMetadata"
                    >
                      Cancelar
                    </button>
                    <button 
                      @click="saveModelEdit(image)" 
                      class="btn btn-xs btn-primary"
                      :disabled="savingMetadata"
                    >
                      <span v-if="savingMetadata" class="loading loading-spinner loading-xs"></span>
                      <Check v-else :size="12" />
                      Aplicar
                    </button>
                  </div>
                </div>
                <!-- Modo visualización (sin checkbox, solo texto clickeable) -->
                <div v-else>
                  <span 
                    style="font-size: 0.875rem; opacity: 0.8; cursor: pointer;"
                    @click="startEditingModel(image)"
                    :title="getLinkedModelName(image) || 'Sin modelo vinculado - Click para editar'"
                  >
                    {{ getLinkedModelName(image) || '-' }}
                  </span>
                </div>
              </div>
            </td>
            
            <!-- COLUMNA: LoRAs Vinculados (editables) -->
            <td @click.stop>
              <div style="display: flex; flex-direction: column; gap: 0.25rem;">
                <!-- Modo edición individual con DROPDOWNS -->
                <div v-if="editingLorasId === image.id" style="display: flex; flex-direction: column; gap: 0.5rem; min-width: 18rem; max-width: 20rem;">
                  <!-- Lista de LoRAs editables -->
                  <div 
                    v-for="(lora, idx) in editingLorasValue" 
                    :key="idx"
                    style="display: flex; gap: 0.25rem; align-items: center;"
                  >
                    <datalist :id="'row-lora-suggestions-' + image.id + '-' + idx">
                      <option v-for="name in loraNameSuggestions" :key="name" :value="name" />
                    </datalist>
                    <input
                      v-model="lora.name"
                      type="text"
                      class="input input-sm input-bordered"
                      style="flex: 1; font-size: 0.875rem;"
                      :list="'row-lora-suggestions-' + image.id + '-' + idx"
                      :disabled="savingMetadata"
                      placeholder="Nombre del LoRA"
                    />
                    <button 
                      @click="removeLora(idx)" 
                      class="btn btn-xs btn-ghost text-error"
                      :disabled="savingMetadata"
                      title="Quitar este LoRA"
                    >
                      <X :size="12" />
                    </button>
                  </div>
                  
                  <!-- Botones de acción -->
                  <div style="display: flex; gap: 0.25rem; flex-wrap: wrap;">
                    <button 
                      @click="addLora" 
                      class="btn btn-xs btn-ghost"
                      :disabled="savingMetadata"
                      style="flex: 1;"
                    >
                      + Agregar LoRA
                    </button>
                  </div>
                  <div style="display: flex; gap: 0.25rem; justify-content: flex-end;">
                    <button 
                      @click="cancelLorasEdit" 
                      class="btn btn-xs btn-ghost"
                      :disabled="savingMetadata"
                    >
                      Cancelar
                    </button>
                    <button 
                      @click="saveLorasEdit(image)" 
                      class="btn btn-xs btn-primary"
                      :disabled="savingMetadata"
                    >
                      <span v-if="savingMetadata" class="loading loading-spinner loading-xs"></span>
                      <Check v-else :size="12" />
                      Aplicar
                    </button>
                  </div>
                </div>
                
                <!-- Modo visualización (sin checkboxes, solo texto clickeable) -->
                <div v-else style="display: flex; flex-direction: column; gap: 0.25rem;">
                  <template v-if="getLinkedLoras(image).length > 0">
                    <div 
                      v-for="(lora, idx) in getLinkedLoras(image)" 
                      :key="idx"
                      style="display: flex; align-items: center; gap: 0.5rem;"
                    >
                      <span 
                        style="font-size: 0.875rem; opacity: 0.8; cursor: pointer;"
                        @click="startEditingLoras(image)"
                        :title="`${lora.nombre} - Click para editar`"
                      >
                        {{ lora.nombre }}
                      </span>
                    </div>
                  </template>
                  <div v-else style="display: flex; align-items: center; gap: 0.5rem;">
                    <span style="font-size: 0.875rem; opacity: 0.5;">-</span>
                    <button 
                      @click="startEditingLoras(image)" 
                      class="btn btn-xs btn-ghost"
                      style="padding: 0.125rem 0.25rem;"
                    >
                      <Edit :size="10" />
                    </button>
                  </div>
                </div>
              </div>
            </td>
            
            <td>
              <div style="font-size: 0.875rem; opacity: 0.8;">
                {{ formatResolution(image.width, image.height) }}
              </div>
            </td>
            <td>
              <div style="font-size: 0.875rem; opacity: 0.8;">{{ formatFileSize(image.size) }}</div>
            </td>
            <td>
              <div style="font-size: 0.875rem; opacity: 0.7;">{{ getFolderName(image.folder_id) }}</div>
            </td>
          </tr>
        </tbody>
      </table>
        </div>

        <!-- Paginación -->
    <div v-if="total > 0" style="display: flex; align-items: center; justify-content: space-between; padding: 1rem; border-top: 1px solid var(--border-base-300); gap: 1rem; flex-shrink: 0; position: relative;">
      <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1;">
        <span style="font-size: 0.875rem; opacity: 0.7;">
          <template v-if="showAllImages">
            Mostrando todas las {{ filteredImages.length }} imagen{{ filteredImages.length !== 1 ? 'es' : '' }}
          </template>
          <template v-else-if="searchFilter">
            Mostrando {{ filteredImages.length }} resultado{{ filteredImages.length !== 1 ? 's' : '' }} filtrado{{ filteredImages.length !== 1 ? 's' : '' }}
          </template>
          <template v-else>
            Mostrando {{ (currentPage - 1) * pageSize + 1 }} - {{ Math.min(currentPage * pageSize, total) }} de {{ total }}
          </template>
        </span>
      </div>
      <div style="display: flex; align-items: center; gap: 0.5rem;">
        <button 
          v-if="!showAllImages"
          class="btn btn-sm btn-primary" 
          :disabled="loading"
          @click="toggleShowAll"
        >
          Mostrar todas
        </button>
        <button 
          v-else
          class="btn btn-sm btn-ghost" 
          :disabled="loading"
          @click="toggleShowAll"
        >
          Volver a paginación
        </button>
        <template v-if="!showAllImages">
          <button 
            class="btn btn-sm btn-ghost" 
            :disabled="currentPage === 1 || loading"
            @click="goToPage(currentPage - 1)"
          >
            <ChevronLeft :size="16" />
            Anterior
          </button>
        <div style="display: flex; gap: 0.25rem;">
          <button
            v-for="page in visiblePages"
            :key="page"
            class="btn btn-sm"
            :class="page === currentPage ? 'btn-active' : 'btn-ghost'"
            :disabled="loading"
            @click="goToPage(page)"
          >
            {{ page }}
          </button>
        </div>
          <button 
            class="btn btn-sm btn-ghost" 
            :disabled="currentPage >= totalPages || loading"
            @click="goToPage(currentPage + 1)"
          >
            Siguiente
            <ChevronRight :size="16" />
          </button>
        </template>
      </div>
      <!-- Overlay de carga sutil -->
      <div 
        v-if="loading" 
        style="position: absolute; inset: 0; background-color: rgba(15, 17, 24, 0.55); display: flex; align-items: center; justify-content: center; pointer-events: none;"
      >
        <span class="loading loading-spinner loading-sm"></span>
      </div>
        </div>
      </div>
    </div>


    <!-- Image Viewer -->
    <ImageViewer ref="imageViewerRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { Table, AlertCircle, ChevronLeft, ChevronRight, Check, X, Edit, Search } from 'lucide-vue-next'
import * as galleryApi from '../api'
import type { Image, Folder } from '../api'
import { getThumbnailUrl, updateImageMetadata, listSortedFolders, moveImagesToSortedFolder } from '../api'
import type { UpdateMetadataRequest } from '../api'
import ImageViewer from '../components/ImageViewer.vue'
import type { ImageViewerData } from '../components/ImageViewer.vue'

const images = ref<Image[]>([])
const folders = ref<Folder[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const selectedImageIds = ref<Set<number>>(new Set())
const lastSelectedIndex = ref<number | null>(null) // Para selección por rango
const imageLoadErrors = ref<Record<number, boolean>>({})
const imageViewerRef = ref<InstanceType<typeof ImageViewer> | null>(null)
const tableContainerRef = ref<HTMLElement | null>(null)
const searchFilter = ref<string>('')
const sidebarOpen = ref(true) // Panel lateral abierto por defecto

// Mover imágenes a carpetas
const sortedFolders = ref<string[]>([])
const selectedFolderName = ref<string>('')
const newFolderName = ref<string>('')
const movingImages = ref(false)
const loadingFolders = ref(false)

// Edición masiva desde selección de imágenes
const bulkSelectedModel = ref<string>('')
const bulkSavingModel = ref(false)
const bulkProgressModel = ref({ current: 0, total: 0 })
const bulkSelectedLora = ref<string>('')
const bulkSavingLora = ref(false)
const bulkProgressLora = ref({ current: 0, total: 0 })

// Edición de metadatos
const editingModelId = ref<number | null>(null)
const editingModelValue = ref<string>('')
const editingLorasId = ref<number | null>(null)
const editingLorasValue = ref<Array<{ name: string; strength?: number; strength_model?: number }>>([])
const savingMetadata = ref(false)

// Paginación
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)
const showAllImages = ref(false)

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

const allSelected = computed(() => {
  return filteredImages.value.length > 0 && filteredImages.value.every(img => selectedImageIds.value.has(img.id))
})

const someSelected = computed(() => {
  const selectedCount = filteredImages.value.filter(img => selectedImageIds.value.has(img.id)).length
  return selectedCount > 0 && selectedCount < filteredImages.value.length
})

const visiblePages = computed(() => {
  const pages: number[] = []
  const maxVisible = 5
  let start = Math.max(1, currentPage.value - Math.floor(maxVisible / 2))
  let end = Math.min(totalPages.value, start + maxVisible - 1)
  
  if (end - start < maxVisible - 1) {
    start = Math.max(1, end - maxVisible + 1)
  }
  
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  
  return pages
})

// Las imágenes ya vienen filtradas del backend cuando hay búsqueda
const filteredImages = computed(() => images.value)

// Validar si se puede mover imágenes
const canMoveImages = computed(() => {
  if (selectedFolderName.value === '') return false
  if (selectedFolderName.value === '__NEW__') {
    return newFolderName.value.trim().length > 0
  }
  return true
})

// Funciones auxiliares
function getImageName(image: Image): string {
  const parts = image.path.split(/[/\\]/)
  return parts[parts.length - 1]
}

function getModelName(image: Image): string {
  if (!image.prompt_json) return ''
  
  const promptJson = image.prompt_json
  
  // Buscar el modelo en los nodos de ComfyUI
  for (const nodeId in promptJson) {
    const node = promptJson[nodeId]
    if (!node || typeof node !== 'object') continue
    
    const classType = node.class_type
    const inputs = node.inputs || {}
    
    // Checkpoint/Modelo
    if (classType === 'CheckpointLoaderSimple' || classType === 'CheckpointLoader') {
      return inputs.ckpt_name || ''
    }
  }
  
  return ''
}

function startEditingModel(image: Image) {
  // Cancelar edición de LoRAs si está activa
  if (editingLorasId.value !== null) {
    cancelLorasEdit()
  }
  editingModelId.value = image.id
  editingModelValue.value = getLinkedModelName(image)  // Ahora usa linked_model
}

function cancelModelEdit() {
  editingModelId.value = null
  editingModelValue.value = ''
}

async function saveModelEdit(image: Image) {
  if (savingMetadata.value) return
  
  let newModelName = editingModelValue.value.trim()
  
  // Manejar "__UNKNOWN__" - convertir a string vacío
  if (newModelName === '__UNKNOWN__' || newModelName === '') {
    newModelName = ''
  }
  
  const currentModelName = getLinkedModelName(image)  // Ahora usa linked_model
  
  // Si no cambió, solo cancelar
  if (newModelName === currentModelName) {
    cancelModelEdit()
    return
  }
  
  savingMetadata.value = true
  
  try {
    const request: UpdateMetadataRequest = {
      model_name: newModelName || undefined
    }
    
    const updatedImage = await updateImageMetadata(image.id, request)
    
    // Actualizar la imagen en la lista (forzar reactividad)
    const index = images.value.findIndex(img => img.id === image.id)
    if (index !== -1) {
      // Usar Object.assign para mantener la reactividad
      Object.assign(images.value[index], updatedImage)
    }
    
    // Esperar a que Vue actualice el DOM
    await nextTick()
    cancelModelEdit()
  } catch (err: any) {
    console.error('Error actualizando modelo:', err)
    alert(`Error al actualizar modelo: ${err.message || 'Error desconocido'}`)
  } finally {
    savingMetadata.value = false
  }
}

function getLoras(image: Image): Array<{ name: string; strength?: number; strength_model?: number }> {
  if (!image.prompt_json) return []
  
  const promptJson = image.prompt_json
  const loras: Array<{ name: string; strength?: number; strength_model?: number }> = []
  
  // Buscar LoRAs en los nodos de ComfyUI
  for (const nodeId in promptJson) {
    const node = promptJson[nodeId]
    if (!node || typeof node !== 'object') continue
    
    const classType = node.class_type
    const inputs = node.inputs || {}
    
    // LoRA Loader
    if (classType === 'LoraLoader' || classType === 'LoraLoaderModelOnly') {
      const loraName = inputs.lora_name
      if (loraName) {
        loras.push({
          name: loraName,
          strength: inputs.strength,
          strength_model: inputs.strength_model
        })
      }
    }
  }
  
  return loras
}

// Funciones para obtener datos de tablas satélite (vinculados)
function getLinkedModelName(image: Image): string {
  return image.linked_model?.nombre || ''
}

function getLinkedLoras(image: Image): Array<{ nombre: string; resource_id: number; strength?: number | null; strength_model?: number | null }> {
  return image.linked_loras || []
}

const modelNameSuggestions = computed(() => {
  const s = new Set<string>()
  for (const img of images.value) {
    const n = getLinkedModelName(img) || getModelName(img)
    if (n && n.trim()) s.add(n.trim())
  }
  return Array.from(s).sort()
})

const loraNameSuggestions = computed(() => {
  const s = new Set<string>()
  for (const img of images.value) {
    for (const l of getLinkedLoras(img)) {
      if (l.nombre?.trim()) s.add(l.nombre.trim())
    }
    for (const l of getLoras(img)) {
      if (l.name?.trim()) s.add(l.name.trim())
    }
  }
  return Array.from(s).sort()
})

function startEditingLoras(image: Image) {
  // Cancelar edición de modelo si está activa
  if (editingModelId.value !== null) {
    cancelModelEdit()
  }
  editingLorasId.value = image.id
  const currentLoras = getLinkedLoras(image)  // Ahora usa linked_loras
  editingLorasValue.value = currentLoras.length > 0 
    ? currentLoras.map(l => ({ 
        name: l.nombre || '',  // Mapear .nombre a .name para el formulario
        strength: l.strength || undefined,
        strength_model: l.strength_model || undefined
      }))
    : [{ name: '' }]
}

function cancelLorasEdit() {
  editingLorasId.value = null
  editingLorasValue.value = []
}

function addLora() {
  editingLorasValue.value.push({ name: '' })
}

function removeLora(index: number) {
  editingLorasValue.value.splice(index, 1)
}

async function saveLorasEdit(image: Image) {
  if (savingMetadata.value) return
  
  // Filtrar LoRAs vacíos y procesar "__UNKNOWN__"
  const validLoras = editingLorasValue.value
    .filter(l => l.name && l.name.trim() !== '' && l.name !== '-- Seleccionar --')
    .map(l => {
      // Si es "__UNKNOWN__", convertir a string vacío (el backend lo manejará)
      const name = l.name.trim() === '__UNKNOWN__' ? '' : l.name.trim()
      return {
        name: name,
        strength: l.strength,
        strength_model: l.strength_model
      }
    })
    .filter(l => l.name !== '')  // Filtrar los que quedaron vacíos después del procesamiento
  
  const currentLoras = getLinkedLoras(image)  // Ahora usa linked_loras
  
  // Comparar si cambió (normalizar nombres para comparación)
  const currentNames = currentLoras.map(l => l.nombre || '').sort().join(',')
  const newNames = validLoras.map(l => l.name).sort().join(',')
  
  if (currentNames === newNames) {
    cancelLorasEdit()
    return
  }
  
  savingMetadata.value = true
  
  try {
    const request: UpdateMetadataRequest = {
      loras: validLoras
    }
    
    const updatedImage = await updateImageMetadata(image.id, request)
    
    // Actualizar la imagen en la lista (forzar reactividad)
    const index = images.value.findIndex(img => img.id === image.id)
    if (index !== -1) {
      // Usar Object.assign para mantener la reactividad
      Object.assign(images.value[index], updatedImage)
    }
    
    // Esperar a que Vue actualice el DOM
    await nextTick()
    cancelLorasEdit()
  } catch (err: any) {
    console.error('Error actualizando LoRAs:', err)
    alert(`Error al actualizar LoRAs: ${err.message || 'Error desconocido'}`)
  } finally {
    savingMetadata.value = false
  }
}

function formatResolution(width: number | null, height: number | null): string {
  if (!width || !height) return '-'
  return `${width} × ${height}`
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '-'
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  const mb = kb / 1024
  return `${mb.toFixed(2)} MB`
}

function getFolderName(folderId: string): string {
  const folder = folders.value.find(f => f.id === folderId)
  return folder ? folder.name : folderId
}

function toggleImageSelection(imageId: number) {
  // Crear un nuevo Set para forzar la reactividad
  const newSet = new Set(selectedImageIds.value)
  if (newSet.has(imageId)) {
    newSet.delete(imageId)
  } else {
    newSet.add(imageId)
  }
  selectedImageIds.value = newSet
}

function handleRowClick(imageId: number, index: number, event: MouseEvent) {
  // Si se presiona Shift, seleccionar rango
  if (event.shiftKey && lastSelectedIndex.value !== null) {
    const start = Math.min(lastSelectedIndex.value, index)
    const end = Math.max(lastSelectedIndex.value, index)
    
    // Crear un nuevo Set para forzar la reactividad
    const newSet = new Set(selectedImageIds.value)
    // Seleccionar todas las imágenes en el rango
    for (let i = start; i <= end; i++) {
      newSet.add(filteredImages.value[i].id)
    }
    selectedImageIds.value = newSet
  } else {
    // Selección normal
    toggleImageSelection(imageId)
    lastSelectedIndex.value = index
  }
}

function handleCheckboxChange(imageId: number, index: number, event: Event) {
  const target = event.target as HTMLInputElement
  // Crear un nuevo Set para forzar la reactividad
  const newSet = new Set(selectedImageIds.value)
  if (target.checked) {
    newSet.add(imageId)
  } else {
    newSet.delete(imageId)
  }
  selectedImageIds.value = newSet
  lastSelectedIndex.value = index
}

function toggleSelectAll() {
  // Crear un nuevo Set para forzar la reactividad
  const newSet = new Set(selectedImageIds.value)
  
  if (allSelected.value) {
    // Deseleccionar solo las imágenes filtradas
    filteredImages.value.forEach(img => newSet.delete(img.id))
    lastSelectedIndex.value = null
  } else {
    // Seleccionar solo las imágenes filtradas
    filteredImages.value.forEach(img => newSet.add(img.id))
    // Establecer el último índice seleccionado al último elemento
    if (filteredImages.value.length > 0) {
      lastSelectedIndex.value = filteredImages.value.length - 1
    }
  }
  
  selectedImageIds.value = newSet
}

function toggleShowAll() {
  // Alternar entre mostrar todas las imágenes o usar paginación
  showAllImages.value = !showAllImages.value
  // Recargar imágenes con el nuevo modo
  loadImages()
}

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value || loading.value) return
  currentPage.value = page
  loadImages()
}

function openImageViewer(imageId: number) {
  if (!imageViewerRef.value) return
  
  const image = filteredImages.value.find(img => img.id === imageId)
  if (!image) return
  
  const viewerData: ImageViewerData[] = filteredImages.value.map(img => ({
    id: img.id,
    path: img.path
  }))
  
  const startIndex = filteredImages.value.findIndex(img => img.id === imageId)
  
  imageViewerRef.value.open(viewerData, startIndex)
}

async function loadImages() {
  loading.value = true
  error.value = null
  
  try {
    let result
    
    if (showAllImages.value) {
      // Modo "Mostrar todas": cargar todas las imágenes sin paginación
      // Primero obtener el total para saber cuántas cargar
      const totalResult = await galleryApi.listImages({
        limit: 1,
        offset: 0,
        search: searchFilter.value.trim() || undefined
      })
      
      // Ahora cargar todas las imágenes
      result = await galleryApi.listImages({
        limit: totalResult.total > 0 ? totalResult.total : 10000, // Usar el total o un límite grande
        offset: 0,
        search: searchFilter.value.trim() || undefined
      })
    } else {
      // Modo paginación normal
      const offset = (currentPage.value - 1) * pageSize.value
      result = await galleryApi.listImages({
        limit: pageSize.value,
        offset: offset,
        search: searchFilter.value.trim() || undefined
      })
    }
    
    images.value = result.images
    total.value = result.total
    
    // Limpiar selección solo si cambió de página (no si solo se activó "mostrar todas")
    if (!showAllImages.value) {
      selectedImageIds.value.clear()
    }
    
    // Scroll suave hacia arriba de la tabla después de cargar
    await nextTick()
    if (tableContainerRef.value) {
      tableContainerRef.value.scrollTop = 0
    }
  } catch (err: any) {
    error.value = err.message || 'Error al cargar imágenes'
    console.error('Error loading images:', err)
  } finally {
    loading.value = false
  }
}

// Watch para recargar cuando cambia el filtro de búsqueda
watch(searchFilter, () => {
  // Resetear a página 1 cuando cambia la búsqueda
  currentPage.value = 1
  loadImages()
})

// Funciones de edición masiva desde selección de imágenes
async function applyBulkModelToSelected() {
  if (!bulkSelectedModel.value || bulkSavingModel.value) return
  if (selectedImageIds.value.size === 0) return
  
  bulkSavingModel.value = true
  
  // Obtener todas las imágenes seleccionadas
  const imagesToUpdate = images.value.filter(img => selectedImageIds.value.has(img.id))
  
  bulkProgressModel.value = { current: 0, total: imagesToUpdate.length }
  
  // Procesar el nombre del modelo (manejar __UNKNOWN__)
  let modelName = bulkSelectedModel.value.trim()
  if (modelName === '__UNKNOWN__' || modelName === '') {
    modelName = ''
  }
  
  try {
    let successCount = 0
    let errorCount = 0
    
    for (const image of imagesToUpdate) {
      try {
        const request: UpdateMetadataRequest = {
          model_name: modelName || undefined
        }
        
        const updatedImage = await updateImageMetadata(image.id, request)
        
        // Actualizar la imagen en la lista
        const index = images.value.findIndex(img => img.id === image.id)
        if (index !== -1) {
          Object.assign(images.value[index], updatedImage)
        }
        
        successCount++
        bulkProgressModel.value.current++
      } catch (err: any) {
        console.error(`Error actualizando imagen ${image.id}:`, err)
        errorCount++
        bulkProgressModel.value.current++
      }
    }
    
    // Mostrar resultado
    if (errorCount === 0) {
      alert(`✅ Modelo actualizado en ${successCount} imagen${successCount !== 1 ? 'es' : ''}`)
    } else {
      alert(`⚠️ Modelo actualizado en ${successCount} imagen${successCount !== 1 ? 'es' : ''}, ${errorCount} error${errorCount !== 1 ? 'es' : ''}`)
    }
    
    // Limpiar selección y resetear
    bulkSelectedModel.value = ''
  } catch (err: any) {
    console.error('Error en edición masiva de modelos:', err)
    alert(`Error al actualizar modelos: ${err.message || 'Error desconocido'}`)
  } finally {
    bulkSavingModel.value = false
    bulkProgressModel.value = { current: 0, total: 0 }
  }
}

async function applyBulkLoraToSelected() {
  if (!bulkSelectedLora.value || bulkSavingLora.value) return
  if (selectedImageIds.value.size === 0) return
  
  bulkSavingLora.value = true
  
  // Obtener todas las imágenes seleccionadas
  const imagesToUpdate = images.value.filter(img => selectedImageIds.value.has(img.id))
  
  bulkProgressLora.value = { current: 0, total: imagesToUpdate.length }
  
  // Procesar el nombre del LoRA (manejar __UNKNOWN__)
  let loraName = bulkSelectedLora.value.trim()
  if (loraName === '__UNKNOWN__' || loraName === '') {
    // No permitir agregar Unknown LoRA masivamente
    alert('No se puede agregar "Unknown LoRA" masivamente. Selecciona un LoRA válido.')
    bulkSavingLora.value = false
    return
  }
  
  try {
    let successCount = 0
    let skippedCount = 0  // LoRAs que ya existían
    let errorCount = 0
    
    for (const image of imagesToUpdate) {
      try {
        // Obtener LoRAs existentes de la imagen
        const existingLoras = getLinkedLoras(image)
        
        // Verificar si el LoRA ya existe en esta imagen
        const loraExists = existingLoras.some(lora => lora.nombre === loraName)
        
        if (loraExists) {
          // El LoRA ya existe, saltar esta imagen
          skippedCount++
          bulkProgressLora.value.current++
          continue
        }
        
        // Verificar si solo tiene "Unknown LoRA" (el LoRA por defecto)
        const hasOnlyUnknown = existingLoras.length === 1 && existingLoras[0].nombre === 'Unknown LoRA'
        
        // Construir la lista de LoRAs
        let lorasToSend: Array<{ name: string; strength?: number; strength_model?: number }> = []
        
        if (hasOnlyUnknown) {
          // Si solo tiene Unknown LoRA, reemplazarlo con el nuevo LoRA
          lorasToSend = [{
            name: loraName,
            strength: undefined,
            strength_model: undefined
          }]
        } else {
          // Si tiene otros LoRAs o no tiene ninguno, agregar el nuevo a los existentes
          lorasToSend = existingLoras
            .filter(lora => lora.nombre !== 'Unknown LoRA')  // Excluir Unknown LoRA si hay otros LoRAs
            .map(lora => ({
              name: lora.nombre,
              strength: lora.strength,
              strength_model: lora.strength_model
            }))
          
          // Agregar el nuevo LoRA
          lorasToSend.push({
            name: loraName,
            strength: undefined,  // Sin strength por defecto
            strength_model: undefined
          })
        }
        
        const request: UpdateMetadataRequest = {
          loras: lorasToSend
        }
        
        const updatedImage = await updateImageMetadata(image.id, request)
        
        // Actualizar la imagen en la lista
        const index = images.value.findIndex(img => img.id === image.id)
        if (index !== -1) {
          Object.assign(images.value[index], updatedImage)
        }
        
        successCount++
        bulkProgressLora.value.current++
      } catch (err: any) {
        console.error(`Error agregando LoRA a imagen ${image.id}:`, err)
        errorCount++
        bulkProgressLora.value.current++
      }
    }
    
    // Mostrar resultado
    let message = `✅ LoRA "${loraName}" agregado a ${successCount} imagen${successCount !== 1 ? 'es' : ''}`
    if (skippedCount > 0) {
      message += `\n⏭️ ${skippedCount} imagen${skippedCount !== 1 ? 'es' : ''} ya tenían este LoRA (saltadas)`
    }
    if (errorCount > 0) {
      message += `\n❌ ${errorCount} error${errorCount !== 1 ? 'es' : ''}`
    }
    alert(message)
    
    // Limpiar selección y resetear
    bulkSelectedLora.value = ''
  } catch (err: any) {
    console.error('Error en edición masiva de LoRAs:', err)
    alert(`Error al agregar LoRAs: ${err.message || 'Error desconocido'}`)
  } finally {
    bulkSavingLora.value = false
    bulkProgressLora.value = { current: 0, total: 0 }
  }
}


async function loadFolders() {
  try {
    folders.value = await galleryApi.listFolders()
  } catch (err) {
    console.error('Error loading folders:', err)
  }
}

async function loadSortedFolders() {
  if (selectedImageIds.value.size === 0) {
    sortedFolders.value = []
    return
  }
  
  loadingFolders.value = true
  try {
    sortedFolders.value = await listSortedFolders()
  } catch (err: any) {
    console.error('Error loading sorted folders:', err)
    alert(`Error al cargar carpetas: ${err.message || 'Error desconocido'}`)
  } finally {
    loadingFolders.value = false
  }
}

async function moveImagesToFolder() {
  if (!canMoveImages.value || movingImages.value) return
  
  const folderName = selectedFolderName.value === '__NEW__' 
    ? newFolderName.value.trim() 
    : selectedFolderName.value
  
  if (!folderName) return
  
  // Validar que no haya carpetas duplicadas
  if (selectedFolderName.value === '__NEW__' && sortedFolders.value.includes(folderName)) {
    alert(`La carpeta "${folderName}" ya existe. Por favor selecciónala de la lista.`)
    return
  }
  
  movingImages.value = true
  
  try {
    const imageIds = Array.from(selectedImageIds.value)
    const result = await moveImagesToSortedFolder({
      image_ids: imageIds,
      folder_name: folderName
    })
    
    if (result.errors && result.errors.length > 0) {
      console.warn('Algunos errores al mover imágenes:', result.errors)
    }
    
    // Recargar carpetas y actualizar lista
    await loadFolders()
    await loadSortedFolders()
    await loadImages()
    
    // Emitir evento para refrescar carpetas en el Sidebar
    // Usar nextTick para asegurar que el DOM se actualice primero
    await nextTick()
    // Disparar evento personalizado que App.vue puede escuchar
    window.dispatchEvent(new CustomEvent('refreshFolders'))
    
    // Limpiar selección
    selectedImageIds.value = new Set()
    selectedFolderName.value = ''
    newFolderName.value = ''
    
    // Mostrar mensaje completo del backend (incluye moved_count, skipped_count, etc.)
    alert(`✅ ${result.message}`)
  } catch (err: any) {
    console.error('Error moviendo imágenes:', err)
    alert(`Error al mover imágenes: ${err.response?.data?.detail || err.message || 'Error desconocido'}`)
  } finally {
    movingImages.value = false
  }
}

// Computed para detectar cambios en el tamaño del Set
const selectedImagesCount = computed(() => selectedImageIds.value.size)

// Watch para cargar carpetas cuando se seleccionan imágenes
watch(selectedImagesCount, (newSize) => {
  if (newSize > 0) {
    loadSortedFolders()
  } else {
    sortedFolders.value = []
    selectedFolderName.value = ''
    newFolderName.value = ''
  }
})

onMounted(async () => {
  await Promise.all([
    loadFolders(),
    loadImages(),
  ])
})
</script>

<style scoped>
.bulk-management-page {
  background-color: var(--bg-base-100);
  color: var(--text-base-content);
}

.table {
  background-color: var(--bg-base-100);
  color: var(--text-base-content);
}

.table thead th {
  background-color: var(--bg-base-300);
  color: var(--text-base-content);
  border-bottom: 1px solid var(--border-base-300);
  font-weight: 600;
  font-size: 0.875rem;
  padding: 0.75rem;
}

.table tbody td {
  border-bottom: 1px solid var(--border-base-300);
  padding: 0.75rem;
}

.table tbody tr:hover {
  background-color: rgba(139, 92, 246, 0.1);
}

.table tbody tr.row-selected {
  background-color: rgba(139, 92, 246, 0.14);
  outline: 1px solid rgba(139, 92, 246, 0.42);
  outline-offset: -1px;
}

.table-zebra tbody tr:nth-child(even) {
  background-color: rgba(23, 27, 39, 0.55);
}

.table-zebra tbody tr:nth-child(even):hover {
  background-color: rgba(139, 92, 246, 0.1);
}

/* Estilos para el panel lateral */
.sidebar-panel {
  scrollbar-width: thin;
  scrollbar-color: var(--border-base-300) transparent;
}

.sidebar-panel::-webkit-scrollbar {
  width: 8px;
}

.sidebar-panel::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-panel::-webkit-scrollbar-thumb {
  background-color: var(--border-base-300);
  border-radius: 4px;
}

.sidebar-panel::-webkit-scrollbar-thumb:hover {
  background-color: #4a5470;
}
</style>


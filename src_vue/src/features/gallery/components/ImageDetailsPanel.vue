<template>
  <!-- Overlay -->
  <div 
    v-show="isOpen" 
    class="fixed inset-0 transition-all duration-300 panel-overlay"
    :class="showContent ? 'opacity-100' : 'opacity-0'"
    @click="close"
  ></div>
  
  <!-- Panel -->
  <aside 
    v-show="isOpen"
    class="shadow-2xl overflow-y-auto"
    :style="{
      position: 'fixed',
      top: '0',
      right: '0',
      height: '100vh',
      width: '640px',
      maxWidth: '90vw',
      zIndex: '10001',
      backgroundColor: 'var(--bg-base-100)',
      borderLeft: '1px solid var(--border-base-300)',
      transform: showContent ? 'translateX(0)' : 'translateX(100%)',
      transition: 'transform 0.3s ease'
    }"
  >
    <!-- Header -->
    <div style="padding: 1rem; border-bottom: 1px solid var(--border-base-300); display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; background-color: var(--bg-base-100); z-index: 10;">
      <h2 style="font-size: 1.125rem; font-weight: 600;">Detalles de la imagen</h2>
      <button @click="close" class="btn btn-ghost btn-sm btn-circle">
        <X :size="20" />
      </button>
    </div>
    
    <!-- Content -->
    <div style="padding: 1rem 1rem 2rem 1rem;">
      <!-- Loading -->
      <div v-if="loading" style="display: flex; align-items: center; justify-content: center; height: 16rem;">
        <span class="loading loading-spinner loading-lg"></span>
      </div>
      
      <!-- Error -->
      <div v-else-if="error" class="alert alert-error" style="margin-bottom: 1rem;">
        <AlertCircle :size="20" />
        <span>{{ error }}</span>
      </div>
      
      <!-- Content -->
      <div v-else-if="image" style="display: flex; flex-direction: column; gap: 1rem;">
        <!-- Preview -->
        <div 
          class="w-full rounded-lg overflow-hidden border border-base-300 bg-base-300 cursor-pointer hover:border-primary transition-colors relative group" 
          style="min-height: 200px; max-height: 400px; display: flex; align-items: center; justify-content: center;"
          @click="openImageViewer"
          title="Click para ver en pantalla completa"
        >
          <img 
            v-if="imageUrl && !imageLoadError" 
            :src="imageUrl" 
            :alt="imageName" 
            style="max-height: 400px; width: 100%; object-fit: contain;"
            @error="imageLoadError = true"
          />
          <div v-else class="flex flex-col items-center justify-center p-8 text-center">
            <ImageOff :size="48" class="mb-2 opacity-30" />
            <p class="text-xs opacity-50">No se pudo cargar la imagen</p>
          </div>
          <!-- Overlay para indicar que es clickeable -->
          <div class="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-10 transition-all flex items-center justify-center">
            <div class="opacity-0 group-hover:opacity-100 transition-opacity bg-black bg-opacity-50 rounded-full p-3">
              <Maximize2 :size="24" class="text-white" />
            </div>
          </div>
        </div>
        
        <!-- Info Básica -->
        <div style="background-color: var(--bg-base-200); border: 1px solid var(--border-base-300); border-radius: 0.5rem; padding: 0.75rem;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
            <h3 style="font-size: 0.875rem; font-weight: 600;">Información Básica</h3>
            <span class="badge" :class="sourceBadgeClass">{{ sourceLabel }}</span>
          </div>
          <div style="font-size: 0.75rem; display: flex; flex-direction: column; gap: 0.25rem;">
            <p><strong>Nombre:</strong> {{ imageName }}</p>
            <p><strong>Resolución:</strong> {{ image.width || '?' }} × {{ image.height || '?' }} px</p>
            <p><strong>Tamaño:</strong> {{ formatBytes(image.size) }}</p>
            <p><strong>Ruta:</strong> <span style="opacity: 0.7; font-size: 0.625rem; word-break: break-all;">{{ image.path }}</span></p>
          </div>
        </div>
        
        <!-- Metadatos AI -->
        <div v-if="hasMetadata" style="background-color: var(--bg-base-200); border: 1px solid var(--border-base-300); border-radius: 0.5rem; padding: 0.75rem;">
          <h3 style="font-size: 0.875rem; font-weight: 600; margin-bottom: 0.5rem;">Metadatos AI</h3>
          <div style="font-size: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem;">
              <!-- Modelo -->
              <div v-if="extractedData.model" class="flex gap-2 items-center">
                <span class="font-semibold opacity-70 min-w-[80px]">Modelo:</span>
                <span class="link link-primary text-xs">{{ extractedData.model }}</span>
              </div>
              
              <!-- Sampler -->
              <div v-if="extractedData.sampler" class="flex gap-2">
                <span class="font-semibold opacity-70 min-w-[80px]">Sampler:</span>
                <span>{{ extractedData.sampler }}</span>
              </div>
              
              <!-- Steps -->
              <div v-if="extractedData.steps" class="flex gap-2">
                <span class="font-semibold opacity-70 min-w-[80px]">Steps:</span>
                <span>{{ extractedData.steps }}</span>
              </div>
              
              <!-- CFG -->
              <div v-if="extractedData.cfg" class="flex gap-2">
                <span class="font-semibold opacity-70 min-w-[80px]">CFG:</span>
                <span>{{ extractedData.cfg }}</span>
              </div>
              
              <!-- Seed -->
              <div v-if="extractedData.seed" class="flex gap-2 items-center">
                <span class="font-semibold opacity-70 min-w-[80px]">Seed:</span>
                <span class="flex-1 font-mono">{{ extractedData.seed }}</span>
                <button @click="copyToClipboard(String(extractedData.seed))" class="btn btn-xs btn-ghost" title="Copiar seed">
                  <Copy :size="12" />
                </button>
              </div>
              
              <!-- Denoise -->
              <div v-if="extractedData.denoise" class="flex gap-2">
                <span class="font-semibold opacity-70 min-w-[80px]">Denoise:</span>
                <span>{{ extractedData.denoise }}</span>
              </div>
              
              <!-- Positive Prompt -->
              <div v-if="extractedData.positivePrompt" style="background-color: var(--bg-base-300); border: 1px solid var(--border-base-300); padding: 0.5rem; border-radius: 0.375rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem;">
                  <p style="font-weight: 600; opacity: 0.7; font-size: 0.75rem;">Prompt Positivo</p>
                  <button @click="copyToClipboard(extractedData.positivePrompt)" class="btn btn-xs btn-ghost" title="Copiar prompt">
                    <Copy :size="12" />
                  </button>
                </div>
                <p style="white-space: pre-wrap; word-break: break-word; font-size: 0.75rem; max-height: 200px; overflow-y: auto;">{{ extractedData.positivePrompt }}</p>
              </div>
              
              <!-- Negative Prompt -->
              <div v-if="extractedData.negativePrompt" style="background-color: var(--bg-base-300); border: 1px solid var(--border-base-300); padding: 0.5rem; border-radius: 0.375rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem;">
                  <p style="font-weight: 600; opacity: 0.7; font-size: 0.75rem;">Prompt Negativo</p>
                  <button @click="copyToClipboard(extractedData.negativePrompt)" class="btn btn-xs btn-ghost" title="Copiar prompt negativo">
                    <Copy :size="12" />
                  </button>
                </div>
                <p style="white-space: pre-wrap; word-break: break-word; font-size: 0.75rem; max-height: 200px; overflow-y: auto;">{{ extractedData.negativePrompt }}</p>
              </div>
          </div>
        </div>
        
        <!-- LORAs -->
        <div v-if="extractedData.loras && extractedData.loras.length > 0" style="background-color: var(--bg-base-200); border: 1px solid var(--border-base-300); border-radius: 0.5rem; padding: 0.75rem;">
          <h3 style="font-size: 0.875rem; font-weight: 600; margin-bottom: 0.5rem;">LORAs</h3>
          <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
            <span 
              v-for="(lora, index) in extractedData.loras" 
              :key="index" 
              class="badge badge-primary badge-lg gap-2 hover:brightness-110 transition cursor-default"
              :title="`LoRA: ${lora.name}${lora.strength != null ? ` (strength: ${lora.strength})` : ''}`"
            >
              {{ lora.name }}
              <span v-if="lora.strength != null" class="opacity-70">({{ lora.strength }})</span>
            </span>
          </div>
        </div>
        
        <!-- JSON Sections -->
        <div v-if="image.prompt_json" style="background-color: var(--bg-base-200); border: 1px solid var(--border-base-300); border-radius: 0.5rem; padding: 0.75rem;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
            <h3 style="font-size: 0.875rem; font-weight: 600;">Prompt embebido (JSON)</h3>
            <div style="display: flex; gap: 0.25rem; align-items: center;">
              <!-- Tabs -->
              <div class="btn-group btn-group-xs">
                <button 
                  @click="promptJsonView = 'raw'" 
                  class="btn btn-xs"
                  :class="promptJsonView === 'raw' ? 'btn-active' : ''"
                >Raw</button>
                <button 
                  @click="promptJsonView = 'pretty'" 
                  class="btn btn-xs"
                  :class="promptJsonView === 'pretty' ? 'btn-active' : ''"
                >Pretty</button>
              </div>
              <!-- Botón copiar -->
              <button @click="copyToClipboard(JSON.stringify(image.prompt_json, null, promptJsonView === 'pretty' ? 2 : 0))" class="btn btn-xs btn-ghost" title="Copiar JSON">
                <Copy :size="12" />
              </button>
            </div>
          </div>
          <div style="background-color: var(--bg-base-300); border: 1px solid var(--border-base-300); border-radius: 0.375rem; padding: 0.75rem; overflow: auto; max-height: 400px;">
            <pre 
              style="margin: 0; font-family: 'Courier New', monospace; line-height: 1.6; tab-size: 2;"
              :style="promptJsonView === 'pretty' ? 'font-size: 0.75rem; white-space: pre;' : 'font-size: 0.625rem; white-space: pre-wrap; word-break: break-all;'"
            >{{ formatJson(image.prompt_json, promptJsonView) }}</pre>
          </div>
        </div>
        
        <div v-if="image.workflow_json" style="background-color: var(--bg-base-200); border: 1px solid var(--border-base-300); border-radius: 0.5rem; padding: 0.75rem;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
            <h3 style="font-size: 0.875rem; font-weight: 600;">Workflow embebido (JSON)</h3>
            <div style="display: flex; gap: 0.25rem; align-items: center;">
              <!-- Tabs -->
              <div class="btn-group btn-group-xs">
                <button 
                  @click="workflowJsonView = 'raw'" 
                  class="btn btn-xs"
                  :class="workflowJsonView === 'raw' ? 'btn-active' : ''"
                >Raw</button>
                <button 
                  @click="workflowJsonView = 'pretty'" 
                  class="btn btn-xs"
                  :class="workflowJsonView === 'pretty' ? 'btn-active' : ''"
                >Pretty</button>
              </div>
              <!-- Botón copiar -->
              <button @click="copyToClipboard(JSON.stringify(image.workflow_json, null, workflowJsonView === 'pretty' ? 2 : 0))" class="btn btn-xs btn-ghost" title="Copiar JSON">
                <Copy :size="12" />
              </button>
            </div>
          </div>
          <div style="background-color: var(--bg-base-300); border: 1px solid var(--border-base-300); border-radius: 0.375rem; padding: 0.75rem; overflow: auto; max-height: 400px;">
            <pre 
              style="margin: 0; font-family: 'Courier New', monospace; line-height: 1.6; tab-size: 2;"
              :style="workflowJsonView === 'pretty' ? 'font-size: 0.75rem; white-space: pre;' : 'font-size: 0.625rem; white-space: pre-wrap; word-break: break-all;'"
            >{{ formatJson(image.workflow_json, workflowJsonView) }}</pre>
          </div>
        </div>
        
        <!-- Sin metadatos -->
        <div v-if="!hasMetadata && !image.prompt_json && !image.workflow_json" style="background-color: var(--bg-base-200); border: 1px solid var(--border-base-300); border-radius: 0.5rem; padding: 0.75rem;">
          <p style="font-size: 0.75rem; opacity: 0.5; text-align: center;">
            <FileCode :size="16" style="display: inline-block; margin-right: 0.25rem; vertical-align: middle;" />
            No hay metadatos AI disponibles para esta imagen
          </p>
        </div>
      </div>
    </div>
  </aside>

  <!-- Image Viewer -->
  <ImageViewer ref="imageViewerRef" />
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { X, AlertCircle, ImageOff, Copy, FileCode, Maximize2 } from 'lucide-vue-next'
import * as galleryApi from '../api'
import type { Image } from '../api'
import { getFullImageUrl } from '../api'
import { getSetting } from '../../settings/api'
import { usePanelStore } from '../../../stores/panelStore'
import ImageViewer from './ImageViewer.vue'
import type { ImageViewerData } from './ImageViewer.vue'

const { currentPanel, closePanel } = usePanelStore()

const isOpen = ref(false)
const showContent = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const image = ref<Image | null>(null)
const imageLoadError = ref(false)
const promptJsonView = ref<'raw' | 'pretty'>('raw')
const workflowJsonView = ref<'raw' | 'pretty'>('raw')
const imageViewerRef = ref<InstanceType<typeof ImageViewer> | null>(null)
const loadFullImageInBulk = ref(false)

// Manejador de teclado para cerrar con Escape
const handleKeydown = (e: KeyboardEvent) => {
  if (!isOpen.value) return
  
  if (e.key === 'Escape') {
    close()
  }
}

// Watch para agregar/quitar event listeners
watch(isOpen, (newValue) => {
  if (newValue) {
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('keydown', handleKeydown)
  }
})

// Watch para abrir/cerrar el panel basado en el store
watch(() => currentPanel.value, async (newPanel) => {
  if (newPanel.type === 'image-details' && newPanel.data?.imageId) {
    await open(newPanel.data.imageId)
  } else if (newPanel.type !== 'image-details' && isOpen.value) {
    close(false)
  }
}, { deep: true, immediate: true })

const imageUrl = computed(() => {
  if (!image.value?.id) return ''
  return loadFullImageInBulk.value 
    ? getFullImageUrl(image.value.id) 
    : galleryApi.getThumbnailUrl(image.value.id)
})

const imageName = computed(() => {
  if (!image.value?.path) return 'Sin nombre'
  const parts = image.value.path.split(/[\\/]/)
  return parts[parts.length - 1]
})

const hasMetadata = computed(() => {
  return image.value?.prompt_json || image.value?.workflow_json
})

const sourceLabel = computed(() => {
  if (image.value?.prompt_json) return 'Workflow embebido'
  if (image.value?.workflow_json) return 'Con Workflow'
  return 'Sin metadatos AI'
})

const sourceBadgeClass = computed(() => {
  if (image.value?.prompt_json) return 'badge-primary'
  if (image.value?.workflow_json) return 'badge-secondary'
  return 'badge-ghost'
})

// Extraer datos relevantes del prompt_json
const extractedData = computed(() => {
  const data: {
    model?: string
    sampler?: string
    steps?: number
    cfg?: number
    seed?: string | number
    denoise?: number
    positivePrompt?: string
    negativePrompt?: string
    loras?: Array<{ name: string; strength?: number }>
  } = {}
  
  if (!image.value?.prompt_json) return data
  
  const promptJson = image.value.prompt_json
  
  // ComfyUI tiene estructura de nodos, buscar valores relevantes
  for (const nodeId in promptJson) {
    const node = promptJson[nodeId]
    if (!node || typeof node !== 'object') continue
    
    const classType = node.class_type
    const inputs = node.inputs || {}
    
    // Checkpoint/Modelo
    if (classType === 'CheckpointLoaderSimple' || classType === 'CheckpointLoader') {
      data.model = inputs.ckpt_name
    }
    
    // Sampler
    if (classType === 'KSampler' || classType === 'KSamplerAdvanced') {
      data.sampler = inputs.sampler_name
      data.steps = inputs.steps
      data.cfg = inputs.cfg
      data.seed = inputs.seed
      data.denoise = inputs.denoise
    }
    
    // CLIP Text Encode (Prompts)
    if (classType === 'CLIPTextEncode') {
      const text = inputs.text
      if (text) {
        // Heurística: si contiene palabras negativas comunes, es negative
        const isNegative = /\b(bad|ugly|worst|low quality|blurry|deformed)\b/i.test(text)
        if (isNegative && !data.negativePrompt) {
          data.negativePrompt = text
        } else if (!data.positivePrompt) {
          data.positivePrompt = text
        }
      }
    }
    
    // LoRA Loader
    if (classType === 'LoraLoader' || classType === 'LoraLoaderModelOnly') {
      if (!data.loras) data.loras = []
      data.loras.push({
        name: inputs.lora_name || 'Unknown',
        strength: inputs.strength_model || inputs.strength
      })
    }
  }
  
  return data
})

async function open(imageId: number) {
  isOpen.value = true
  loading.value = true
  error.value = null
  image.value = null
  imageLoadError.value = false
  promptJsonView.value = 'raw'
  workflowJsonView.value = 'raw'
  
  // Delay para animación
  await nextTick()
  showContent.value = true
  
  // Prevenir scroll del body
  document.body.style.overflow = 'hidden'
  
  try {
    image.value = await galleryApi.getImage(imageId)
  } catch (err: any) {
    console.error('Error cargando imagen:', err)
    error.value = err.message || 'Error al cargar la imagen'
  } finally {
    loading.value = false
  }
}

function close(syncStore = true) {
  showContent.value = false

  setTimeout(() => {
    isOpen.value = false
    image.value = null
    if (syncStore) {
      document.body.style.overflow = ''
      closePanel()
    }
  }, 300)
}

function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

function formatJson(obj: any, view: 'raw' | 'pretty'): string {
  if (view === 'pretty') {
    return JSON.stringify(obj, null, 2)
  }
  return JSON.stringify(obj)
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch (err) {
    console.error('Error al copiar:', err)
  }
}

function openImageViewer() {
  if (!image.value) return
  
  const imageData: ImageViewerData = {
    id: image.value.id,
    path: image.value.path
  }
  
  imageViewerRef.value?.open([imageData], 0)
}

async function loadFullImageSetting() {
  try {
    const setting = await getSetting('load_full_image_in_bulk')
    loadFullImageInBulk.value = setting.value !== null && setting.value !== undefined && setting.value.toLowerCase() === 'true'
  } catch (err: any) {
    // Si no existe el setting, usar false por defecto
    if (err.response?.status === 404) {
      loadFullImageInBulk.value = false
    } else {
      console.error('Error al cargar preferencia load_full_image_in_bulk:', err)
      loadFullImageInBulk.value = false
    }
  }
}

onMounted(() => {
  loadFullImageSetting()
})

// Exponer para uso externo
defineExpose({ open, close })
</script>

<style scoped>
/* Overlay con blur */
.panel-overlay {
  z-index: 10000;
  background-color: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

/* Panel de detalles de imagen */
aside {
  background-color: var(--bg-base-100, #1d232a) !important;
  scrollbar-width: thin;
  scrollbar-color: var(--border-base-300) transparent;
}

aside::-webkit-scrollbar {
  width: 8px;
}

aside::-webkit-scrollbar-track {
  background: transparent;
}

aside::-webkit-scrollbar-thumb {
  background-color: var(--border-base-300);
  border-radius: 4px;
}

aside::-webkit-scrollbar-thumb:hover {
  background-color: #4a5470;
}

/* Asegurar visibilidad */
.fixed {
  position: fixed !important;
}

/* Mejorar scroll de prompts */
.bg-base-100 p {
  scrollbar-width: thin;
  scrollbar-color: var(--border-base-300) transparent;
}

.bg-base-100 p::-webkit-scrollbar {
  width: 6px;
}

.bg-base-100 p::-webkit-scrollbar-track {
  background: transparent;
}

.bg-base-100 p::-webkit-scrollbar-thumb {
  background-color: var(--border-base-300);
  border-radius: 3px;
}

.bg-base-100 p::-webkit-scrollbar-thumb:hover {
  background-color: #4a5470;
}
</style>

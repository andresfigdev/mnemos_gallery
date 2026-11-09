<template>
  <!-- Modal fullscreen -->
  <Teleport to="body">
    <div 
      v-show="isOpen"
      class="image-viewer-modal"
      :class="{ 'opacity-0': !showContent }"
      @click="handleBackgroundClick"
    >
      <div class="viewer-content">
        <!-- Botón cerrar -->
        <button @click="close" class="viewer-btn viewer-btn-close">
          <X :size="24" />
        </button>

        <!-- Navegación -->
        <button 
          v-show="images.length > 1" 
          @click.stop="prev" 
          class="viewer-btn viewer-btn-prev"
          :disabled="currentIndex === 0"
          :style="{ opacity: currentIndex === 0 ? '0.3' : '1' }"
        >
          <ChevronLeft :size="32" />
        </button>

        <button 
          v-show="images.length > 1" 
          @click.stop="next" 
          class="viewer-btn viewer-btn-next"
          :disabled="currentIndex >= images.length - 1"
          :style="{ opacity: currentIndex >= images.length - 1 ? '0.3' : '1' }"
        >
          <ChevronRight :size="32" />
        </button>

        <!-- Contenedor de imagen -->
        <div class="viewer-image-container" @click.stop>
          <!-- Loading -->
          <div v-if="loading" class="viewer-loading">
            <span class="loading loading-spinner loading-lg text-white"></span>
            <p class="text-white text-sm mt-4">Cargando imagen...</p>
          </div>

          <!-- Imagen -->
          <img 
            v-show="!loading && !imageError" 
            ref="imageRef"
            :src="currentImageUrl" 
            :alt="currentImageName"
            class="viewer-image"
            @load="handleImageLoad"
            @error="handleImageError"
          />

          <!-- Error -->
          <div v-if="imageError" class="viewer-error">
            <ImageOff :size="48" class="text-white opacity-50" />
            <p class="text-white text-sm mt-4">No se pudo cargar la imagen</p>
          </div>
        </div>

        <!-- Info inferior -->
        <div class="viewer-info">
          <p class="text-white text-sm text-center">
            <span v-if="images.length > 1">{{ currentIndex + 1 }} / {{ images.length }} - </span>
            <span>{{ currentImageName }}</span>
          </p>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { X, ChevronLeft, ChevronRight, ImageOff } from 'lucide-vue-next'
import { getFullImageUrl } from '../api'

export interface ImageViewerData {
  id: number
  path: string
}

const isOpen = ref(false)
const showContent = ref(false)
const loading = ref(false)
const imageError = ref(false)
const images = ref<ImageViewerData[]>([])
const currentIndex = ref(0)
const imageRef = ref<HTMLImageElement | null>(null)

const currentImage = computed(() => {
  return images.value[currentIndex.value] || null
})

const currentImageUrl = computed(() => {
  if (!currentImage.value) return ''
  return getFullImageUrl(currentImage.value.id)
})

const currentImageName = computed(() => {
  if (!currentImage.value) return ''
  const parts = currentImage.value.path.split(/[/\\]/)
  return parts[parts.length - 1]
})

// Manejadores de teclado
const handleKeydown = (e: KeyboardEvent) => {
  if (!isOpen.value) return
  
  switch (e.key) {
    case 'Escape':
      close()
      break
    case 'ArrowLeft':
      prev()
      break
    case 'ArrowRight':
      next()
      break
  }
}

// Watch para agregar/quitar event listeners
watch(isOpen, (newValue) => {
  if (newValue) {
    document.addEventListener('keydown', handleKeydown)
    document.body.style.overflow = 'hidden'
  } else {
    document.removeEventListener('keydown', handleKeydown)
    document.body.style.overflow = ''
  }
})

const open = async (imageList: ImageViewerData[], startIndex: number = 0) => {
  images.value = imageList
  currentIndex.value = startIndex
  loading.value = true
  imageError.value = false
  
  isOpen.value = true
  await nextTick()
  showContent.value = true
}

const close = () => {
  showContent.value = false
  
  setTimeout(() => {
    isOpen.value = false
    images.value = []
    currentIndex.value = 0
  }, 300)
}

const prev = () => {
  if (currentIndex.value > 0) {
    currentIndex.value--
    loadImage()
  }
}

const next = () => {
  if (currentIndex.value < images.value.length - 1) {
    currentIndex.value++
    loadImage()
  }
}

const loadImage = () => {
  loading.value = true
  imageError.value = false
}

const handleImageLoad = () => {
  loading.value = false
}

const handleImageError = () => {
  loading.value = false
  imageError.value = true
}

const handleBackgroundClick = (e: MouseEvent) => {
  // Solo cerrar si se hace clic en el fondo, no en la imagen
  if (e.target === e.currentTarget) {
    close()
  }
}

// Watch para recargar imagen cuando cambia el índice
watch(currentIndex, () => {
  loadImage()
})

defineExpose({ open, close })
</script>

<style scoped>
.image-viewer-modal {
  position: fixed;
  inset: 0;
  z-index: 10002;
  background-color: rgba(0, 0, 0, 0.95);
  transition: opacity 0.3s ease;
}

.viewer-content {
  position: relative;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.viewer-btn {
  position: absolute;
  z-index: 10;
  background: transparent;
  border: none;
  color: white;
  cursor: pointer;
  border-radius: 50%;
  padding: 0.75rem;
  transition: background-color 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.viewer-btn:hover:not(:disabled) {
  background-color: rgba(255, 255, 255, 0.2);
}

.viewer-btn:disabled {
  cursor: not-allowed;
}

.viewer-btn-close {
  top: 1rem;
  right: 1rem;
}

.viewer-btn-prev {
  left: 1rem;
  top: 50%;
  transform: translateY(-50%);
}

.viewer-btn-next {
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
}

.viewer-image-container {
  width: 100%;
  height: 100%;
  padding: 4rem 4rem 5rem 4rem; /* Más padding abajo para el info */
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  overflow: hidden;
}

.viewer-image {
  max-width: calc(100vw - 8rem); /* Restar padding izquierdo y derecho */
  max-height: calc(100vh - 9rem); /* Restar padding superior, inferior y espacio del info */
  width: auto;
  height: auto;
  object-fit: contain;
  object-position: center;
}

.viewer-loading,
.viewer-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.viewer-info {
  position: absolute;
  bottom: 1rem;
  left: 50%;
  transform: translateX(-50%);
  background-color: rgba(0, 0, 0, 0.7);
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
}
</style>


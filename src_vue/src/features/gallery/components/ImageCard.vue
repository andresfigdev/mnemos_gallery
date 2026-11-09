<template>
  <div class="image-card">
    <div
      class="image-thumbnail-container cursor-pointer hover:opacity-90 transition-opacity"
      @click="handleThumbAreaClick"
      :title="pickable ? 'Click para marcar o desmarcar' : 'Click para ver en pantalla completa'"
    >
      <label
        v-if="pickable"
        class="rename-pick-badge"
        @click.stop
      >
        <input
          type="checkbox"
          class="checkbox checkbox-sm checkbox-primary"
          :checked="picked"
          @click.prevent="emit('togglePick', image.id)"
        />
      </label>
      <img 
        :src="thumbnailUrl" 
        :alt="image.path" 
        class="image-thumbnail" 
        @error="handleImageError"
        v-if="!imageError"
      />
      <div v-else class="image-thumbnail image-error">
        <span>❌</span>
      </div>
      <!-- Badge si tiene metadatos -->
      <div v-if="hasMetadata" class="metadata-badge" title="Tiene metadatos AI">
        <FileJson :size="12" />
      </div>
    </div>
    <div class="image-info">
      <div class="image-name">{{ imageName }}</div>
      <div class="image-meta">{{ image.width }}x{{ image.height }} | {{ formatBytes(image.size) }}</div>
      <div class="image-actions">
        <button @click.stop="handleDetailsClick" class="btn btn-xs btn-ghost details-btn">
          Detalles
        </button>
        <button 
          @click.stop="handleMoveToTrash" 
          class="btn btn-xs btn-ghost text-error details-btn"
          :disabled="movingToTrash"
          title="Mover a papelera"
        >
          <Trash2 v-if="!movingToTrash" :size="12" />
          <span v-else class="loading loading-spinner loading-xs"></span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { FileJson, Trash2 } from 'lucide-vue-next'
import type { Image } from '../api'
import { getThumbnailUrl, moveImageToTrash } from '../api'
import { getSetting } from '../../settings/api'

const props = withDefaults(
  defineProps<{
    image: Image
    pickable?: boolean
    picked?: boolean
  }>(),
  { pickable: false, picked: false }
)

const emit = defineEmits<{
  (e: 'showDetails', imageId: number): void
  (e: 'expandImage', imageId: number): void
  (e: 'imageMoved', imageId: number): void
  (e: 'togglePick', imageId: number): void
}>()

const imageError = ref(false)
const movingToTrash = ref(false)
const shouldConfirmTrashMove = ref(true) // Por defecto siempre pregunta

const thumbnailUrl = computed(() => {
  return props.image.id ? getThumbnailUrl(props.image.id) : ''
})

const imageName = computed(() => {
  const parts = props.image.path.split(/[/\\]/)
  return parts[parts.length - 1]
})

const hasMetadata = computed(() => {
  return props.image.prompt_json || props.image.workflow_json
})

const formatBytes = (bytes: number, decimals = 2) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

const handleImageError = () => {
  imageError.value = true
}

const handleDetailsClick = () => {
  emit('showDetails', props.image.id)
}

const handleThumbAreaClick = () => {
  if (props.pickable) {
    emit('togglePick', props.image.id)
    return
  }
  emit('expandImage', props.image.id)
}

async function loadConfirmSetting() {
  try {
    const setting = await getSetting('confirm_trash_move')
    // Si no existe o es null, usar true por defecto
    shouldConfirmTrashMove.value = setting.value === null || setting.value === undefined || setting.value.toLowerCase() === 'true'
  } catch (err: any) {
    // Si no existe el setting (404), usar true por defecto
    if (err.response?.status === 404) {
      shouldConfirmTrashMove.value = true
    } else {
      console.error('Error al cargar configuración de confirmación:', err)
      // En caso de error, usar true por defecto (más seguro)
      shouldConfirmTrashMove.value = true
    }
  }
}

async function handleMoveToTrash() {
  if (movingToTrash.value) return
  
  // Solo preguntar si la configuración está activada
  if (shouldConfirmTrashMove.value) {
    if (!confirm(`¿Mover "${imageName.value}" a la papelera?`)) {
      return
    }
  }
  
  movingToTrash.value = true
  try {
    await moveImageToTrash(props.image.id)
    emit('imageMoved', props.image.id)
  } catch (err: any) {
    console.error('Error moviendo imagen a papelera:', err)
    alert(err.response?.data?.detail || 'Error al mover imagen a papelera')
  } finally {
    movingToTrash.value = false
  }
}

onMounted(() => {
  loadConfirmSetting()
})
</script>

<style scoped>
.image-thumbnail-container {
  position: relative;
}

.image-error {
  display: flex;
  align-items: center;
  justify-content: center;
}

.rename-pick-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  z-index: 2;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.45);
}

.metadata-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: #86efac;
  padding: 2px 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-actions {
  margin-top: 4px;
  display: flex;
  justify-content: flex-end;
}

.details-btn {
  font-size: 0.7rem;
  padding: 4px 12px;
  height: auto;
  min-height: unset;
  border-radius: 0.375rem;
}
</style>

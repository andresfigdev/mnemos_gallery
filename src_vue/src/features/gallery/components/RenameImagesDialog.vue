<template>
  <section class="rename-embedded">
    <div class="rename-head">
      <h4 class="rename-title">Renombrar imágenes</h4>
      <button type="button" class="btn btn-xs btn-ghost" @click="close">
        Cerrar
      </button>
    </div>

    <p v-if="error" class="rename-error">{{ error }}</p>

    <div v-if="step === 'choose'" class="rename-block">
      <p class="rename-help">
        Elige si quieres renombrar solo una selección (más control) o todas las imágenes de la carpeta activa (más rápido, con confirmación).
      </p>
      <button type="button" class="btn btn-sm btn-primary justify-start" @click="startSelectedFlow">
        Renombrar imágenes seleccionadas
      </button>
      <button type="button" class="btn btn-sm btn-outline justify-start" @click="startAllFlow">
        Renombrar toda la carpeta
      </button>
    </div>

    <div v-else-if="step === 'pick'" class="rename-block">
      <p class="rename-help">
        Marca imágenes en la galería (aparece una casilla en cada tarjeta). Puedes usar «Seleccionar visibles» en la barra de la galería.
      </p>
      <p class="rename-counter">Seleccionadas: {{ pickedImageIds.length }}</p>
      <div class="rename-actions">
        <button type="button" class="btn btn-sm btn-ghost" @click="emit('stop-picking')">Cancelar selección</button>
        <button
          type="button"
          class="btn btn-sm btn-primary"
          :disabled="pickedImageIds.length === 0 || loading"
          @click="runPreview('selected')"
        >
          Vista previa
        </button>
      </div>
    </div>

    <div v-else-if="step === 'confirm_all'" class="rename-block">
      <p class="rename-subtitle">Renombrado masivo</p>
      <p class="rename-help">
        Se aplicará la nomenclatura a todas las imágenes de esta carpeta (solo esta carpeta lógica, sin subcarpetas).
      </p>
      <label class="label cursor-pointer justify-start gap-2">
        <input v-model="confirmMass" type="checkbox" class="checkbox checkbox-sm" />
        <span class="label-text text-xs">Confirmo que quiero renombrar toda la carpeta</span>
      </label>
      <div class="rename-actions">
        <button type="button" class="btn btn-sm btn-ghost" @click="step = 'choose'">Atrás</button>
        <button
          type="button"
          class="btn btn-sm btn-primary"
          :disabled="!confirmMass || loading"
          @click="runPreview('all')"
        >
          Vista previa
        </button>
      </div>
    </div>

    <div v-else-if="step === 'preview'" class="rename-block">
      <div class="rename-meta">
        Siguiente índice: {{ preview?.next_counter_start }} · Relacionadas: {{ preview?.related_count }} · Otras:
        {{ preview?.unrelated_count }} · Sin cambios: {{ preview?.unchanged_count }}
      </div>
      <div class="rename-table-wrap">
        <table class="table rename-table">
          <thead>
            <tr>
              <th class="rename-th rename-th-before" scope="col">Antes</th>
              <th class="rename-th rename-th-after" scope="col">Después</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in previewRows" :key="row.image_id">
              <td class="rename-td rename-td-before rename-path-cell" :title="row.old_path">
                {{ shortFileStem(row.old_path) }}
              </td>
              <td class="rename-td rename-td-after rename-path-cell" :title="row.new_path || 'sin cambios'">
                <span v-if="row.reason === 'rename' && row.new_path">{{ shortFileStem(row.new_path) }}</span>
                <span v-else class="rename-unchanged">sin cambios</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="rename-actions">
        <button type="button" class="btn btn-sm btn-ghost" :disabled="loading" @click="goBackFromPreview">Atrás</button>
        <button type="button" class="btn btn-sm btn-primary" :disabled="loading || !preview" @click="runApply">
          Aplicar
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { RenamePreviewEntry, RenamePreviewResponse } from '../api'
import { applyFolderNodeRename, previewFolderNodeRename } from '../api'

const props = defineProps<{
  folderId: string
  folderNodeId: number
  pickedImageIds: number[]
}>()

const emit = defineEmits<{
  close: []
  applied: []
  'start-picking': []
  'stop-picking': []
}>()

type Step = 'choose' | 'pick' | 'confirm_all' | 'preview'
const step = ref<Step>('choose')
const preview = ref<RenamePreviewResponse | null>(null)
const lastMode = ref<'all' | 'selected'>('all')
const confirmMass = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

const previewRows = computed<RenamePreviewEntry[]>(() => preview.value?.entries ?? [])

/** Nombre de archivo sin carpeta ni extensión (para la tabla de vista previa). */
function shortFileStem(relPath: string | null | undefined): string {
  if (!relPath) return '—'
  const norm = relPath.replace(/\\/g, '/')
  const parts = norm.split('/').filter(Boolean)
  const base = parts.length ? parts[parts.length - 1]! : norm
  const dot = base.lastIndexOf('.')
  if (dot <= 0) return base
  return base.slice(0, dot)
}

function close() {
  emit('stop-picking')
  emit('close')
}

function reset() {
  step.value = 'choose'
  preview.value = null
  confirmMass.value = false
  error.value = null
  lastMode.value = 'all'
}

function startSelectedFlow() {
  reset()
  step.value = 'pick'
  emit('start-picking')
}

function startAllFlow() {
  reset()
  step.value = 'confirm_all'
}

async function runPreview(mode: 'all' | 'selected') {
  error.value = null
  loading.value = true
  lastMode.value = mode
  try {
    const body =
      mode === 'all'
        ? { mode: 'all' as const }
        : { mode: 'selected' as const, image_ids: [...props.pickedImageIds] }
    preview.value = await previewFolderNodeRename(props.folderId, props.folderNodeId, body)
    step.value = 'preview'
    emit('stop-picking')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err.response?.data?.detail || err.message || 'Error en vista previa'
  } finally {
    loading.value = false
  }
}

function goBackFromPreview() {
  preview.value = null
  if (lastMode.value === 'all') {
    step.value = 'confirm_all'
  } else {
    step.value = 'pick'
    emit('start-picking')
  }
}

async function runApply() {
  if (!preview.value) return
  error.value = null
  loading.value = true
  try {
    const body =
      lastMode.value === 'all'
        ? { mode: 'all' as const }
        : { mode: 'selected' as const, image_ids: [...props.pickedImageIds] }
    await applyFolderNodeRename(props.folderId, props.folderNodeId, body)
    emit('applied')
    close()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err.response?.data?.detail || err.message || 'Error al aplicar'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.rename-embedded {
  border: 1px solid var(--border-base-300);
  border-radius: 0.6rem;
  background: var(--bg-base-200);
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.rename-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.rename-title {
  font-size: 0.85rem;
  font-weight: 600;
}

.rename-block {
  display: flex;
  flex-direction: column;
  gap: 0.48rem;
}

.rename-help {
  font-size: 0.75rem;
  line-height: 1.35;
  opacity: 0.82;
}

.rename-subtitle {
  font-size: 0.78rem;
  font-weight: 600;
}

.rename-counter {
  font-size: 0.78rem;
  font-weight: 600;
  margin-top: 0.05rem;
}

.rename-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
  margin-top: 0.1rem;
}

.rename-meta {
  font-size: 0.72rem;
  line-height: 1.35;
  opacity: 0.78;
}

.rename-table-wrap {
  width: 100%;
  overflow: auto;
  border: 1px solid var(--border-base-300);
  border-radius: 0.45rem;
  max-height: 21rem;
  background: var(--bg-base-100);
}

.rename-table-wrap table.rename-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
}

.rename-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-base-200);
  font-size: 0.73rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-align: left;
  padding: 0.55rem 0.9rem;
  border-bottom: 1px solid var(--border-base-300);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.06);
}

.rename-th-before {
  width: 50%;
}

.rename-th-after {
  width: 50%;
  border-left: 1px solid var(--border-base-300);
  background: var(--bg-base-100);
}

.rename-table tbody td {
  padding: 0.48rem 0.9rem;
  vertical-align: middle;
  border-bottom: 1px solid var(--border-base-300);
}

.rename-td-after {
  border-left: 1px solid var(--border-base-300);
  background: rgba(148, 163, 184, 0.05);
}

.rename-table tbody tr:nth-child(even) .rename-td-before {
  background: rgba(148, 163, 184, 0.07);
}

.rename-table tbody tr:nth-child(even) .rename-td-after {
  background: rgba(148, 163, 184, 0.1);
}

.rename-path-cell {
  font-family: ui-monospace, monospace;
  font-size: 0.72rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 0; /* con table-layout: fixed, fuerza ellipsis al ancho de columna */
}

.rename-unchanged {
  opacity: 0.65;
}

.rename-error {
  font-size: 0.72rem;
  line-height: 1.35;
  color: var(--error, #f87171);
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.32);
  border-radius: 0.45rem;
  padding: 0.42rem 0.5rem;
}
</style>

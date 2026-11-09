<template>
  <section class="dashboard-page">
    <header class="dashboard-header">
      <div>
        <h1>Dashboard</h1>
        <p class="dashboard-subtitle">Vista operativa resumida del contenido de la galería.</p>
      </div>
      <button type="button" class="btn btn-sm btn-primary" :disabled="loading" @click="loadMetrics">
        {{ loading ? 'Actualizando...' : 'Actualizar métricas' }}
      </button>
    </header>

    <div v-if="error" class="alert alert-error">
      <span>{{ error }}</span>
    </div>

    <div v-if="loading && !metrics" class="dashboard-loading">
      <span class="loading loading-spinner loading-md" />
      <span>Cargando métricas...</span>
    </div>

    <template v-else-if="metrics">
      <div class="dashboard-row dashboard-kpis">
        <article class="dashboard-kpi-card">
          <p class="dashboard-kpi-title">Total imágenes</p>
          <p class="dashboard-kpi-value">{{ formatInt(metrics.summary.total_images) }}</p>
        </article>
        <article class="dashboard-kpi-card">
          <p class="dashboard-kpi-title">Carpetas raíz</p>
          <p class="dashboard-kpi-value">{{ formatInt(metrics.summary.total_folders) }}</p>
        </article>
        <article class="dashboard-kpi-card">
          <p class="dashboard-kpi-title">Subcarpetas</p>
          <p class="dashboard-kpi-value">{{ formatInt(metrics.summary.total_subfolders) }}</p>
        </article>
        <article class="dashboard-kpi-card">
          <p class="dashboard-kpi-title">Tags activos</p>
          <p class="dashboard-kpi-value">{{ formatInt(metrics.summary.total_active_tags) }}</p>
        </article>
        <button
          type="button"
          class="dashboard-kpi-card dashboard-kpi-card--clickable"
          @click="openImagesWithFilter({ missing_checkpoint: true })"
        >
          <p class="dashboard-kpi-title">Sin CheckPoint</p>
          <p class="dashboard-kpi-value">{{ formatInt(metrics.ai_usage.missing_checkpoint_count) }}</p>
        </button>
        <button
          type="button"
          class="dashboard-kpi-card dashboard-kpi-card--clickable"
          @click="openImagesWithFilter({ missing_lora: true })"
        >
          <p class="dashboard-kpi-title">Sin LoRA</p>
          <p class="dashboard-kpi-value">{{ formatInt(metrics.ai_usage.missing_lora_count) }}</p>
        </button>
      </div>

      <div class="dashboard-row dashboard-grid-2">
        <article class="dashboard-panel">
          <h2>Top 10 CheckPoints</h2>
          <ul class="dashboard-bar-list">
            <li v-for="item in metrics.ai_usage.top_checkpoints" :key="`ckpt-${item.name}`">
              <button
                type="button"
                class="dashboard-bar-item"
                :title="item.name"
                @click="handleFilterFromItem(item)"
              >
                <div class="dashboard-bar-item-top">
                  <span class="dashboard-bar-label">{{ item.display_name }}</span>
                  <span class="dashboard-bar-value">{{ formatInt(item.count) }} · {{ formatPercent(item.percent) }}</span>
                </div>
                <div class="dashboard-bar-track">
                  <div class="dashboard-bar-fill" :style="{ width: `${clampPercent(item.percent)}%` }" />
                </div>
              </button>
            </li>
            <li v-if="metrics.ai_usage.top_checkpoints.length === 0" class="dashboard-empty">Sin datos</li>
          </ul>
        </article>

        <article class="dashboard-panel">
          <h2>Top 10 LoRAs</h2>
          <ul class="dashboard-bar-list">
            <li v-for="item in metrics.ai_usage.top_loras" :key="`lora-${item.name}`">
              <button
                type="button"
                class="dashboard-bar-item"
                :title="item.name"
                @click="handleFilterFromItem(item)"
              >
                <div class="dashboard-bar-item-top">
                  <span class="dashboard-bar-label">{{ item.display_name }}</span>
                  <span class="dashboard-bar-value">{{ formatInt(item.count) }} · {{ formatPercent(item.percent) }}</span>
                </div>
                <div class="dashboard-bar-track">
                  <div class="dashboard-bar-fill" :style="{ width: `${clampPercent(item.percent)}%` }" />
                </div>
              </button>
            </li>
            <li v-if="metrics.ai_usage.top_loras.length === 0" class="dashboard-empty">Sin datos</li>
          </ul>
        </article>
      </div>

      <div class="dashboard-row dashboard-grid-2">
        <article class="dashboard-panel">
          <h2>Root vs Subfolder</h2>
          <div class="dashboard-root-compare">
            <button type="button" class="dashboard-root-card dashboard-root-card--root">
              <span class="dashboard-root-label">Root</span>
              <strong>{{ formatInt(metrics.distribution.root_vs_subfolder.root_images) }}</strong>
              <small>{{ formatPercent(metrics.distribution.root_vs_subfolder.root_percent) }}</small>
            </button>
            <button type="button" class="dashboard-root-card dashboard-root-card--sub">
              <span class="dashboard-root-label">Subfolder</span>
              <strong>{{ formatInt(metrics.distribution.root_vs_subfolder.subfolder_images) }}</strong>
              <small>{{ formatPercent(metrics.distribution.root_vs_subfolder.subfolder_percent) }}</small>
            </button>
          </div>
        </article>

        <article class="dashboard-panel">
          <h2>Imágenes por tipo de carpeta</h2>
          <ul class="dashboard-bar-list">
            <li v-for="item in metrics.distribution.images_by_folder_type" :key="`type-${item.name}`">
              <button
                type="button"
                class="dashboard-bar-item"
                :title="item.name"
                @click="handleFilterFromItem(item)"
              >
                <div class="dashboard-bar-item-top">
                  <span class="dashboard-bar-label">{{ item.display_name }}</span>
                  <span class="dashboard-bar-value">{{ formatInt(item.count) }} · {{ formatPercent(item.percent) }}</span>
                </div>
                <div class="dashboard-bar-track">
                  <div class="dashboard-bar-fill" :style="{ width: `${clampPercent(item.percent)}%` }" />
                </div>
              </button>
            </li>
            <li v-if="metrics.distribution.images_by_folder_type.length === 0" class="dashboard-empty">Sin datos</li>
          </ul>
        </article>
      </div>

      <div class="dashboard-row">
        <article class="dashboard-panel">
          <h2>Top carpetas raíz</h2>
          <ul class="dashboard-bar-list">
            <li v-for="item in topFolders" :key="`folder-${item.folder_id}`">
              <button
                type="button"
                class="dashboard-bar-item"
                :title="item.folder_name"
                @click="handleOpenFolder(item.folder_id)"
              >
                <div class="dashboard-bar-item-top">
                  <span class="dashboard-bar-label">{{ item.display_name }}</span>
                  <span class="dashboard-bar-value">{{ formatInt(item.count) }} · {{ formatPercent(item.percent) }}</span>
                </div>
                <div class="dashboard-bar-track">
                  <div class="dashboard-bar-fill" :style="{ width: `${clampPercent(item.percent)}%` }" />
                </div>
              </button>
            </li>
            <li v-if="topFolders.length === 0" class="dashboard-empty">Sin datos</li>
          </ul>
        </article>
      </div>

      <p class="dashboard-footer">Última actualización: {{ generatedAtLabel }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDashboardMetrics, type DashboardMetrics, type DashboardNamedCount } from '../../gallery/api'

type DashboardNavigationPayload = {
  missing_checkpoint?: boolean
  missing_lora?: boolean
  checkpoint_name?: string
  lora_name?: string
  folder_type?: string
  folder_id?: string
}

const emit = defineEmits<{
  (e: 'openImages', payload: DashboardNavigationPayload): void
}>()

const metrics = ref<DashboardMetrics | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const topFolders = computed(() => (metrics.value?.distribution.images_by_folder ?? []).slice(0, 10))

const generatedAtLabel = computed(() => {
  const raw = metrics.value?.generated_at
  if (!raw) return '—'
  try {
    return new Date(raw).toLocaleString()
  } catch {
    return raw
  }
})

function formatInt(value: number): string {
  return new Intl.NumberFormat('es-CL').format(value)
}

function formatPercent(value: number): string {
  return `${value.toFixed(2)}%`
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value))
}

function openImagesWithFilter(payload: DashboardNavigationPayload): void {
  emit('openImages', payload)
}

function handleFilterFromItem(item: DashboardNamedCount): void {
  const mode = item.filter?.mode
  const value = item.filter?.value
  if (!mode || !value) return
  if (mode === 'checkpoint_name') {
    openImagesWithFilter({ checkpoint_name: value })
    return
  }
  if (mode === 'lora_name') {
    openImagesWithFilter({ lora_name: value })
    return
  }
  if (mode === 'folder_type') {
    openImagesWithFilter({ folder_type: value })
  }
}

function handleOpenFolder(folderId: string): void {
  openImagesWithFilter({ folder_id: folderId })
}

async function loadMetrics(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    metrics.value = await getDashboardMetrics()
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } }; message?: string }
    error.value = e.response?.data?.detail || e.message || 'No se pudieron cargar las métricas.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadMetrics()
})
</script>

<style scoped>
.dashboard-page {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.8rem;
}

.dashboard-header h1 {
  margin: 0;
  font-size: 1.15rem;
  color: var(--text-base-content);
}

.dashboard-subtitle {
  margin: 0.25rem 0 0;
  opacity: 0.78;
  font-size: 0.86rem;
}

.dashboard-loading {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.9rem;
  opacity: 0.78;
}

.dashboard-row {
  display: grid;
  gap: 0.75rem;
}

.dashboard-kpis {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.dashboard-kpi-card {
  background: var(--bg-base-200);
  border: 1px solid var(--border-base-300);
  border-radius: 0.6rem;
  padding: 0.65rem 0.7rem;
  text-align: left;
}

.dashboard-kpi-card--clickable {
  appearance: none;
  font: inherit;
  color: var(--text-base-content);
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.dashboard-kpi-card--clickable:hover {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
}

.dashboard-kpi-title {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-base);
}

.dashboard-kpi-value {
  margin: 0.2rem 0 0;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text-base-content);
}

.dashboard-grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.dashboard-panel {
  border: 1px solid var(--border-base-300);
  border-radius: 0.7rem;
  background: var(--bg-base-200);
  padding: 0.7rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.dashboard-panel h2 {
  margin: 0;
  font-size: 0.9rem;
  color: var(--text-base-content);
  font-weight: 600;
}

.dashboard-root-compare {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
}

.dashboard-root-card {
  appearance: none;
  font: inherit;
  color: var(--text-base-content);
  text-align: left;
  border-radius: 0.6rem;
  border: 1px solid var(--border-base-300);
  background: var(--bg-base-200);
  padding: 0.6rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.15rem;
  cursor: default;
}

.dashboard-root-card strong {
  font-size: 1.2rem;
}

.dashboard-root-card small {
  opacity: 0.72;
}

.dashboard-root-label {
  font-size: 0.78rem;
  opacity: 0.72;
}

.dashboard-bar-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.dashboard-bar-item {
  appearance: none;
  width: 100%;
  border: 1px solid var(--border-base-300);
  border-radius: 0.55rem;
  background: var(--bg-base-200);
  padding: 0.45rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  text-align: left;
  font: inherit;
  color: var(--text-base-content);
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.dashboard-bar-item:hover {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--bg-base-200) 92%, var(--primary) 8%);
}

.dashboard-bar-item-top {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  align-items: baseline;
}

.dashboard-bar-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8rem;
  color: var(--text-base-content);
  font-weight: 500;
}

.dashboard-bar-value {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--text-base);
  font-family: ui-monospace, monospace;
}

.dashboard-bar-track {
  width: 100%;
  height: 0.45rem;
  background: var(--neutral);
  border: 1px solid var(--border-base-300);
  border-radius: 999px;
  overflow: hidden;
  box-sizing: border-box;
}

.dashboard-bar-fill {
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  background: var(--primary);
}

.dashboard-empty {
  opacity: 0.6;
  font-size: 0.82rem;
}

.dashboard-footer {
  margin: 0;
  font-size: 0.76rem;
  opacity: 0.72;
}

@media (max-width: 1200px) {
  .dashboard-kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .dashboard-grid-2 {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .dashboard-kpis,
  .dashboard-root-compare {
    grid-template-columns: 1fr;
  }
}
</style>

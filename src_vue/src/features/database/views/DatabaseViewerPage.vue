<template>
  <div class="database-viewer-page">
    <header class="page-header">
      <h1>
        <DatabaseIcon :size="24" />
        Visor de Base de Datos
      </h1>
      <p class="subtitle">Visualiza las tablas y datos de la base de datos</p>
    </header>

    <div class="database-content">
      <!-- Panel izquierdo: Lista de tablas -->
      <aside class="tables-sidebar">
        <div class="sidebar-header">
          <h2>Tablas</h2>
          <button @click="loadTables" class="btn-refresh" :disabled="loading">
            <RefreshCwIcon :size="16" :class="{ spin: loading }" />
          </button>
        </div>
        
        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          <span>Cargando tablas...</span>
        </div>
        
        <div v-else-if="error" class="error-state">
          <AlertCircleIcon :size="24" />
          <p>{{ error }}</p>
        </div>
        
        <div v-else class="tables-list">
          <div
            v-for="table in tables"
            :key="table.name"
            class="table-item"
            :class="{ active: selectedTable === table.name }"
            @click="selectTable(table.name)"
          >
            <div class="table-name">
              <TableIcon :size="16" />
              {{ table.name }}
            </div>
            <div class="table-meta">
              <span class="row-count">{{ formatNumber(table.row_count) }} filas</span>
              <span class="column-count">{{ table.columns.length }} columnas</span>
            </div>
          </div>
        </div>
      </aside>

      <!-- Panel derecho: Datos de la tabla seleccionada -->
      <main class="table-data-panel">
        <div v-if="!selectedTable" class="empty-state">
          <DatabaseIcon :size="64" />
          <h3>Selecciona una tabla</h3>
          <p>Elige una tabla del panel izquierdo para ver sus datos</p>
        </div>

        <div v-else class="table-viewer">
          <!-- Header de la tabla -->
          <div class="table-header">
            <div class="table-title">
              <h2>{{ selectedTable }}</h2>
              <span v-if="tableData" class="table-info">
                {{ formatNumber(tableData.total_rows) }} filas totales
              </span>
            </div>
            <div class="table-actions">
              <button @click="loadTableData" class="btn-refresh" :disabled="loadingData">
                <RefreshCwIcon :size="16" :class="{ spin: loadingData }" />
              </button>
            </div>
          </div>

          <!-- Información de columnas -->
          <div v-if="selectedTableInfo" class="columns-info">
            <details>
              <summary>
                <span>{{ selectedTableInfo.columns.length }} columnas</span>
                <ChevronDownIcon :size="16" />
              </summary>
              <div class="columns-list">
                <div
                  v-for="col in selectedTableInfo.columns"
                  :key="col.name"
                  class="column-item"
                  :class="{ 
                    'is-pk': col.primary_key,
                    'is-fk': col.foreign_key 
                  }"
                >
                  <div class="column-name">
                    <KeyIcon v-if="col.primary_key" :size="14" class="pk-icon" />
                    <LinkIcon v-if="col.foreign_key" :size="14" class="fk-icon" />
                    <strong>{{ col.name }}</strong>
                    <span class="column-type">{{ col.type }}</span>
                  </div>
                  <div class="column-meta">
                    <span v-if="!col.nullable" class="badge">NOT NULL</span>
                    <span v-if="col.foreign_key" class="badge fk-badge">
                      → {{ col.foreign_key }}
                    </span>
                  </div>
                </div>
              </div>
            </details>
          </div>

          <!-- Datos de la tabla -->
          <div v-if="loadingData" class="loading-state">
            <div class="spinner"></div>
            <span>Cargando datos...</span>
          </div>

          <div v-else-if="dataError" class="error-state">
            <AlertCircleIcon :size="24" />
            <p>{{ dataError }}</p>
          </div>

          <div v-else-if="tableData" class="table-data-container">
            <!-- Tabla de datos -->
            <div class="table-wrapper">
              <table class="data-table">
                <thead>
                  <tr>
                    <th
                      v-for="col in tableData.columns"
                      :key="col"
                      class="sortable"
                      @click="sortByColumn(col)"
                    >
                      {{ col }}
                      <ChevronUpIcon
                        v-if="orderBy === col"
                        :size="14"
                        class="sort-icon"
                      />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in tableData.rows" :key="idx">
                    <td
                      v-for="col in tableData.columns"
                      :key="col"
                      :title="formatCellValue(row[col])"
                    >
                      {{ formatCellValue(row[col]) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Paginación -->
            <div v-if="tableData.total_pages > 1" class="pagination">
              <button
                class="btn-page"
                :disabled="currentPage === 1"
                @click="changePage(currentPage - 1)"
              >
                <ChevronLeftIcon :size="16" />
                Anterior
              </button>
              <span class="page-info">
                Página {{ currentPage }} de {{ tableData.total_pages }}
                <span class="total-info">
                  ({{ formatNumber(tableData.total_rows) }} resultados)
                </span>
              </span>
              <button
                class="btn-page"
                :disabled="currentPage >= tableData.total_pages"
                @click="changePage(currentPage + 1)"
              >
                Siguiente
                <ChevronRightIcon :size="16" />
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  Database as DatabaseIcon,
  Table as TableIcon,
  RefreshCw as RefreshCwIcon,
  AlertCircle as AlertCircleIcon,
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
  Key as KeyIcon,
  Link as LinkIcon
} from 'lucide-vue-next'
import { getTables, getTableData, type TableInfo, type TableData } from '../api'

const loading = ref(false)
const error = ref<string | null>(null)
const tables = ref<TableInfo[]>([])
const selectedTable = ref<string | null>(null)
const selectedTableInfo = ref<TableInfo | null>(null)

const loadingData = ref(false)
const dataError = ref<string | null>(null)
const tableData = ref<TableData | null>(null)
const currentPage = ref(1)
const pageSize = ref(50)
const orderBy = ref<string | null>(null)

async function loadTables() {
  loading.value = true
  error.value = null
  try {
    const overview = await getTables()
    tables.value = overview.tables
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || 'Error cargando tablas'
    console.error('Error cargando tablas:', err)
  } finally {
    loading.value = false
  }
}

async function selectTable(tableName: string) {
  selectedTable.value = tableName
  selectedTableInfo.value = tables.value.find(t => t.name === tableName) || null
  currentPage.value = 1
  orderBy.value = null
  await loadTableData()
}

async function loadTableData() {
  if (!selectedTable.value) return

  loadingData.value = true
  dataError.value = null
  try {
    const data = await getTableData(
      selectedTable.value,
      currentPage.value,
      pageSize.value,
      orderBy.value || undefined
    )
    tableData.value = data
  } catch (err: any) {
    dataError.value = err.response?.data?.detail || err.message || 'Error cargando datos'
    console.error('Error cargando datos:', err)
  } finally {
    loadingData.value = false
  }
}

function changePage(page: number) {
  currentPage.value = page
  loadTableData()
}

function sortByColumn(column: string) {
  if (orderBy.value === column) {
    orderBy.value = null
  } else {
    orderBy.value = column
  }
  currentPage.value = 1
  loadTableData()
}

function formatNumber(num: number): string {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

function formatCellValue(value: any): string {
  if (value === null || value === undefined) return 'NULL'
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'string' && value.length > 100) {
    return value.substring(0, 100) + '...'
  }
  return String(value)
}

onMounted(() => {
  loadTables()
})
</script>

<style scoped>
.database-viewer-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.page-header h1 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0 0 0.5rem 0;
  font-size: 1.5rem;
  font-weight: 600;
}

.subtitle {
  margin: 0;
  opacity: 0.7;
  font-size: 0.9rem;
}

.database-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* Sidebar de tablas */
.tables-sidebar {
  width: 300px;
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--sidebar-bg);
}

.sidebar-header {
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-header h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.btn-refresh {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tables-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.table-item {
  padding: 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 0.5rem;
}

.table-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.table-item.active {
  background: var(--primary-color);
  color: white;
}

.table-name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.table-meta {
  display: flex;
  gap: 0.75rem;
  font-size: 0.75rem;
  opacity: 0.7;
}

/* Panel de datos */
.table-data-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-base);
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  opacity: 0.5;
}

.empty-state h3 {
  margin: 0;
  font-size: 1.25rem;
}

.table-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.table-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.table-title h2 {
  margin: 0 0 0.25rem 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.table-info {
  font-size: 0.85rem;
  opacity: 0.7;
}

.columns-info {
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.columns-info details {
  cursor: pointer;
}

.columns-info summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  list-style: none;
  font-size: 0.9rem;
  font-weight: 500;
}

.columns-info summary::-webkit-details-marker {
  display: none;
}

.columns-list {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.column-item {
  padding: 0.5rem;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 4px;
  font-size: 0.85rem;
}

.column-name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.column-type {
  opacity: 0.6;
  font-weight: normal;
  font-size: 0.8rem;
}

.pk-icon {
  color: #fbbf24;
}

.fk-icon {
  color: #60a5fa;
}

.column-meta {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.badge {
  padding: 0.125rem 0.5rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
}

.fk-badge {
  background: rgba(96, 165, 250, 0.2);
  color: #60a5fa;
}

.table-data-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 1.5rem;
}

.table-wrapper {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.data-table thead {
  position: sticky;
  top: 0;
  background: var(--header-bg);
  z-index: 10;
}

.data-table th {
  padding: 0.75rem;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid var(--border-color);
  white-space: nowrap;
}

.data-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.data-table th.sortable:hover {
  background: rgba(255, 255, 255, 0.05);
}

.sort-icon {
  margin-left: 0.25rem;
}

.data-table td {
  padding: 0.75rem;
  border-bottom: 1px solid var(--border-color);
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.data-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.pagination {
  margin-top: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  flex-shrink: 0;
}

.btn-page {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.875rem;
}

.btn-page:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
}

.btn-page:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.875rem;
  opacity: 0.7;
}

.total-info {
  font-size: 0.75rem;
  opacity: 0.6;
}

.loading-state,
.error-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 2rem;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.spin {
  animation: spin 1s linear infinite;
}
</style>


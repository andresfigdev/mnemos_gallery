/**
 * API client para Database Viewer
 */

import apiClient from '../../shared/api'
import type { AxiosResponse } from 'axios'

export interface ColumnInfo {
  name: string
  type: string
  nullable: boolean
  default?: string | null
  primary_key: boolean
  foreign_key?: string | null
}

export interface TableInfo {
  name: string
  columns: ColumnInfo[]
  row_count: number
  description?: string | null
}

export interface DatabaseOverview {
  tables: TableInfo[]
  total_tables: number
}

export interface TableData {
  table_name: string
  columns: string[]
  rows: Record<string, any>[]
  total_rows: number
  page: number
  page_size: number
  total_pages: number
}

/**
 * Obtiene información de todas las tablas
 */
export async function getTables(): Promise<DatabaseOverview> {
  const response: AxiosResponse<DatabaseOverview> = await apiClient.get('/database/tables')
  return response.data
}

/**
 * Obtiene los datos de una tabla con paginación
 */
export async function getTableData(
  tableName: string,
  page: number = 1,
  pageSize: number = 50,
  orderBy?: string
): Promise<TableData> {
  const params: Record<string, any> = {
    page,
    page_size: pageSize
  }
  if (orderBy) {
    params.order_by = orderBy
  }
  
  const response: AxiosResponse<TableData> = await apiClient.get(
    `/database/tables/${tableName}/data`,
    { params }
  )
  return response.data
}


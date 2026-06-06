import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api'
import type {
  Document,
  DocumentUploadProgress,
  PaginatedResponse,
  UploadDocumentRequest,
} from '@/types'

// ─── Query Keys ───────────────────────────────────────────────
export const documentKeys = {
  all: ['documents'] as const,
  lists: () => [...documentKeys.all, 'list'] as const,
  list: (filters: Record<string, unknown>) => [...documentKeys.lists(), filters] as const,
  detail: (id: string) => [...documentKeys.all, 'detail', id] as const,
}

export interface DocumentFilters {
  search?: string
  department?: string
  status?: string
  tags?: string[]
  page?: number
  pageSize?: number
  sortBy?: string
  sortDir?: 'asc' | 'desc'
}

// ─── Fetch Documents ──────────────────────────────────────────
async function fetchDocuments(filters: DocumentFilters): Promise<PaginatedResponse<Document>> {
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  if (filters.department) params.set('department', filters.department)
  if (filters.status) params.set('status', filters.status)
  if (filters.tags?.length) params.set('tags', filters.tags.join(','))
  if (filters.page) params.set('page', String(filters.page))
  if (filters.pageSize) params.set('pageSize', String(filters.pageSize))
  if (filters.sortBy) params.set('sortBy', filters.sortBy)
  if (filters.sortDir) params.set('sortDir', filters.sortDir)

  const { data } = await apiClient.get<PaginatedResponse<Document>>(`/documents?${params}`)
  return data
}

export function useDocuments(filters: DocumentFilters = {}) {
  return useQuery({
    queryKey: documentKeys.list(filters as Record<string, unknown>),
    queryFn: () => fetchDocuments(filters),
    staleTime: 30_000,
  })
}

// ─── Fetch Single Document ────────────────────────────────────
async function fetchDocument(id: string): Promise<Document> {
  const { data } = await apiClient.get<Document>(`/documents/${id}`)
  return data
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: documentKeys.detail(id),
    queryFn: () => fetchDocument(id),
    enabled: Boolean(id),
  })
}

// ─── Upload Document ──────────────────────────────────────────
export async function uploadDocument(
  request: UploadDocumentRequest,
  onProgress?: (progress: number) => void
): Promise<Document> {
  const formData = new FormData()
  formData.append('file', request.file)
  formData.append('department', request.department)
  if (request.tags?.length) {
    formData.append('tags', JSON.stringify(request.tags))
  }

  const { data } = await apiClient.post<Document>('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress?.(percent)
      }
    },
  })
  return data
}

export function useUploadDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      request,
      onProgress,
    }: {
      request: UploadDocumentRequest
      onProgress?: (progress: number) => void
    }) => uploadDocument(request, onProgress),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// ─── Delete Document ──────────────────────────────────────────
async function deleteDocument(id: string): Promise<void> {
  await apiClient.delete(`/documents/${id}`)
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// ─── Bulk Delete ──────────────────────────────────────────────
async function bulkDeleteDocuments(ids: string[]): Promise<void> {
  await apiClient.post('/documents/bulk-delete', { ids })
}

export function useBulkDeleteDocuments() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: bulkDeleteDocuments,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// ─── Reindex Document ─────────────────────────────────────────
async function reindexDocument(id: string): Promise<Document> {
  const { data } = await apiClient.post<Document>(`/documents/${id}/reindex`)
  return data
}

export function useReindexDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: reindexDocument,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) })
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// ─── Departments (for filter dropdowns) ──────────────────────
async function fetchDepartments(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>('/documents/departments')
  return data
}

export function useDepartments() {
  return useQuery({
    queryKey: ['departments'],
    queryFn: fetchDepartments,
    staleTime: 5 * 60_000,
  })
}

export type { DocumentUploadProgress }

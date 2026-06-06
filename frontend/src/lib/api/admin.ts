import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api'
import type {
  ApiKey,
  AuditLog,
  DashboardMetrics,
  DepartmentDocumentCount,
  InviteUserRequest,
  PaginatedResponse,
  QueryMetric,
  RecentQuery,
  UpdateUserRequest,
  User,
} from '@/types'

// ─── Query Keys ───────────────────────────────────────────────
export const adminKeys = {
  metrics: ['admin', 'metrics'] as const,
  users: (filters?: Record<string, unknown>) => ['admin', 'users', filters] as const,
  auditLogs: (filters?: Record<string, unknown>) => ['admin', 'audit-logs', filters] as const,
  queryMetrics: (days: number) => ['admin', 'query-metrics', days] as const,
  departmentStats: ['admin', 'department-stats'] as const,
  apiKeys: ['admin', 'api-keys'] as const,
}

// ─── Dashboard Metrics ─────────────────────────────────────────
async function fetchMetrics(): Promise<DashboardMetrics> {
  const { data } = await apiClient.get<DashboardMetrics>('/admin/metrics')
  return data
}

export function useMetrics() {
  return useQuery({
    queryKey: adminKeys.metrics,
    queryFn: fetchMetrics,
    staleTime: 60_000,
    refetchInterval: 60_000,
  })
}

// ─── Query Metrics (chart) ─────────────────────────────────────
async function fetchQueryMetrics(days: number): Promise<QueryMetric[]> {
  const { data } = await apiClient.get<QueryMetric[]>(`/admin/metrics/queries?days=${days}`)
  return data
}

export function useQueryMetrics(days = 30) {
  return useQuery({
    queryKey: adminKeys.queryMetrics(days),
    queryFn: () => fetchQueryMetrics(days),
    staleTime: 5 * 60_000,
  })
}

// ─── Department Stats ──────────────────────────────────────────
async function fetchDepartmentStats(): Promise<DepartmentDocumentCount[]> {
  const { data } = await apiClient.get<DepartmentDocumentCount[]>('/admin/metrics/departments')
  return data
}

export function useDepartmentStats() {
  return useQuery({
    queryKey: adminKeys.departmentStats,
    queryFn: fetchDepartmentStats,
    staleTime: 5 * 60_000,
  })
}

// ─── Recent Queries ────────────────────────────────────────────
async function fetchRecentQueries(limit = 10): Promise<RecentQuery[]> {
  const { data } = await apiClient.get<RecentQuery[]>(`/admin/metrics/recent-queries?limit=${limit}`)
  return data
}

export function useRecentQueries(limit = 10) {
  return useQuery({
    queryKey: ['admin', 'recent-queries', limit],
    queryFn: () => fetchRecentQueries(limit),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })
}

// ─── Users ────────────────────────────────────────────────────
export interface UserFilters {
  search?: string
  role?: string
  isActive?: boolean
  page?: number
  pageSize?: number
}

async function fetchUsers(filters: UserFilters): Promise<PaginatedResponse<User>> {
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  if (filters.role) params.set('role', filters.role)
  if (filters.isActive !== undefined) params.set('isActive', String(filters.isActive))
  if (filters.page) params.set('page', String(filters.page))
  if (filters.pageSize) params.set('pageSize', String(filters.pageSize))
  const { data } = await apiClient.get<PaginatedResponse<User>>(`/admin/users?${params}`)
  return data
}

export function useUsers(filters: UserFilters = {}) {
  return useQuery({
    queryKey: adminKeys.users(filters as Record<string, unknown>),
    queryFn: () => fetchUsers(filters),
    staleTime: 30_000,
  })
}

export function useInviteUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: InviteUserRequest) =>
      apiClient.post('/admin/users/invite', request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: UpdateUserRequest }) =>
      apiClient.patch(`/admin/users/${id}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useDeactivateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.post(`/admin/users/${id}/deactivate`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

// ─── Audit Logs ───────────────────────────────────────────────
export interface AuditLogFilters {
  userId?: string
  action?: string
  resource?: string
  status?: string
  dateFrom?: string
  dateTo?: string
  page?: number
  pageSize?: number
}

async function fetchAuditLogs(filters: AuditLogFilters): Promise<PaginatedResponse<AuditLog>> {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined) params.set(k, String(v))
  })
  const { data } = await apiClient.get<PaginatedResponse<AuditLog>>(`/admin/audit-logs?${params}`)
  return data
}

export function useAuditLogs(filters: AuditLogFilters = {}) {
  return useQuery({
    queryKey: adminKeys.auditLogs(filters as Record<string, unknown>),
    queryFn: () => fetchAuditLogs(filters),
    staleTime: 30_000,
  })
}

// ─── API Keys ─────────────────────────────────────────────────
async function fetchApiKeys(): Promise<ApiKey[]> {
  const { data } = await apiClient.get<ApiKey[]>('/admin/api-keys')
  return data
}

export function useApiKeys() {
  return useQuery({
    queryKey: adminKeys.apiKeys,
    queryFn: fetchApiKeys,
  })
}

export function useCreateApiKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, scopes }: { name: string; scopes: string[] }) =>
      apiClient.post<{ key: string; apiKey: ApiKey }>('/admin/api-keys', { name, scopes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.apiKeys })
    },
  })
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/admin/api-keys/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.apiKeys })
    },
  })
}

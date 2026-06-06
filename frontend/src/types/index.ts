export interface User {
  id: string
  email: string
  name: string
  avatar?: string
  role: 'admin' | 'manager' | 'user' | 'viewer'
  organizationId: string
  department?: string
  createdAt: string
  lastLoginAt?: string
  isActive: boolean
  mfaEnabled: boolean
}

export interface Organization {
  id: string
  name: string
  plan: 'free' | 'starter' | 'professional' | 'enterprise'
  logoUrl?: string
  membersCount: number
  documentsCount: number
  storageUsedGb: number
  storageQuotaGb: number
  createdAt: string
}

export interface Document {
  id: string
  name: string
  originalName: string
  mimeType: string
  sizeBytes: number
  department: string
  tags: string[]
  status: 'pending' | 'processing' | 'indexed' | 'failed'
  chunkCount: number
  pageCount?: number
  uploadedBy: User
  uploadedAt: string
  indexedAt?: string
  errorMessage?: string
  metadata: Record<string, unknown>
  embeddingModel?: string
}

export interface DocumentUploadProgress {
  file: File
  id: string
  progress: number
  status: 'queued' | 'uploading' | 'processing' | 'done' | 'error'
  error?: string
}

export interface Chunk {
  id: string
  documentId: string
  content: string
  pageNumber?: number
  chunkIndex: number
  score?: number
}

export interface Source {
  documentId: string
  documentName: string
  chunkId: string
  content: string
  pageNumber?: number
  score: number
  url?: string
}

export interface Message {
  id: string
  conversationId: string
  role: 'user' | 'assistant' | 'system'
  content: string
  sources?: Source[]
  model?: string
  latencyMs?: number
  tokensUsed?: number
  createdAt: string
  feedback?: 'positive' | 'negative' | null
  isStreaming?: boolean
}

export interface Conversation {
  id: string
  title: string
  userId: string
  messages: Message[]
  model: string
  department?: string
  createdAt: string
  updatedAt: string
  messageCount: number
  totalTokens?: number
}

export interface ConversationSummary {
  id: string
  title: string
  lastMessage?: string
  messageCount: number
  model: string
  updatedAt: string
  createdAt: string
}

export interface LLMModel {
  id: string
  name: string
  provider: 'openai' | 'anthropic' | 'google' | 'azure' | 'local'
  contextLength: number
  inputCostPer1k: number
  outputCostPer1k: number
  isAvailable: boolean
  isDefault?: boolean
}

export interface SearchResult {
  documents: Document[]
  conversations: Conversation[]
  totalCount: number
}

export interface DashboardMetrics {
  totalDocuments: number
  indexedDocuments: number
  processingDocuments: number
  failedDocuments: number
  queriesToday: number
  queriesThisMonth: number
  activeUsers: number
  totalUsers: number
  embeddingCostMonth: number
  llmCostMonth: number
  storageUsedGb: number
}

export interface QueryMetric {
  date: string
  count: number
  avgLatencyMs: number
}

export interface DepartmentDocumentCount {
  department: string
  count: number
  indexed: number
}

export interface RecentQuery {
  id: string
  user: Pick<User, 'id' | 'name' | 'avatar'>
  query: string
  model: string
  latencyMs: number
  tokensUsed: number
  sourcesCount: number
  timestamp: string
}

export interface AuditLog {
  id: string
  userId: string
  userName: string
  action: string
  resource: string
  resourceId?: string
  details?: Record<string, unknown>
  ipAddress: string
  userAgent?: string
  timestamp: string
  status: 'success' | 'failure'
}

export interface ApiKey {
  id: string
  name: string
  prefix: string
  scopes: string[]
  createdAt: string
  lastUsedAt?: string
  expiresAt?: string
  isActive: boolean
}

export interface NotificationPreferences {
  emailOnUpload: boolean
  emailOnProcessingComplete: boolean
  emailOnError: boolean
  emailWeeklySummary: boolean
  inAppNotifications: boolean
}

export interface UserSettings {
  defaultModel: string
  responseLanguage: string
  citationsEnabled: boolean
  streamingEnabled: boolean
  darkMode: boolean
  notifications: NotificationPreferences
}

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  expiresAt: number
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  user: User
  organization: Organization
  tokens: AuthTokens
}

export interface InviteUserRequest {
  email: string
  role: User['role']
  department?: string
}

export interface UpdateUserRequest {
  name?: string
  role?: User['role']
  department?: string
  isActive?: boolean
}

export interface ApiError {
  message: string
  code?: string
  status: number
  details?: Record<string, unknown>
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

export interface UploadDocumentRequest {
  file: File
  department: string
  tags?: string[]
}

export interface ChatRequest {
  conversationId?: string
  message: string
  model: string
  department?: string
  stream?: boolean
}

export interface StreamChunk {
  type: 'content' | 'sources' | 'done' | 'error'
  content?: string
  sources?: Source[]
  error?: string
  messageId?: string
  tokensUsed?: number
  latencyMs?: number
}

export type NavItem = {
  label: string
  href: string
  icon: string
  adminOnly?: boolean
  badge?: number
}

export type ThemeMode = 'dark' | 'light' | 'system'

export type SortDirection = 'asc' | 'desc'

export type DocumentStatus = Document['status']
export type UserRole = User['role']
export type LLMProvider = LLMModel['provider']

'use client'

import React, { createContext, useContext, useReducer, useEffect } from 'react'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RagDocument {
  id: string
  name: string
  fileType: string
  mimeType: string
  size: string
  sizeBytes: number
  status: 'uploading' | 'processing' | 'indexed' | 'error'
  pages: number
  department: string
  uploadedAt: string
  content: string       // raw extracted text (empty for binary)
  chunks: string[]      // text chunks for search
  canQuery: boolean     // true if we have extractable content
  error?: string
}

export interface RagSource {
  docId: string
  docName: string
  excerpt: string
  score: number
}

export interface RagMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: RagSource[]
  isStreaming?: boolean
  timestamp: string
  responseMs?: number
}

export interface RagConversation {
  id: string
  title: string
  messages: RagMessage[]
  createdAt: string
  updatedAt: string
}

export interface QueryLog {
  id: string
  query: string
  userName: string
  docsSearched: number
  responseMs: number
  found: boolean
  timestamp: string
}

export interface AppUser {
  id: string
  name: string
  email: string
  role: 'admin' | 'manager' | 'user'
  department: string
  joinedAt: string
  queries: number
  active: boolean
}

export interface AppSettings {
  model: string
  temperature: number
  maxTokens: number
  openaiApiKey: string
  orgName: string
  topK: number
  chunkSize: number
}

export interface AppState {
  documents: RagDocument[]
  conversations: RagConversation[]
  queryLogs: QueryLog[]
  users: AppUser[]
  settings: AppSettings
}

// ─── Actions ─────────────────────────────────────────────────────────────────

type Action =
  | { type: 'LOAD'; state: AppState }
  | { type: 'ADD_DOC'; doc: RagDocument }
  | { type: 'UPDATE_DOC'; id: string; patch: Partial<RagDocument> }
  | { type: 'DELETE_DOC'; id: string }
  | { type: 'ADD_CONV'; conv: RagConversation }
  | { type: 'UPDATE_CONV'; id: string; patch: Partial<RagConversation> }
  | { type: 'UPDATE_MSG'; convId: string; msgId: string; patch: Partial<RagMessage> }
  | { type: 'APPEND_MSG'; convId: string; msg: RagMessage }
  | { type: 'DELETE_CONV'; id: string }
  | { type: 'LOG_QUERY'; log: QueryLog }
  | { type: 'ADD_USER'; user: AppUser }
  | { type: 'UPDATE_USER'; id: string; patch: Partial<AppUser> }
  | { type: 'DELETE_USER'; id: string }
  | { type: 'UPDATE_SETTINGS'; patch: Partial<AppSettings> }

// ─── Defaults ────────────────────────────────────────────────────────────────

const DEFAULT_SETTINGS: AppSettings = {
  model: 'gpt-4o',
  temperature: 0.2,
  maxTokens: 2048,
  openaiApiKey: '',
  orgName: 'My Organization',
  topK: 5,
  chunkSize: 400,
}

const INITIAL_STATE: AppState = {
  documents: [],
  conversations: [],
  queryLogs: [],
  users: [],
  settings: DEFAULT_SETTINGS,
}

// ─── Reducer ─────────────────────────────────────────────────────────────────

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'LOAD': return action.state

    case 'ADD_DOC':
      return { ...state, documents: [action.doc, ...state.documents] }
    case 'UPDATE_DOC':
      return { ...state, documents: state.documents.map(d => d.id === action.id ? { ...d, ...action.patch } : d) }
    case 'DELETE_DOC':
      return { ...state, documents: state.documents.filter(d => d.id !== action.id) }

    case 'ADD_CONV':
      return { ...state, conversations: [action.conv, ...state.conversations] }
    case 'UPDATE_CONV':
      return { ...state, conversations: state.conversations.map(c => c.id === action.id ? { ...c, ...action.patch } : c) }
    case 'UPDATE_MSG':
      return {
        ...state,
        conversations: state.conversations.map(c =>
          c.id === action.convId
            ? { ...c, messages: c.messages.map(m => m.id === action.msgId ? { ...m, ...action.patch } : m) }
            : c
        )
      }
    case 'APPEND_MSG':
      return {
        ...state,
        conversations: state.conversations.map(c =>
          c.id === action.convId ? { ...c, messages: [...c.messages, action.msg] } : c
        )
      }
    case 'DELETE_CONV':
      return { ...state, conversations: state.conversations.filter(c => c.id !== action.id) }

    case 'LOG_QUERY':
      return { ...state, queryLogs: [action.log, ...state.queryLogs].slice(0, 500) }

    case 'ADD_USER':
      return { ...state, users: [...state.users, action.user] }
    case 'UPDATE_USER':
      return { ...state, users: state.users.map(u => u.id === action.id ? { ...u, ...action.patch } : u) }
    case 'DELETE_USER':
      return { ...state, users: state.users.filter(u => u.id !== action.id) }

    case 'UPDATE_SETTINGS':
      return { ...state, settings: { ...state.settings, ...action.patch } }

    default: return state
  }
}

// ─── Context ─────────────────────────────────────────────────────────────────

const StoreCtx = createContext<{
  state: AppState
  dispatch: React.Dispatch<Action>
} | null>(null)

const STORAGE_KEY = 'rag_app_v2'

export function AppStoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)

  // Hydrate from localStorage on mount
  useEffect(() => {
    try {
      // Clean up old storage keys from previous versions
      localStorage.removeItem('rag_indexed_docs')
      localStorage.removeItem('rag_app_state')

      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const saved = JSON.parse(raw) as Partial<AppState>
        // Validate it's actually the right structure (has documents array)
        if (Array.isArray(saved.documents)) {
          dispatch({
            type: 'LOAD', state: {
              // Sanitize docs: ensure required fields are valid types
              documents: saved.documents
                .filter(d => d && typeof d.id === 'string' && typeof d.name === 'string')
                .map(d => ({
                  ...d,
                  chunks: Array.isArray(d.chunks) ? d.chunks : [],
                  status: ['uploading', 'processing', 'indexed', 'error'].includes(d.status) ? d.status : 'indexed',
                  content: typeof d.content === 'string' ? d.content : '',
                  canQuery: Array.isArray(d.chunks) && d.chunks.length > 0,
                })),
              conversations: (saved.conversations ?? [])
                .filter(c => c && typeof c.id === 'string')
                .map(c => ({
                  ...c,
                  messages: (c.messages ?? []).map(m => ({ ...m, isStreaming: false }))
                })),
              queryLogs: (saved.queryLogs ?? []).filter(q => q && typeof q.id === 'string'),
              users: (saved.users ?? []).filter(u => u && typeof u.id === 'string'),
              settings: { ...DEFAULT_SETTINGS, ...(saved.settings ?? {}) },
            }
          })
        }
      }
    } catch { /* fresh state */ }
  }, [])

  // Persist on every change
  useEffect(() => {
    try {
      const toSave: AppState = {
        ...state,
        conversations: state.conversations.map(c => ({
          ...c,
          messages: c.messages.map(m => ({ ...m, isStreaming: false }))
        }))
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
    } catch { /* storage full */ }
  }, [state])

  return <StoreCtx.Provider value={{ state, dispatch }}>{children}</StoreCtx.Provider>
}

export function useAppStore() {
  const ctx = useContext(StoreCtx)
  if (!ctx) throw new Error('useAppStore must be inside AppStoreProvider')
  return ctx
}

// ─── RAG Engine ──────────────────────────────────────────────────────────────

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 2)
}

const STOP_WORDS = new Set([
  'the','and','for','are','but','not','you','all','any','can','had','her','was','one',
  'our','out','day','get','has','him','his','how','man','new','now','old','see','two',
  'way','who','boy','did','its','let','put','say','she','too','use','what','that','this',
  'with','have','from','they','will','been','than','when','were','your'
])

function meaningfulTokens(text: string): string[] {
  return tokenize(text).filter(t => !STOP_WORDS.has(t))
}

export function buildChunks(text: string, chunkSize = 400): string[] {
  if (!text.trim()) return []

  // Try paragraph-based chunking first
  const paras = text.split(/\n{2,}/).map(p => p.trim()).filter(Boolean)
  const chunks: string[] = []
  let current = ''

  for (const para of paras) {
    const combined = current ? current + '\n\n' + para : para
    if (combined.split(/\s+/).length > chunkSize && current) {
      chunks.push(current.trim())
      current = para
    } else {
      current = combined
    }
  }
  if (current.trim()) chunks.push(current.trim())

  // Fallback: word-based chunking
  if (chunks.length === 0) {
    const words = text.split(/\s+/)
    for (let i = 0; i < words.length; i += chunkSize) {
      chunks.push(words.slice(i, i + chunkSize).join(' '))
    }
  }

  return chunks
}

export interface SearchHit {
  docId: string
  docName: string
  chunkIndex: number
  chunk: string
  score: number
}

export function ragSearch(
  query: string,
  documents: RagDocument[],
  topK = 5
): SearchHit[] {
  const qTokens = meaningfulTokens(query)
  if (qTokens.length === 0) return []

  const hits: SearchHit[] = []
  const qSet = new Set(qTokens)

  for (const doc of documents) {
    if (doc.status !== 'indexed' || doc.chunks.length === 0) continue

    for (let ci = 0; ci < doc.chunks.length; ci++) {
      const chunk = doc.chunks[ci]
      const cTokens = tokenize(chunk)
      const cFreq: Record<string, number> = {}
      for (const t of cTokens) cFreq[t] = (cFreq[t] ?? 0) + 1

      // BM25 scoring
      const k1 = 1.5, b = 0.75, avgLen = 350
      let score = 0
      for (const qt of qSet) {
        const tf = cFreq[qt] ?? 0
        if (tf > 0) {
          const bm25 = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * cTokens.length / avgLen))
          score += bm25
        }
      }

      // Bonus: exact phrase match
      if (chunk.toLowerCase().includes(query.toLowerCase().slice(0, 20))) {
        score *= 1.5
      }

      // Bonus: first chunk (usually most relevant)
      if (ci === 0) score *= 1.1

      if (score > 0) {
        hits.push({ docId: doc.id, docName: doc.name, chunkIndex: ci, chunk, score })
      }
    }
  }

  return hits.sort((a, b) => b.score - a.score).slice(0, topK)
}

export function formatAnswer(query: string, hits: SearchHit[], docs: RagDocument[]): string {
  if (hits.length === 0) return ''

  const uniqueDocs = [...new Set(hits.map(h => h.docName))]
  const topChunk = hits[0].chunk
  const rest = hits.slice(1, 3)

  const lines: string[] = []

  // Detect question type for smarter formatting
  const q = query.toLowerCase()
  const isWhat = q.startsWith('what')
  const isHow = q.startsWith('how')
  const isWhen = q.startsWith('when')
  const isWhere = q.startsWith('where')
  const isWho = q.startsWith('who')
  const isList = q.includes('list') || q.includes('all ') || q.includes('types')
  const isSummarize = q.includes('summar') || q.includes('overview') || q.includes('explain')

  if (isSummarize) {
    lines.push(`## Summary`)
    lines.push('')
    lines.push(`Based on **${uniqueDocs.map(d => `\`${d}\``).join(', ')}**:`)
    lines.push('')
    lines.push(topChunk)
    if (rest.length > 0) {
      lines.push('')
      lines.push('**Additional context:**')
      lines.push('')
      for (const h of rest) {
        lines.push(`> From \`${h.docName}\`:`)
        lines.push(`> ${h.chunk.slice(0, 300)}${h.chunk.length > 300 ? '…' : ''}`)
        lines.push('')
      }
    }
  } else if (isList) {
    lines.push(`## Results`)
    lines.push('')
    lines.push(topChunk)
    for (const h of rest) {
      lines.push('')
      lines.push(`---`)
      lines.push(h.chunk.slice(0, 400))
    }
  } else {
    // Direct answer format
    lines.push(`## Answer`)
    lines.push('')
    lines.push(topChunk)
    if (rest.length > 0) {
      lines.push('')
      lines.push(`**Related content from \`${rest[0].docName}\`:**`)
      lines.push('')
      lines.push(`> ${rest[0].chunk.slice(0, 300)}${rest[0].chunk.length > 300 ? '…' : ''}`)
    }
  }

  lines.push('')
  lines.push(`---`)
  lines.push(`*Retrieved from ${uniqueDocs.length} document${uniqueDocs.length > 1 ? 's' : ''}: ${uniqueDocs.map(d => `\`${d}\``).join(', ')}*`)

  return lines.join('\n')
}

// ─── Text Extraction ─────────────────────────────────────────────────────────

export function extractTextContent(file: File): Promise<string> {
  return new Promise((resolve) => {
    const textExtensions = /\.(txt|md|markdown|csv|json|xml|html|htm|log|yaml|yml|ts|tsx|js|jsx|py|java|c|cpp|h|css|sql|sh|bash|env|toml|ini|conf)$/i

    if (textExtensions.test(file.name)) {
      const reader = new FileReader()
      reader.onload = e => resolve((e.target?.result as string) ?? '')
      reader.onerror = () => resolve('')
      reader.readAsText(file)
    } else {
      // Binary file (PDF, DOCX, XLSX, etc.) — can't extract in browser without backend
      resolve('')
    }
  })
}

export function getFileType(name: string): string {
  const ext = name.split('.').pop()?.toUpperCase() ?? 'FILE'
  return ext
}

export function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

export function isToday(iso: string): boolean {
  const d = new Date(iso)
  const now = new Date()
  return d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
}

import { useCallback, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api'
import type {
  ChatRequest,
  Conversation,
  ConversationSummary,
  LLMModel,
  Message,
  PaginatedResponse,
  StreamChunk,
} from '@/types'

// ─── Query Keys ───────────────────────────────────────────────
export const chatKeys = {
  all: ['conversations'] as const,
  lists: () => [...chatKeys.all, 'list'] as const,
  list: (filters?: Record<string, unknown>) => [...chatKeys.lists(), filters] as const,
  detail: (id: string) => [...chatKeys.all, 'detail', id] as const,
  models: ['llm-models'] as const,
}

// ─── Fetch Conversations ──────────────────────────────────────
async function fetchConversations(
  page = 1,
  pageSize = 50
): Promise<PaginatedResponse<ConversationSummary>> {
  const { data } = await apiClient.get<PaginatedResponse<ConversationSummary>>(
    `/chat/conversations?page=${page}&pageSize=${pageSize}`
  )
  return data
}

export function useConversations(page = 1) {
  return useQuery({
    queryKey: chatKeys.list({ page }),
    queryFn: () => fetchConversations(page),
    staleTime: 10_000,
  })
}

// ─── Fetch Single Conversation ────────────────────────────────
async function fetchConversation(id: string): Promise<Conversation> {
  const { data } = await apiClient.get<Conversation>(`/chat/conversations/${id}`)
  return data
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: chatKeys.detail(id),
    queryFn: () => fetchConversation(id),
    enabled: Boolean(id),
  })
}

// ─── Create Conversation ──────────────────────────────────────
async function createConversation(title: string, model: string): Promise<Conversation> {
  const { data } = await apiClient.post<Conversation>('/chat/conversations', { title, model })
  return data
}

export function useCreateConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ title, model }: { title: string; model: string }) =>
      createConversation(title, model),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.lists() })
    },
  })
}

// ─── Delete Conversation ──────────────────────────────────────
async function deleteConversation(id: string): Promise<void> {
  await apiClient.delete(`/chat/conversations/${id}`)
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.lists() })
    },
  })
}

// ─── Message Feedback ─────────────────────────────────────────
async function sendFeedback(
  messageId: string,
  feedback: 'positive' | 'negative'
): Promise<void> {
  await apiClient.post(`/chat/messages/${messageId}/feedback`, { feedback })
}

export function useSendFeedback() {
  return useMutation({
    mutationFn: ({ messageId, feedback }: { messageId: string; feedback: 'positive' | 'negative' }) =>
      sendFeedback(messageId, feedback),
  })
}

// ─── Available LLM Models ─────────────────────────────────────
async function fetchModels(): Promise<LLMModel[]> {
  const { data } = await apiClient.get<LLMModel[]>('/chat/models')
  return data
}

export function useLLMModels() {
  return useQuery({
    queryKey: chatKeys.models,
    queryFn: fetchModels,
    staleTime: 5 * 60_000,
  })
}

// ─── Non-streaming Chat Send ──────────────────────────────────
async function sendMessage(request: ChatRequest): Promise<Message> {
  const { data } = await apiClient.post<Message>('/chat/send', { ...request, stream: false })
  return data
}

export function useSendMessage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: sendMessage,
    onSuccess: (_, variables) => {
      if (variables.conversationId) {
        queryClient.invalidateQueries({ queryKey: chatKeys.detail(variables.conversationId) })
      }
      queryClient.invalidateQueries({ queryKey: chatKeys.lists() })
    },
  })
}

// ─── Streaming Message Hook ───────────────────────────────────
export interface StreamingState {
  content: string
  isStreaming: boolean
  error: string | null
  sources: NonNullable<Message['sources']>
  messageId: string | null
  tokensUsed: number | null
  latencyMs: number | null
}

export function useStreamingMessage() {
  const [state, setState] = useState<StreamingState>({
    content: '',
    isStreaming: false,
    error: null,
    sources: [],
    messageId: null,
    tokensUsed: null,
    latencyMs: null,
  })

  const abortControllerRef = useRef<AbortController | null>(null)

  const startStream = useCallback(async (request: ChatRequest) => {
    // Abort any in-progress stream
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setState({
      content: '',
      isStreaming: true,
      error: null,
      sources: [],
      messageId: null,
      tokensUsed: null,
      latencyMs: null,
    })

    const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
    const token = typeof window !== 'undefined' ? localStorage.getItem('accessToken') : null

    try {
      const response = await fetch(`${API_BASE_URL}/chat/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ ...request, stream: true }),
        signal: controller.signal,
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({ message: 'Stream failed' }))
        throw new Error(err.message || `HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') break

          try {
            const chunk: StreamChunk = JSON.parse(raw)

            switch (chunk.type) {
              case 'content':
                setState((prev) => ({
                  ...prev,
                  content: prev.content + (chunk.content ?? ''),
                }))
                break
              case 'sources':
                setState((prev) => ({
                  ...prev,
                  sources: chunk.sources ?? [],
                }))
                break
              case 'done':
                setState((prev) => ({
                  ...prev,
                  isStreaming: false,
                  messageId: chunk.messageId ?? null,
                  tokensUsed: chunk.tokensUsed ?? null,
                  latencyMs: chunk.latencyMs ?? null,
                }))
                break
              case 'error':
                setState((prev) => ({
                  ...prev,
                  isStreaming: false,
                  error: chunk.error ?? 'Unknown stream error',
                }))
                break
            }
          } catch {
            // Skip malformed SSE chunks
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        error: (err as Error).message || 'Streaming failed',
      }))
    }
  }, [])

  const abort = useCallback(() => {
    abortControllerRef.current?.abort()
    setState((prev) => ({ ...prev, isStreaming: false }))
  }, [])

  const reset = useCallback(() => {
    setState({
      content: '',
      isStreaming: false,
      error: null,
      sources: [],
      messageId: null,
      tokensUsed: null,
      latencyMs: null,
    })
  }, [])

  return { ...state, startStream, abort, reset }
}

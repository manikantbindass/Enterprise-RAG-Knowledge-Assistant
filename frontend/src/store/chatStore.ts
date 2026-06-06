import { create } from 'zustand'
import type { Conversation, ConversationSummary, Message, Source } from '@/types'

interface StreamingMessage {
  content: string
  sources: Source[]
  isStreaming: boolean
}

interface ChatState {
  conversations: ConversationSummary[]
  currentConversationId: string | null
  currentConversation: Conversation | null
  streamingMessage: StreamingMessage | null
  isStreaming: boolean
  selectedModel: string
}

interface ChatActions {
  setConversations: (conversations: ConversationSummary[]) => void
  setCurrentConversation: (conversation: Conversation | null) => void
  setCurrentConversationId: (id: string | null) => void
  addMessage: (message: Message) => void
  updateMessage: (messageId: string, updates: Partial<Message>) => void
  setStreamingMessage: (msg: StreamingMessage | null) => void
  appendStreamingContent: (content: string) => void
  setStreamingSources: (sources: Source[]) => void
  setIsStreaming: (streaming: boolean) => void
  finalizeStreamingMessage: (messageId: string, tokensUsed?: number, latencyMs?: number) => void
  setSelectedModel: (model: string) => void
  addConversationSummary: (summary: ConversationSummary) => void
  removeConversation: (id: string) => void
  updateConversationTitle: (id: string, title: string) => void
}

export type ChatStore = ChatState & ChatActions

export const useChatStore = create<ChatStore>((set, get) => ({
  // ─── State ─────────────────────────────────────────────────
  conversations: [],
  currentConversationId: null,
  currentConversation: null,
  streamingMessage: null,
  isStreaming: false,
  selectedModel: 'gpt-4o',

  // ─── Actions ───────────────────────────────────────────────
  setConversations: (conversations) => set({ conversations }),

  setCurrentConversation: (currentConversation) => set({ currentConversation }),

  setCurrentConversationId: (id) => set({ currentConversationId: id }),

  addMessage: (message) => {
    const conv = get().currentConversation
    if (!conv) return
    set({
      currentConversation: {
        ...conv,
        messages: [...conv.messages, message],
        messageCount: conv.messageCount + 1,
        updatedAt: new Date().toISOString(),
      },
    })
  },

  updateMessage: (messageId, updates) => {
    const conv = get().currentConversation
    if (!conv) return
    set({
      currentConversation: {
        ...conv,
        messages: conv.messages.map((m) => (m.id === messageId ? { ...m, ...updates } : m)),
      },
    })
  },

  setStreamingMessage: (streamingMessage) => set({ streamingMessage }),

  appendStreamingContent: (content) => {
    set((state) => ({
      streamingMessage: state.streamingMessage
        ? { ...state.streamingMessage, content: state.streamingMessage.content + content }
        : { content, sources: [], isStreaming: true },
    }))
  },

  setStreamingSources: (sources) => {
    set((state) => ({
      streamingMessage: state.streamingMessage
        ? { ...state.streamingMessage, sources }
        : null,
    }))
  },

  setIsStreaming: (isStreaming) => set({ isStreaming }),

  finalizeStreamingMessage: (messageId, tokensUsed, latencyMs) => {
    const streaming = get().streamingMessage
    const conv = get().currentConversation
    if (!streaming || !conv) return

    const finalMessage: Message = {
      id: messageId,
      conversationId: conv.id,
      role: 'assistant',
      content: streaming.content,
      sources: streaming.sources,
      tokensUsed,
      latencyMs,
      createdAt: new Date().toISOString(),
    }

    set({
      currentConversation: {
        ...conv,
        messages: [...conv.messages, finalMessage],
        messageCount: conv.messageCount + 1,
        updatedAt: new Date().toISOString(),
      },
      streamingMessage: null,
      isStreaming: false,
    })
  },

  setSelectedModel: (selectedModel) => set({ selectedModel }),

  addConversationSummary: (summary) => {
    set((state) => ({ conversations: [summary, ...state.conversations] }))
  },

  removeConversation: (id) => {
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      currentConversationId: state.currentConversationId === id ? null : state.currentConversationId,
      currentConversation:
        state.currentConversation?.id === id ? null : state.currentConversation,
    }))
  },

  updateConversationTitle: (id, title) => {
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === id ? { ...c, title } : c)),
      currentConversation:
        state.currentConversation?.id === id
          ? { ...state.currentConversation, title }
          : state.currentConversation,
    }))
  },
}))

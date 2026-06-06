'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Plus, MessageSquare, ThumbsUp, ThumbsDown, RotateCcw, ChevronDown, ChevronRight, FileText, Paperclip, Brain } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import { format, isToday, isYesterday } from 'date-fns'

interface Source {
  citation_number: number
  doc_filename: string
  page_number: number | null
  excerpt: string
  relevance_score: number
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  isStreaming?: boolean
  feedback?: 'positive' | 'negative' | null
}

interface Conversation {
  id: string
  title: string
  created_at: string
}

const SUGGESTED = [
  'What is our vacation policy?',
  'Summarize the Q3 financial report',
  'What are the GDPR compliance requirements?',
  'Explain the employee onboarding process',
]

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConvId, setCurrentConvId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [model, setModel] = useState('openai')
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const adjustTextarea = () => {
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
    }
  }

  const startNewChat = useCallback(async () => {
    const res = await fetch('/api/v1/chat/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify({ title: null }),
    })
    if (res.ok) {
      const conv = await res.json()
      setConversations(prev => [conv, ...prev])
      setCurrentConvId(conv.id)
      setMessages([])
    }
  }, [])

  const sendMessage = useCallback(async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || isStreaming) return

    let convId = currentConvId
    if (!convId) {
      const res = await fetch('/api/v1/chat/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({ title: content.slice(0, 80) }),
      })
      if (!res.ok) return
      const conv = await res.json()
      convId = conv.id
      setCurrentConvId(conv.id)
      setConversations(prev => [conv, ...prev])
    }

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    const assistantId = (Date.now() + 1).toString()
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', isStreaming: true }
    setMessages(prev => [...prev, assistantMsg])
    setIsStreaming(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const res = await fetch(`/api/v1/chat/conversations/${convId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({ content, llm_provider: model }),
        signal: ctrl.signal,
      })

      if (!res.body) throw new Error('No stream')
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let sources: Source[] = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        const lines = text.split('\n').filter(l => l.startsWith('data: '))
        for (const line of lines) {
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'token') {
              setMessages(prev => prev.map(m =>
                m.id === assistantId ? { ...m, content: m.content + event.content } : m
              ))
            } else if (event.type === 'sources') {
              sources = event.content
            } else if (event.type === 'done') {
              setMessages(prev => prev.map(m =>
                m.id === assistantId ? { ...m, isStreaming: false, sources } : m
              ))
            }
          } catch {}
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: 'Error: Failed to get response.', isStreaming: false } : m
        ))
      }
    } finally {
      setIsStreaming(false)
    }
  }, [input, currentConvId, isStreaming, model])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const toggleSources = (msgId: string) => {
    setExpandedSources(prev => {
      const next = new Set(prev)
      next.has(msgId) ? next.delete(msgId) : next.add(msgId)
      return next
    })
  }

  return (
    <div className="flex h-full gap-0 -m-6">
      {/* Conversation Sidebar */}
      <div className="w-64 flex-shrink-0 border-r border-slate-800 bg-slate-950/50 flex flex-col h-full overflow-hidden">
        <div className="p-4 border-b border-slate-800">
          <button
            onClick={startNewChat}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all shadow-lg shadow-indigo-600/30"
          >
            <Plus className="w-4 h-4" /> New Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {conversations.length === 0 && (
            <div className="text-center text-slate-500 text-sm py-8">No conversations yet</div>
          )}
          {conversations.map(conv => (
            <button
              key={conv.id}
              onClick={() => setCurrentConvId(conv.id)}
              className={cn(
                'w-full text-left px-3 py-2 rounded-lg text-sm transition-all truncate',
                currentConvId === conv.id
                  ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/20'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              )}
            >
              <div className="flex items-center gap-2">
                <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{conv.title || 'Untitled'}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full px-6 py-12">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center mb-6">
                <Brain className="w-8 h-8 text-indigo-400" />
              </div>
              <h2 className="text-2xl font-bold text-white mb-2">How can I help?</h2>
              <p className="text-slate-400 text-sm mb-8 text-center max-w-md">
                Ask questions about your documents. I'll search through all your organization's knowledge and provide answers with source citations.
              </p>
              <div className="grid grid-cols-2 gap-3 max-w-xl w-full">
                {SUGGESTED.map(q => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="text-left px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700 text-slate-300 hover:text-white hover:border-indigo-500/50 hover:bg-slate-800 transition-all text-sm"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
              {messages.map((msg, i) => (
                <div key={msg.id} className={cn('flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0 mt-1">
                      <Brain className="w-4 h-4 text-indigo-400" />
                    </div>
                  )}
                  <div className={cn('max-w-2xl', msg.role === 'user' ? 'max-w-lg' : '')}>
                    <div className={cn(
                      'px-4 py-3 rounded-2xl text-sm leading-relaxed',
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-tr-sm'
                        : 'bg-slate-800/60 border border-slate-700 text-slate-200 rounded-tl-sm'
                    )}>
                      {msg.role === 'assistant' ? (
                        <div className="prose prose-invert prose-sm max-w-none">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                          {msg.isStreaming && (
                            <span className="inline-flex gap-1 ml-1">
                              {[0, 1, 2].map(d => (
                                <motion.span
                                  key={d}
                                  className="w-1 h-1 rounded-full bg-indigo-400 inline-block"
                                  animate={{ opacity: [0.3, 1, 0.3] }}
                                  transition={{ duration: 1, repeat: Infinity, delay: d * 0.2 }}
                                />
                              ))}
                            </span>
                          )}
                        </div>
                      ) : msg.content}
                    </div>

                    {/* Sources */}
                    {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && !msg.isStreaming && (
                      <div className="mt-2">
                        <button
                          onClick={() => toggleSources(msg.id)}
                          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors px-1"
                        >
                          {expandedSources.has(msg.id) ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          <FileText className="w-3 h-3" />
                          {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                        </button>
                        <AnimatePresence>
                          {expandedSources.has(msg.id) && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: 'auto' }}
                              exit={{ opacity: 0, height: 0 }}
                              className="mt-2 space-y-2 overflow-hidden"
                            >
                              {msg.sources.map(src => (
                                <div key={src.citation_number} className="p-3 rounded-lg bg-slate-900/80 border border-slate-700/50 text-xs">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <span className="w-5 h-5 rounded bg-indigo-500/20 text-indigo-400 text-xs flex items-center justify-center font-bold flex-shrink-0">
                                      {src.citation_number}
                                    </span>
                                    <span className="text-slate-300 font-medium truncate">{src.doc_filename}</span>
                                    {src.page_number && <span className="text-slate-500 flex-shrink-0">p.{src.page_number}</span>}
                                  </div>
                                  <p className="text-slate-400 line-clamp-2">{src.excerpt}</p>
                                </div>
                              ))}
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    )}

                    {/* Feedback */}
                    {msg.role === 'assistant' && !msg.isStreaming && (
                      <div className="flex items-center gap-2 mt-2 px-1">
                        <button className="p-1 text-slate-600 hover:text-emerald-400 transition-colors"><ThumbsUp className="w-3.5 h-3.5" /></button>
                        <button className="p-1 text-slate-600 hover:text-red-400 transition-colors"><ThumbsDown className="w-3.5 h-3.5" /></button>
                        {i === messages.length - 1 && (
                          <button className="p-1 text-slate-600 hover:text-indigo-400 transition-colors ml-1"><RotateCcw className="w-3.5 h-3.5" /></button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="border-t border-slate-800 bg-slate-950/50 p-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-3 p-3 rounded-2xl bg-slate-800/60 border border-slate-700 focus-within:border-indigo-500/50 transition-all">
              <button className="p-1.5 text-slate-500 hover:text-slate-300 transition-colors flex-shrink-0 mb-0.5">
                <Paperclip className="w-4 h-4" />
              </button>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => { setInput(e.target.value); adjustTextarea() }}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about your documents..."
                rows={1}
                className="flex-1 bg-transparent text-white placeholder-slate-500 text-sm resize-none focus:outline-none min-h-[24px] max-h-[200px] py-0.5"
              />
              <div className="flex items-center gap-2 flex-shrink-0 mb-0.5">
                <select
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  className="text-xs bg-slate-700 border border-slate-600 text-slate-300 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="openai">GPT-4o</option>
                  <option value="anthropic">Claude 3.5</option>
                  <option value="azure">Azure GPT-4o</option>
                  <option value="ollama">Ollama</option>
                </select>
                <button
                  onClick={() => sendMessage()}
                  disabled={!input.trim() || isStreaming}
                  className="w-8 h-8 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center justify-center transition-all shadow-lg shadow-indigo-600/30"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
            <p className="text-center text-xs text-slate-600 mt-2">
              RAG answers from your organization's documents · Sources cited
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Plus, MessageSquare, ThumbsUp, ThumbsDown, RotateCcw,
  ChevronDown, ChevronRight, FileText, Paperclip, Brain, X,
  Database, CheckCircle, Loader2, AlertCircle, Trash2, Upload
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import {
  useAppStore, ragSearch, formatAnswer, buildChunks,
  relativeTime, RagConversation, RagMessage, RagSource, RagDocument
} from '@/lib/store'
import Link from 'next/link'

// ─── Inline-attached file (not yet indexed) ──────────────────────────────────
interface AttachedFile {
  name: string
  content: string
  size: string
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { state, dispatch } = useAppStore()
  const { documents, conversations, settings } = state

  const [currentConvId, setCurrentConvId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const [showDocs, setShowDocs] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const currentConv = conversations.find(c => c.id === currentConvId) ?? null
  const messages = currentConv?.messages ?? []
  const indexedDocs = documents.filter(d => d.status === 'indexed')

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const adjustTextarea = () => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }

  // ── New conversation ────────────────────────────────────────────────────────
  const startNewConv = useCallback(() => {
    const id = crypto.randomUUID()
    const conv: RagConversation = {
      id, title: 'New Chat', messages: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    dispatch({ type: 'ADD_CONV', conv })
    setCurrentConvId(id)
    setAttachedFiles([])
  }, [dispatch])

  // ── Stream text ────────────────────────────────────────────────────────────
  const streamText = useCallback(async (
    convId: string,
    msgId: string,
    text: string,
    sources: RagSource[]
  ) => {
    let acc = ''
    for (const ch of text) {
      await new Promise(r => setTimeout(r, 4 + Math.random() * 6))
      acc += ch
      dispatch({ type: 'UPDATE_MSG', convId, msgId, patch: { content: acc } })
    }
    dispatch({ type: 'UPDATE_MSG', convId, msgId, patch: { content: text, isStreaming: false, sources } })
    setIsStreaming(false)
  }, [dispatch])

  // ── Send message ────────────────────────────────────────────────────────────
  const sendMessage = useCallback(async (overrideText?: string) => {
    const content = (overrideText ?? input).trim()
    if ((!content && attachedFiles.length === 0) || isStreaming) return

    const t0 = Date.now()

    // Get or create conversation
    let convId = currentConvId
    if (!convId) {
      const id = crypto.randomUUID()
      const title = (content || attachedFiles[0]?.name || 'New Chat').slice(0, 60)
      const conv: RagConversation = {
        id, title, messages: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
      dispatch({ type: 'ADD_CONV', conv })
      convId = id
      setCurrentConvId(id)
    } else if (currentConv?.title === 'New Chat' && content) {
      dispatch({ type: 'UPDATE_CONV', id: convId, patch: { title: content.slice(0, 60) } })
    }

    // Build temporary docs from attached files
    const inlineDocs: RagDocument[] = attachedFiles
      .filter(f => f.content)
      .map(f => ({
        id: 'inline_' + f.name,
        name: f.name,
        fileType: 'TXT',
        mimeType: 'text/plain',
        size: f.size,
        sizeBytes: f.content.length,
        status: 'indexed' as const,
        pages: 1,
        department: 'Inline',
        uploadedAt: new Date().toISOString(),
        content: f.content,
        chunks: buildChunks(f.content, settings.chunkSize),
        canQuery: true,
      }))

    const allDocs = [...indexedDocs, ...inlineDocs]

    const userMsgId = crypto.randomUUID()
    const userMsg: RagMessage = {
      id: userMsgId,
      role: 'user',
      content: content || `📎 ${attachedFiles.map(f => f.name).join(', ')}`,
      sources: [],
      timestamp: new Date().toISOString(),
    }

    // Reset input
    const filesForThisMsg = [...attachedFiles]
    setInput('')
    setAttachedFiles([])
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    // Add user message and placeholder assistant message via atomic actions
    dispatch({ type: 'APPEND_MSG', convId, msg: userMsg })

    const assistantId = crypto.randomUUID()
    const placeholder: RagMessage = {
      id: assistantId, role: 'assistant', content: '', sources: [], isStreaming: true,
      timestamp: new Date().toISOString(),
    }
    dispatch({ type: 'APPEND_MSG', convId, msg: placeholder })
    setIsStreaming(true)

    // Small delay for realism
    await new Promise(r => setTimeout(r, 350))

    let responseText = ''
    let sources: RagSource[] = []

    if (allDocs.length === 0) {
      responseText = [
        '## Knowledge Base Empty',
        '',
        'Your knowledge base has no indexed documents yet.',
        '',
        'To get started:',
        '1. Go to the **Documents** page',
        '2. Upload your files (PDF, DOCX, TXT, CSV, Markdown…)',
        '3. Wait for indexing to complete',
        '4. Come back and ask your question',
        '',
        'Or **attach a text file directly** using the 📎 button below — it\'ll be searched inline without permanent indexing.',
      ].join('\n')
    } else if (!content) {
      responseText = `You attached: ${filesForThisMsg.map(f => `\`${f.name}\``).join(', ')}. What would you like to know about ${filesForThisMsg.length === 1 ? 'it' : 'them'}?`
    } else {
      const hits = ragSearch(content, allDocs, settings.topK)

      if (hits.length === 0) {
        responseText = [
          `## No Results Found`,
          '',
          `I searched **${allDocs.length} document${allDocs.length > 1 ? 's' : ''}** but found no relevant content for:`,
          `> *"${content}"*`,
          '',
          '**Indexed documents:**',
          allDocs.map(d => `- \`${d.name}\` (${d.department})`).join('\n'),
          '',
          '**Try:**',
          '- Rephrasing your question with different keywords',
          '- Uploading a document that covers this topic',
        ].join('\n')
      } else {
        responseText = formatAnswer(content, hits, allDocs)
        sources = hits.map((h, i) => ({
          docId: h.docId,
          docName: h.docName,
          excerpt: h.chunk.slice(0, 200) + (h.chunk.length > 200 ? '…' : ''),
          score: Math.round(h.score * 100) / 100,
        }))
      }

      // Log query
      const responseMs = Date.now() - t0
      dispatch({
        type: 'LOG_QUERY',
        log: {
          id: crypto.randomUUID(),
          query: content,
          userName: (() => { try { return JSON.parse(localStorage.getItem('rag_user') ?? '{}').name ?? 'User' } catch { return 'User' } })(),
          docsSearched: allDocs.length,
          responseMs,
          found: hits.length > 0,
          timestamp: new Date().toISOString(),
        }
      })
    }

    // Stream it
    await streamText(convId, assistantId, responseText, sources)
  }, [input, currentConvId, currentConv, isStreaming, attachedFiles, indexedDocs, settings, dispatch, state.conversations, streamText, buildChunks])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  const handleFileAttach = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    files.forEach(file => {
      const size = file.size >= 1024 * 1024
        ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
        : `${(file.size / 1024).toFixed(0)} KB`
      const isText = /\.(txt|md|csv|json|html|log|yaml|yml|py|js|ts|sql)$/i.test(file.name)
      if (isText) {
        const reader = new FileReader()
        reader.onload = ev => {
          setAttachedFiles(prev => [...prev, {
            name: file.name, content: (ev.target?.result as string) ?? '', size
          }])
        }
        reader.readAsText(file)
      } else {
        setAttachedFiles(prev => [...prev, { name: file.name, content: '', size }])
      }
    })
    e.target.value = ''
  }

  const deleteConv = (id: string) => {
    dispatch({ type: 'DELETE_CONV', id })
    if (currentConvId === id) setCurrentConvId(null)
  }

  // Re-read messages fresh from store every render (streaming updates store)
  const liveMessages = state.conversations.find(c => c.id === currentConvId)?.messages ?? []

  return (
    <div className="flex h-full gap-0 -m-6">

      {/* ── Sidebar ── */}
      <div className="w-60 flex-shrink-0 border-r border-slate-800 bg-slate-950/60 flex flex-col h-full">
        <div className="p-3 border-b border-slate-800 space-y-2">
          <button onClick={startNewConv}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition-all shadow-lg shadow-indigo-600/20">
            <Plus className="w-4 h-4" /> New Chat
          </button>

          {/* KB indicator */}
          <button onClick={() => setShowDocs(v => !v)}
            className={cn(
              'w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium border transition-all',
              indexedDocs.length > 0
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/15'
                : 'bg-slate-800/50 border-slate-700 text-slate-500 hover:text-white'
            )}>
            <Database className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="flex-1 text-left">
              {indexedDocs.length > 0 ? `${indexedDocs.length} docs indexed` : 'No docs yet'}
            </span>
            <ChevronDown className={cn('w-3 h-3 transition-transform', showDocs && 'rotate-180')} />
          </button>
        </div>

        {/* Doc list */}
        <AnimatePresence>
          {showDocs && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-b border-slate-800">
              <div className="p-2 max-h-44 overflow-y-auto space-y-1">
                {documents.length === 0 ? (
                  <p className="text-xs text-slate-600 text-center py-3">No documents uploaded</p>
                ) : (
                  documents.map(doc => (
                    <div key={doc.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs">
                      {doc.status === 'indexed' && <CheckCircle className="w-3 h-3 text-emerald-400 flex-shrink-0" />}
                      {doc.status === 'processing' && <Loader2 className="w-3 h-3 text-amber-400 animate-spin flex-shrink-0" />}
                      {doc.status === 'uploading' && <Loader2 className="w-3 h-3 text-indigo-400 animate-spin flex-shrink-0" />}
                      {doc.status === 'error' && <AlertCircle className="w-3 h-3 text-red-400 flex-shrink-0" />}
                      <span className={cn('truncate', doc.status === 'indexed' ? 'text-slate-300' : 'text-slate-600')}>
                        {doc.name}
                      </span>
                    </div>
                  ))
                )}
                {indexedDocs.length === 0 && documents.length > 0 && (
                  <p className="text-xs text-amber-500 text-center py-1">Documents still indexing…</p>
                )}
              </div>
              {indexedDocs.length === 0 && (
                <Link href="/documents" className="block px-3 py-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors border-t border-slate-800 text-center">
                  → Upload documents
                </Link>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 ? (
            <div className="text-center text-slate-600 text-xs py-8">
              <MessageSquare className="w-6 h-6 mx-auto mb-2 opacity-30" />
              No conversations yet
            </div>
          ) : (
            conversations.map(conv => (
              <div key={conv.id}
                className={cn('group flex items-center gap-1 rounded-lg transition-all',
                  currentConvId === conv.id ? 'bg-indigo-500/15 border border-indigo-500/20' : 'hover:bg-slate-800'
                )}>
                <button
                  onClick={() => setCurrentConvId(conv.id)}
                  className="flex-1 flex items-center gap-2 px-3 py-2 text-sm text-left min-w-0">
                  <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-50" />
                  <span className={cn('truncate text-xs', currentConvId === conv.id ? 'text-indigo-300' : 'text-slate-400 group-hover:text-white')}>
                    {conv.title}
                  </span>
                </button>
                <button onClick={() => deleteConv(conv.id)}
                  className="p-1.5 mr-1 text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto">

          {/* ── Welcome screen ── */}
          {liveMessages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full px-6 py-10 text-center">
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5, type: 'spring' }}
                className="w-20 h-20 rounded-2xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center mb-6 shadow-2xl shadow-indigo-500/20"
              >
                <Brain className="w-10 h-10 text-indigo-400" />
              </motion.div>

              <motion.h2 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
                className="text-3xl font-bold text-white mb-3">
                Enterprise RAG Assistant
              </motion.h2>

              <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
                className="text-slate-400 text-sm max-w-md mb-2">
                Ask questions about your uploaded documents. I search your knowledge base and return answers with source citations.
              </motion.p>

              {indexedDocs.length > 0 ? (
                <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}
                  className="text-xs text-emerald-400 mb-10 font-medium">
                  ✓ {indexedDocs.length} document{indexedDocs.length !== 1 ? 's' : ''} ready in your knowledge base
                </motion.p>
              ) : (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}
                  className="mb-10">
                  <Link href="/documents"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 hover:bg-indigo-600/30 text-sm font-medium transition-all mt-2">
                    <Upload className="w-4 h-4" /> Upload documents to get started
                  </Link>
                </motion.div>
              )}

              {indexedDocs.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
                  className="text-xs text-slate-600 mb-6">
                  Indexed: {indexedDocs.map(d => d.name).slice(0, 3).join(', ')}{indexedDocs.length > 3 ? ` +${indexedDocs.length - 3} more` : ''}
                </motion.div>
              )}
            </div>
          )}

          {/* ── Messages ── */}
          {liveMessages.length > 0 && (
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
              {liveMessages.map((msg, idx) => (
                <motion.div key={msg.id}
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  className={cn('flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start')}>

                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0 mt-1">
                      <Brain className="w-4 h-4 text-indigo-400" />
                    </div>
                  )}

                  <div className={cn('max-w-2xl min-w-0', msg.role === 'user' ? 'max-w-lg' : '')}>
                    <div className={cn('px-4 py-3 rounded-2xl text-sm leading-relaxed',
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-tr-sm'
                        : 'bg-slate-800/70 border border-slate-700/60 text-slate-200 rounded-tl-sm'
                    )}>
                      {msg.role === 'assistant' ? (
                        <div className="prose prose-invert prose-sm max-w-none">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                          {msg.isStreaming && (
                            <span className="inline-flex gap-1 ml-1 align-middle">
                              {[0, 1, 2].map(d => (
                                <motion.span key={d}
                                  className="w-1.5 h-1.5 rounded-full bg-indigo-400 inline-block"
                                  animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
                                  transition={{ duration: 0.9, repeat: Infinity, delay: d * 0.2 }}
                                />
                              ))}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span>{msg.content}</span>
                      )}
                    </div>

                    {/* Sources */}
                    {msg.role === 'assistant' && msg.sources.length > 0 && !msg.isStreaming && (
                      <div className="mt-2">
                        <button onClick={() => setExpandedSources(prev => {
                          const n = new Set(prev); n.has(msg.id) ? n.delete(msg.id) : n.add(msg.id); return n
                        })} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors px-1">
                          {expandedSources.has(msg.id)
                            ? <ChevronDown className="w-3 h-3" />
                            : <ChevronRight className="w-3 h-3" />}
                          <FileText className="w-3 h-3" />
                          {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                        </button>
                        <AnimatePresence>
                          {expandedSources.has(msg.id) && (
                            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                              className="mt-2 space-y-2 overflow-hidden">
                              {msg.sources.map((src, si) => (
                                <div key={si} className="p-3 rounded-xl bg-slate-900/80 border border-slate-700/40 text-xs">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <span className="w-5 h-5 rounded bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold flex-shrink-0 text-[10px]">{si + 1}</span>
                                    <span className="text-slate-300 font-medium truncate flex-1">{src.docName}</span>
                                    <span className="text-emerald-400 flex-shrink-0 text-[10px] font-semibold">
                                      {Math.min(99, Math.round(src.score * 30 + 65))}% match
                                    </span>
                                  </div>
                                  <p className="text-slate-400 line-clamp-2 leading-relaxed">{src.excerpt}</p>
                                </div>
                              ))}
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    )}

                    {/* Actions */}
                    {msg.role === 'assistant' && !msg.isStreaming && (
                      <div className="flex items-center gap-1 mt-1.5 px-1">
                        <button className="p-1 text-slate-700 hover:text-emerald-400 transition-colors" title="Helpful">
                          <ThumbsUp className="w-3.5 h-3.5" />
                        </button>
                        <button className="p-1 text-slate-700 hover:text-red-400 transition-colors" title="Not helpful">
                          <ThumbsDown className="w-3.5 h-3.5" />
                        </button>
                        {idx === liveMessages.length - 1 && (
                          <button title="Regenerate" className="p-1 text-slate-700 hover:text-indigo-400 transition-colors ml-1"
                            onClick={() => {
                              const lastUser = [...liveMessages].reverse().find(m => m.role === 'user')
                              if (!lastUser || !currentConvId) return
                              dispatch({
                                type: 'UPDATE_CONV', id: currentConvId,
                                patch: { messages: liveMessages.slice(0, -1) }
                              })
                              setTimeout(() => sendMessage(lastUser.content), 100)
                            }}>
                            <RotateCcw className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ── Input bar ── */}
        <div className="border-t border-slate-800 bg-slate-950/60 p-4">
          <div className="max-w-3xl mx-auto">
            {/* Attached files */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {attachedFiles.map((f, i) => (
                  <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-500/15 border border-indigo-500/20 text-indigo-300 text-xs">
                    <FileText className="w-3 h-3" />
                    {f.name}
                    {f.content && <span className="text-emerald-400">✓</span>}
                    <button onClick={() => setAttachedFiles(prev => prev.filter((_, j) => j !== i))}
                      className="ml-0.5 hover:text-white transition-colors"><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            )}

            <div className="flex items-end gap-2 p-3 rounded-2xl bg-slate-800/70 border border-slate-700 focus-within:border-indigo-500/60 transition-all">
              <button onClick={() => fileInputRef.current?.click()}
                title="Attach text file for inline search"
                className="p-1.5 text-slate-500 hover:text-indigo-400 transition-colors flex-shrink-0 mb-0.5">
                <Paperclip className="w-4 h-4" />
              </button>
              <input ref={fileInputRef} type="file" multiple
                accept=".txt,.md,.csv,.json,.html,.log,.yaml,.yml,.py,.js,.ts,.sql"
                className="hidden" onChange={handleFileAttach} />

              <textarea ref={textareaRef} value={input}
                onChange={e => { setInput(e.target.value); adjustTextarea() }}
                onKeyDown={handleKeyDown}
                placeholder={
                  indexedDocs.length > 0
                    ? `Ask anything about your ${indexedDocs.length} document${indexedDocs.length !== 1 ? 's' : ''}…`
                    : 'Upload documents first, or attach a text file with 📎…'
                }
                rows={1}
                className="flex-1 bg-transparent text-white placeholder-slate-600 text-sm resize-none focus:outline-none min-h-[24px] max-h-[200px] py-0.5" />

              <div className="flex items-center gap-2 flex-shrink-0 mb-0.5">
                <span className="hidden sm:block text-xs text-slate-600 font-mono bg-slate-900/60 px-2 py-1 rounded-lg border border-slate-800">
                  {settings.model}
                </span>
                <button onClick={() => sendMessage()}
                  disabled={(!input.trim() && attachedFiles.length === 0) || isStreaming}
                  className="w-8 h-8 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed text-white flex items-center justify-center transition-all shadow-lg shadow-indigo-600/30">
                  {isStreaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <p className="text-center text-xs text-slate-700 mt-2">
              {indexedDocs.length > 0
                ? `Searching ${indexedDocs.length} indexed document${indexedDocs.length !== 1 ? 's' : ''} · Sources cited per answer`
                : 'No documents indexed · Upload files in the Documents page'
              }
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

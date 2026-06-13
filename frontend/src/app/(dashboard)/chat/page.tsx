'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Plus, MessageSquare, ThumbsUp, ThumbsDown, RotateCcw, ChevronDown, ChevronRight, FileText, Paperclip, Brain, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

interface Source {
  citation_number: number
  doc_filename: string
  page_number: number | null
  excerpt: string
  relevance_score: number
}

interface AttachedFile {
  name: string
  type: string
  content: string
  size: string
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  isStreaming?: boolean
  attachments?: string[]
}

interface Conversation {
  id: string
  title: string
  messages: Message[]
}

const SUGGESTED = [
  'What is our vacation policy?',
  'Summarize the Q3 financial report',
  'What are the GDPR compliance requirements?',
  'Explain the employee onboarding process',
]

// ── Response helpers ────────────────────────────────────────────────────────

function getFileResponse(query: string, file: AttachedFile): { content: string; sources: Source[] } {
  const fname = file.name
  const hasText = file.content.length > 50

  if (hasText) {
    const preview = file.content.slice(0, 600).replace(/\n{3,}/g, '\n\n').trim()
    const words = file.content.split(/\s+/).length
    const lines = file.content.split('\n').length
    const docType = /report|analysis/i.test(fname) ? 'analytical report'
      : /policy|handbook/i.test(fname) ? 'policy document'
      : /contract|agreement/i.test(fname) ? 'legal/contractual document'
      : 'reference document'

    return {
      content: [
        `## Analysis of \`${fname}\``,
        '',
        `**Document stats:** ${words.toLocaleString()} words · ${lines} lines · ${file.size}`,
        `**Document type:** ${docType}`,
        '',
        '**Content preview:**',
        '```',
        preview,
        file.content.length > 600 ? '\n… [document continues]' : '',
        '```',
        '',
        query
          ? `**Your question:** *"${query}"*\n\nBased on the content above, the document ${words > 300 ? 'contains detailed information that addresses your query. Key sections are highlighted in the preview above.' : 'is concise — the full content is shown above.'}`
          : '**Ask me anything about this document** and I will answer based on its content.',
        '',
        '> 💡 *Connect the backend for full semantic search & precise RAG answers.*',
      ].join('\n'),
      sources: [{
        citation_number: 1,
        doc_filename: fname,
        page_number: 1,
        excerpt: preview.slice(0, 200),
        relevance_score: 0.93,
      }],
    }
  }

  // Binary file (PDF/DOCX) — filename-based simulation
  const docType = /report|analysis/i.test(fname) ? 'a report or analysis document'
    : /policy|handbook/i.test(fname) ? 'a policy or handbook'
    : /contract|agreement/i.test(fname) ? 'a legal or contractual document'
    : /invoice|receipt|financial/i.test(fname) ? 'a financial document'
    : 'a business document'

  return {
    content: [
      `## Document Indexed: \`${fname}\``,
      '',
      `✅ Your file (${file.size}) has been received and simulated-indexed.`,
      '',
      `**Detected type:** ${docType}`,
      '',
      query
        ? [
            `**Your question:** *"${query}"*`,
            '',
            'In the full production system, I would:',
            `1. Extract text from \`${fname}\` using OCR / parser`,
            '2. Chunk it into semantic segments',
            '3. Embed each chunk with OpenAI embeddings',
            '4. Run vector similarity search for your query',
            '5. Generate a grounded answer with page-level citations',
            '',
            '> 💡 *Run `docker compose up` to start the backend and get real answers.*',
          ].join('\n')
        : '**What would you like to know?** Ask me a question about this document.',
    ].join('\n'),
    sources: [{
      citation_number: 1,
      doc_filename: fname,
      page_number: null,
      excerpt: `Uploaded file: ${fname} (${file.size})`,
      relevance_score: 0.85,
    }],
  }
}

function getKeywordResponse(query: string): { content: string; sources: Source[] } {
  const q = query.toLowerCase()

  if (q.includes('vacation') || q.includes('leave') || q.includes('pto')) {
    return {
      content: `## Vacation Policy\n\nAccording to your **Employee Handbook 2024**:\n\n| Employment Duration | Annual PTO |\n|---|---|\n| 0–1 year | 10 days |\n| 1–3 years | 15 days |\n| 3–5 years | 18 days |\n| 5+ years | 22 days |\n\n**Key rules:**\n- Carry-over max: 5 days\n- Submit requests ≥ 2 weeks ahead\n- Emergency leave handled separately\n- Remote employees follow the same policy`,
      sources: [
        { citation_number: 1, doc_filename: 'Employee-Handbook-2024.docx', page_number: 24, excerpt: 'Full-time employees accrue paid time off based on their years of service.', relevance_score: 0.97 },
        { citation_number: 2, doc_filename: 'HR-Policy-Manual.pdf', page_number: 15, excerpt: 'PTO requests must be approved by the direct manager no less than two weeks prior.', relevance_score: 0.89 },
      ],
    }
  }

  if (q.includes('gdpr') || q.includes('compliance') || q.includes('data protection')) {
    return {
      content: `## GDPR Compliance Requirements\n\n### Core Principles\n1. **Lawfulness** — Process data lawfully and transparently\n2. **Purpose Limitation** — Collect for specified, legitimate purposes\n3. **Data Minimization** — Only collect what's necessary\n4. **Accuracy** — Keep data accurate and current\n5. **Storage Limitation** — Retain only as long as needed\n6. **Integrity & Confidentiality** — Apply appropriate security\n\n### Employee Obligations\n- ✅ Complete annual GDPR training\n- ⚠️ Report breaches within **72 hours**\n- 🔒 Use encrypted channels for sensitive data`,
      sources: [
        { citation_number: 1, doc_filename: 'GDPR-Compliance-Policy.pdf', page_number: 3, excerpt: 'All employees must complete mandatory annual training and adhere to the six core GDPR principles.', relevance_score: 0.96 },
        { citation_number: 2, doc_filename: 'Security-Audit-Report-2024.pdf', page_number: 18, excerpt: 'Breaches must be reported to the DPO within 72 hours per GDPR Article 33.', relevance_score: 0.88 },
      ],
    }
  }

  if (q.includes('financial') || q.includes('q3') || q.includes('revenue') || q.includes('report')) {
    return {
      content: `## Q3 2024 Financial Highlights\n\n| Metric | Value | YoY |\n|---|---|---|\n| Total Revenue | $48.2M | +18% |\n| ARR | $41.6M | +22% |\n| Gross Margin | 74.3% | +3.1pp |\n| NRR | 118% | — |\n\n**Q4 guidance:** $51–53M revenue at ~74% gross margin.\n\nFocus areas: enterprise expansion, EMEA penetration.`,
      sources: [
        { citation_number: 1, doc_filename: 'Q3-2024-Financial-Report.pdf', page_number: 4, excerpt: 'Total revenue reached $48.2M, an 18% year-over-year increase.', relevance_score: 0.98 },
        { citation_number: 2, doc_filename: 'Q3-2024-Financial-Report.pdf', page_number: 9, excerpt: 'Net Revenue Retention of 118% reflects strong expansion from enterprise customers.', relevance_score: 0.91 },
      ],
    }
  }

  if (q.includes('onboarding') || q.includes('new employee') || q.includes('joining')) {
    return {
      content: `## Employee Onboarding — 90-Day Plan\n\n**Week 1:** IT setup, HR docs, company culture intro, meet your buddy\n\n**Weeks 2–4:** Dept training, shadow team, compliance training (GDPR, Security), first 1:1 with manager\n\n**Days 30–90:** Own first project, 30/60/90-day check-ins, performance expectations, feedback survey`,
      sources: [
        { citation_number: 1, doc_filename: 'Employee-Handbook-2024.docx', page_number: 8, excerpt: 'The 90-day onboarding program integrates new employees into their roles and company culture.', relevance_score: 0.95 },
      ],
    }
  }

  return {
    content: `Based on your organization's knowledge base:\n\n**Summary**\nThe relevant information has been retrieved from multiple indexed documents. Your query touches on topics covered across several policy documents.\n\n**Key Points**\n- Your organization follows industry-standard practices\n- Policies are reviewed annually\n- Refer to the HR portal for the most current versions\n\n> *Generated using RAG over your organization's indexed documents.*`,
    sources: [
      { citation_number: 1, doc_filename: 'Employee-Handbook-2024.docx', page_number: 12, excerpt: 'All employees are entitled to the benefits described herein.', relevance_score: 0.88 },
      { citation_number: 2, doc_filename: 'HR-Policy-Manual.pdf', page_number: 7, excerpt: 'Policies are reviewed annually by the HR leadership team.', relevance_score: 0.81 },
    ],
  }
}

// ── Component ───────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConvId, setCurrentConvId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [model, setModel] = useState('openai')
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  const startNewChat = useCallback(() => {
    const id = Date.now().toString()
    setConversations(prev => [{ id, title: 'New Chat', messages: [] }, ...prev])
    setCurrentConvId(id)
    setMessages([])
    setAttachedFiles([])
  }, [])

  const streamResponse = useCallback(async (assistantId: string, mockResp: { content: string; sources: Source[] }) => {
    const chars = mockResp.content.split('')
    let accumulated = ''
    for (const ch of chars) {
      await new Promise(r => setTimeout(r, 6 + Math.random() * 6))
      accumulated += ch
      const snap = accumulated
      setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: snap } : m))
    }
    await new Promise(r => setTimeout(r, 200))
    setMessages(prev => prev.map(m =>
      m.id === assistantId ? { ...m, isStreaming: false, sources: mockResp.sources } : m
    ))
    setIsStreaming(false)
  }, [])

  const sendMessage = useCallback(async (text?: string) => {
    const content = (text ?? input).trim()
    if ((!content && attachedFiles.length === 0) || isStreaming) return

    let convId = currentConvId
    if (!convId) {
      const id = Date.now().toString()
      const title = content.slice(0, 50) || attachedFiles[0]?.name || 'New Chat'
      setConversations(prev => [{ id, title, messages: [] }, ...prev])
      setCurrentConvId(id)
      convId = id
    } else {
      setConversations(prev => prev.map(c =>
        c.id === convId && c.title === 'New Chat'
          ? { ...c, title: (content || attachedFiles[0]?.name || 'New Chat').slice(0, 50) }
          : c
      ))
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: content || `Uploaded: ${attachedFiles.map(f => f.name).join(', ')}`,
      attachments: attachedFiles.length > 0 ? attachedFiles.map(f => f.name) : undefined,
    }
    const currentFiles = [...attachedFiles]
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setAttachedFiles([])
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    const assistantId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', isStreaming: true }])
    setIsStreaming(true)

    // Pick response: file-aware or keyword-based
    const mockResp = currentFiles.length > 0
      ? getFileResponse(content, currentFiles[0])
      : getKeywordResponse(content)

    await streamResponse(assistantId, mockResp)
  }, [input, currentConvId, isStreaming, attachedFiles, streamResponse])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  const handleFileAttach = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    files.forEach(file => {
      const sizeStr = file.size >= 1024 * 1024
        ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
        : `${(file.size / 1024).toFixed(0)} KB`

      const isText = /\.(txt|md|csv|json|xml|html|htm|log|yaml|yml|ts|js|py)$/i.test(file.name)

      if (isText) {
        const reader = new FileReader()
        reader.onload = ev => {
          setAttachedFiles(prev => [...prev, {
            name: file.name,
            type: file.type,
            content: (ev.target?.result as string) || '',
            size: sizeStr,
          }])
        }
        reader.readAsText(file)
      } else {
        // Binary (PDF/DOCX etc.) — store without content
        setAttachedFiles(prev => [...prev, {
          name: file.name,
          type: file.type,
          content: '',
          size: sizeStr,
        }])
      }
    })
    e.target.value = ''
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
      {/* Sidebar */}
      <div className="w-64 flex-shrink-0 border-r border-slate-800 bg-slate-950/50 flex flex-col h-full overflow-hidden">
        <div className="p-4 border-b border-slate-800">
          <button onClick={startNewChat}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all shadow-lg shadow-indigo-600/30">
            <Plus className="w-4 h-4" /> New Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {conversations.length === 0 && (
            <div className="text-center text-slate-500 text-sm py-8">No conversations yet</div>
          )}
          {conversations.map(conv => (
            <button key={conv.id}
              onClick={() => { setCurrentConvId(conv.id); setMessages(conv.messages) }}
              className={cn('w-full text-left px-3 py-2 rounded-lg text-sm transition-all',
                currentConvId === conv.id
                  ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/20'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              )}>
              <div className="flex items-center gap-2">
                <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                <span className="truncate">{conv.title}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main Chat */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full px-6 py-12">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center mb-6">
                <Brain className="w-8 h-8 text-indigo-400" />
              </div>
              <h2 className="text-2xl font-bold text-white mb-2">How can I help?</h2>
              <p className="text-slate-400 text-sm mb-8 text-center max-w-md">
                Ask questions about your documents, or upload a file and ask questions about it.
              </p>
              <div className="grid grid-cols-2 gap-3 max-w-xl w-full">
                {SUGGESTED.map(q => (
                  <button key={q} onClick={() => sendMessage(q)}
                    className="text-left px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700 text-slate-300 hover:text-white hover:border-indigo-500/50 hover:bg-slate-800 transition-all text-sm">
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
                    {msg.attachments && msg.attachments.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2 justify-end">
                        {msg.attachments.map(name => (
                          <span key={name} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-500/20 border border-indigo-500/20 text-indigo-300 text-xs">
                            <FileText className="w-3 h-3" /> {name}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className={cn('px-4 py-3 rounded-2xl text-sm leading-relaxed',
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
                                <motion.span key={d}
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

                    {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && !msg.isStreaming && (
                      <div className="mt-2">
                        <button onClick={() => toggleSources(msg.id)}
                          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors px-1">
                          {expandedSources.has(msg.id) ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          <FileText className="w-3 h-3" />
                          {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                        </button>
                        <AnimatePresence>
                          {expandedSources.has(msg.id) && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                              className="mt-2 space-y-2 overflow-hidden">
                              {msg.sources.map(src => (
                                <div key={src.citation_number} className="p-3 rounded-lg bg-slate-900/80 border border-slate-700/50 text-xs">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <span className="w-5 h-5 rounded bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold flex-shrink-0">
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

                    {msg.role === 'assistant' && !msg.isStreaming && (
                      <div className="flex items-center gap-2 mt-2 px-1">
                        <button className="p-1 text-slate-600 hover:text-emerald-400 transition-colors"><ThumbsUp className="w-3.5 h-3.5" /></button>
                        <button className="p-1 text-slate-600 hover:text-red-400 transition-colors"><ThumbsDown className="w-3.5 h-3.5" /></button>
                        {i === messages.length - 1 && (
                          <button className="p-1 text-slate-600 hover:text-indigo-400 transition-colors ml-1"
                            onClick={() => {
                              const lastUser = [...messages].reverse().find(m => m.role === 'user')
                              if (lastUser) { setMessages(prev => prev.slice(0, -1)); setTimeout(() => sendMessage(lastUser.content), 50) }
                            }}>
                            <RotateCcw className="w-3.5 h-3.5" />
                          </button>
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

        {/* Input */}
        <div className="border-t border-slate-800 bg-slate-950/50 p-4">
          <div className="max-w-3xl mx-auto">
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {attachedFiles.map((f, i) => (
                  <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-500/20 border border-indigo-500/20 text-indigo-300 text-xs">
                    <FileText className="w-3 h-3" /> {f.name}
                    <span className="text-indigo-500 ml-1">{f.size}</span>
                    {f.content && <span className="text-emerald-400 ml-1">✓ readable</span>}
                    <button onClick={() => setAttachedFiles(prev => prev.filter((_, j) => j !== i))} className="ml-0.5 hover:text-white">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-end gap-3 p-3 rounded-2xl bg-slate-800/60 border border-slate-700 focus-within:border-indigo-500/50 transition-all">
              <button onClick={() => fileInputRef.current?.click()}
                className="p-1.5 text-slate-500 hover:text-indigo-400 transition-colors flex-shrink-0 mb-0.5" title="Attach file (PDF, DOCX, TXT, CSV…)">
                <Paperclip className="w-4 h-4" />
              </button>
              <input ref={fileInputRef} type="file" multiple
                accept=".pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.json,.html,.log"
                className="hidden" onChange={handleFileAttach} />
              <textarea ref={textareaRef} value={input}
                onChange={e => { setInput(e.target.value); adjustTextarea() }}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about your documents… or attach a file"
                rows={1}
                className="flex-1 bg-transparent text-white placeholder-slate-500 text-sm resize-none focus:outline-none min-h-[24px] max-h-[200px] py-0.5" />
              <div className="flex items-center gap-2 flex-shrink-0 mb-0.5">
                <select value={model} onChange={e => setModel(e.target.value)}
                  className="text-xs bg-slate-700 border border-slate-600 text-slate-300 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                  <option value="openai">GPT-4o</option>
                  <option value="anthropic">Claude 3.5</option>
                  <option value="azure">Azure GPT-4o</option>
                  <option value="ollama">Ollama</option>
                </select>
                <button onClick={() => sendMessage()}
                  disabled={(!input.trim() && attachedFiles.length === 0) || isStreaming}
                  className="w-8 h-8 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center justify-center transition-all shadow-lg shadow-indigo-600/30">
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

'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Plus, MessageSquare, ThumbsUp, ThumbsDown, RotateCcw,
  ChevronDown, ChevronRight, FileText, Paperclip, Brain, X,
  Database, CheckCircle, AlertCircle, Loader2
} from 'lucide-react'
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

interface IndexedDoc {
  id: number
  name: string
  type: string
  size: string
  status: string
  pages: number
  dept: string
  uploaded: string
  content?: string   // full text content if text-readable
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

// ── Knowledge base mock data matching Documents page ───────────────────────
const KNOWLEDGE_BASE: Record<string, { content: string; pages: number }> = {
  'Employee-Handbook-2024.docx': {
    pages: 124,
    content: `EMPLOYEE HANDBOOK 2024

VACATION & PTO POLICY
Full-time employees accrue paid time off based on years of service:
- 0-1 year: 10 days per year
- 1-3 years: 15 days per year  
- 3-5 years: 18 days per year
- 5+ years: 22 days per year
Carry-over maximum: 5 days. Submit requests at least 2 weeks in advance.
Emergency leave is handled separately by HR.

ONBOARDING PROCESS (90-Day Plan)
Week 1: IT setup, HR documentation, company culture orientation, buddy assignment
Weeks 2-4: Department training, shadow team members, compliance training (GDPR, Security), first 1:1 with manager
Days 30-90: Own first project, 30/60/90-day check-ins, performance expectations setting, feedback survey

CODE OF CONDUCT
All employees must uphold integrity, respect, and professionalism. Zero tolerance for harassment, discrimination, or retaliation. Report violations to HR or use the anonymous Ethics Hotline.

REMOTE WORK POLICY
Remote employees follow the same PTO policy as on-site staff. Core collaboration hours: 10am-3pm local time. Equipment provided by company for approved remote roles.

BENEFITS
- Health insurance (medical, dental, vision)
- 401(k) with 4% company match
- Annual learning budget: $2,000 per employee
- Monthly wellness stipend: $75`,
  },
  'GDPR-Compliance-Policy.pdf': {
    pages: 32,
    content: `GDPR COMPLIANCE POLICY

CORE PRINCIPLES (Article 5)
1. Lawfulness, fairness and transparency - process data lawfully and transparently
2. Purpose limitation - collect for specified, legitimate purposes only
3. Data minimisation - only collect what is strictly necessary
4. Accuracy - keep personal data accurate and up to date
5. Storage limitation - retain only as long as necessary
6. Integrity and confidentiality - apply appropriate technical and organisational security

EMPLOYEE OBLIGATIONS
- Complete mandatory annual GDPR training
- Report data breaches to DPO within 72 hours (GDPR Article 33)
- Use encrypted channels for transmitting sensitive personal data
- Do not share personal data with unauthorized third parties
- Complete Data Protection Impact Assessment (DPIA) for high-risk processing

DATA SUBJECT RIGHTS
- Right to access (respond within 30 days)
- Right to rectification
- Right to erasure ("right to be forgotten")
- Right to data portability
- Right to object to automated processing

BREACH RESPONSE PROCEDURE
1. Identify and contain the breach immediately
2. Assess the risk level (high/medium/low)
3. Notify DPO within 24 hours internally
4. Notify supervisory authority within 72 hours if high risk
5. Notify affected data subjects without undue delay if very high risk`,
  },
  'Q3-2024-Financial-Report.pdf': {
    pages: 48,
    content: `Q3 2024 FINANCIAL REPORT

EXECUTIVE SUMMARY
Strong performance in Q3 2024 driven by enterprise expansion and EMEA growth.

FINANCIAL HIGHLIGHTS
- Total Revenue: $48.2M (+18% YoY)
- Annual Recurring Revenue (ARR): $41.6M (+22% YoY)
- Gross Margin: 74.3% (+3.1 percentage points YoY)
- Net Revenue Retention (NRR): 118%
- Operating Cash Flow: $8.4M
- Headcount: 412 employees (+28 QoQ)

Q4 2024 GUIDANCE
Revenue: $51-53M
Gross Margin: ~74%
Focus areas: Enterprise tier expansion, EMEA penetration, new AI-powered features

DEPARTMENTAL BREAKDOWN
- Legal: $12.3M revenue (Documents: 1,240)
- Finance: $9.8M revenue  
- HR: $7.2M revenue
- Product: $11.4M revenue
- IT: $7.5M revenue

KEY METRICS
- Customer count: 847 (+62 QoQ)
- Average contract value: $49,200
- Sales cycle: 47 days avg
- Churn rate: 2.1% annual`,
  },
  'Security-Audit-Report-2024.pdf': {
    pages: 89,
    content: `SECURITY AUDIT REPORT 2024

EXECUTIVE SUMMARY
Annual security audit conducted by external firm CyberSec Partners. Overall security posture: STRONG. 3 medium findings, 0 critical findings.

FINDINGS & REMEDIATION
Medium Finding 1: Legacy API endpoints without rate limiting → Remediation: Implement rate limiting by Q4 2024 ✅ COMPLETED
Medium Finding 2: Some S3 buckets with broad access policies → Remediation: Apply least-privilege IAM policies ✅ COMPLETED  
Medium Finding 3: Missing MFA enforcement for admin accounts → Remediation: Enforce MFA via SSO/Keycloak ✅ COMPLETED

SECURITY CONTROLS IN PLACE
- OWASP Top 10 protections implemented
- JWT tokens with 15-minute expiry + refresh tokens
- AES-256 encryption at rest, TLS 1.3 in transit
- PII detection and automatic masking
- Prompt injection defense (for AI features)
- Rate limiting: per-user, per-org, per-IP
- File upload validation: type check, size limit, ClamAV virus scan

GDPR & COMPLIANCE
- Data breaches must be reported within 72 hours per GDPR Article 33
- Annual penetration testing conducted
- SOC 2 Type II audit in progress (expected Q1 2025)
- ISO 27001 certification target: Q2 2025`,
  },
  'Sales-Playbook-EMEA.docx': {
    pages: 56,
    content: `SALES PLAYBOOK - EMEA REGION

TARGET SEGMENTS
- Enterprise: 500+ employees, deal size $50K-500K ARR
- Mid-market: 100-500 employees, deal size $15K-50K ARR
- SMB: 10-100 employees, deal size $5K-15K ARR

QUALIFICATION CRITERIA (MEDDPIC)
M - Metrics: Can the prospect quantify the value? (time saved, cost reduced)
E - Economic Buyer: Is the CFO/CTO involved?
D - Decision Criteria: What does success look like to them?
D - Decision Process: Who else is involved in the purchase?
P - Paper Process: Legal/procurement timeline?
I - Implicate the Pain: What happens if they don't solve this problem?
C - Champion: Who will advocate for us internally?

COMPETITIVE POSITIONING
vs. Competitor A: We win on security (SOC 2, GDPR) and multi-tenancy
vs. Competitor B: We win on RAG quality and source citations
vs. In-house build: We win on time-to-value (weeks vs. 12-18 months)

PRICING
- Starter: $1,200/month (up to 50 users, 10GB docs)
- Growth: $4,800/month (up to 250 users, 100GB docs)
- Enterprise: Custom pricing, unlimited users and docs`,
  },
  'Vendor-Contracts-2024.pdf': {
    pages: 0,
    content: '',
  },
  'Product-Roadmap-H1-2025.pptx': {
    pages: 64,
    content: `PRODUCT ROADMAP H1 2025

Q1 2025 INITIATIVES
- AI-powered document summarization (auto-summary on upload)
- Multi-language support: Spanish, French, German, Japanese
- Advanced analytics dashboard for admins
- Microsoft Teams integration
- Slack bot for querying knowledge base

Q2 2025 INITIATIVES  
- Vision/OCR improvements: 40% accuracy increase for scanned PDFs
- API v2 with GraphQL support
- Knowledge graph builder (entity extraction)
- Custom embedding models (fine-tuned on customer data)
- SOC 2 Type II certification completion

KEY METRICS TARGETS H1 2025
- Query accuracy: 94% (up from 89%)
- P99 response latency: <2 seconds
- Document processing speed: 10x improvement via GPU optimization
- New customers: 150 net new logos
- NPS target: 52 (up from 47)`,
  },
}

// ── RAG-style answer engine ─────────────────────────────────────────────────

function ragAnswer(
  query: string,
  attachedFiles: AttachedFile[],
  indexedDocs: IndexedDoc[]
): { content: string; sources: Source[] } {
  const q = query.toLowerCase()

  // 1. If user attached a file inline in this message, answer from that file
  if (attachedFiles.length > 0) {
    const file = attachedFiles[0]
    if (file.content.length > 50) {
      const preview = file.content.slice(0, 800).replace(/\n{3,}/g, '\n\n').trim()
      return {
        content: [
          `## Analysis of \`${file.name}\``,
          '',
          `**Size:** ${file.size} · **Content:** ${file.content.split(/\s+/).length.toLocaleString()} words`,
          '',
          query ? `**Your question:** *"${query}"*\n` : '',
          '**Extracted content:**',
          '```',
          preview,
          file.content.length > 800 ? '\n… [document continues]' : '',
          '```',
          '',
          query
            ? `Based on this document, the content ${file.content.split(/\s+/).length > 300
              ? 'contains detailed information relevant to your query. The key sections are shown above.'
              : 'is concise and shown in full above.'}`
            : '**Ask me anything about this document.**',
        ].join('\n'),
        sources: [{
          citation_number: 1,
          doc_filename: file.name,
          page_number: 1,
          excerpt: preview.slice(0, 200),
          relevance_score: 0.95,
        }],
      }
    }
  }

  // 2. Search indexed documents (from Documents page) for relevant content
  const availableDocs = indexedDocs.filter(d => d.status === 'indexed')
  const knowledgeSources: { doc: IndexedDoc; kb: { content: string; pages: number }; score: number }[] = []

  for (const doc of availableDocs) {
    const kb = KNOWLEDGE_BASE[doc.name]
    if (kb && kb.content) {
      // Simple keyword relevance scoring
      const words = q.split(/\s+/).filter(w => w.length > 3)
      const hits = words.filter(w => kb.content.toLowerCase().includes(w)).length
      const score = hits / Math.max(words.length, 1)
      if (score > 0 || availableDocs.length <= 2) {
        knowledgeSources.push({ doc, kb, score: score + (availableDocs.length <= 2 ? 0.3 : 0) })
      }
    }
  }
  knowledgeSources.sort((a, b) => b.score - a.score)
  const topSources = knowledgeSources.slice(0, 3)

  // 3. If we found relevant documents, build a grounded answer
  if (topSources.length > 0) {
    const primaryDoc = topSources[0]
    const kb = primaryDoc.kb

    // Vacation / PTO
    if (q.includes('vacation') || q.includes('pto') || q.includes('leave') || q.includes('time off')) {
      const section = extractSection(kb.content, ['vacation', 'pto', 'time off'])
      return {
        content: buildGroundedAnswer('Vacation & PTO Policy', section, topSources),
        sources: buildSources(topSources, 'vacation'),
      }
    }

    // GDPR / compliance
    if (q.includes('gdpr') || q.includes('compliance') || q.includes('data protection') || q.includes('privacy')) {
      const section = extractSection(kb.content, ['gdpr', 'principle', 'data', 'breach'])
      return {
        content: buildGroundedAnswer('GDPR & Data Protection', section, topSources),
        sources: buildSources(topSources, 'gdpr'),
      }
    }

    // Financial / Q3
    if (q.includes('financial') || q.includes('q3') || q.includes('revenue') || q.includes('report') || q.includes('metric')) {
      const section = extractSection(kb.content, ['revenue', 'financial', 'arr', 'margin'])
      return {
        content: buildGroundedAnswer('Financial Performance', section, topSources),
        sources: buildSources(topSources, 'financial'),
      }
    }

    // Onboarding
    if (q.includes('onboarding') || q.includes('new employee') || q.includes('joining') || q.includes('first day')) {
      const section = extractSection(kb.content, ['onboarding', 'week 1', '90-day', 'orientation'])
      return {
        content: buildGroundedAnswer('Employee Onboarding', section, topSources),
        sources: buildSources(topSources, 'onboarding'),
      }
    }

    // Security
    if (q.includes('security') || q.includes('audit') || q.includes('vulnerability') || q.includes('breach')) {
      const section = extractSection(kb.content, ['security', 'breach', 'finding', 'encryption'])
      return {
        content: buildGroundedAnswer('Security & Audit', section, topSources),
        sources: buildSources(topSources, 'security'),
      }
    }

    // Sales / EMEA
    if (q.includes('sales') || q.includes('emea') || q.includes('pricing') || q.includes('revenue')) {
      const section = extractSection(kb.content, ['sales', 'pricing', 'emea', 'enterprise'])
      return {
        content: buildGroundedAnswer('Sales & Commercial', section, topSources),
        sources: buildSources(topSources, 'sales'),
      }
    }

    // Roadmap / product
    if (q.includes('roadmap') || q.includes('product') || q.includes('feature') || q.includes('2025')) {
      const section = extractSection(kb.content, ['roadmap', 'q1', 'q2', 'initiative', 'target'])
      return {
        content: buildGroundedAnswer('Product Roadmap', section, topSources),
        sources: buildSources(topSources, 'roadmap'),
      }
    }

    // Summarize
    if (q.includes('summar') || q.includes('overview') || q.includes('tell me about') || q.includes('what is')) {
      const preview = kb.content.slice(0, 700).trim()
      return {
        content: [
          `## Summary from your knowledge base`,
          '',
          `Based on **${topSources.length}** indexed document${topSources.length > 1 ? 's' : ''} in your organization:`,
          '',
          preview,
          '',
          topSources.length > 1
            ? `\n*Additional context available from: ${topSources.slice(1).map(s => `\`${s.doc.name}\``).join(', ')}*`
            : '',
        ].join('\n'),
        sources: buildSources(topSources, 'general'),
      }
    }

    // Generic answer from the best matching doc
    const preview = kb.content.slice(0, 500).trim()
    return {
      content: [
        `## Answer from your knowledge base`,
        '',
        `I searched **${availableDocs.length}** indexed document${availableDocs.length > 1 ? 's' : ''} and found relevant content in **\`${primaryDoc.doc.name}\`**:`,
        '',
        preview,
        '',
        `> *Relevance score: ${Math.round(primaryDoc.score * 100)}% match · From ${primaryDoc.doc.dept} dept · ${primaryDoc.doc.pages} pages*`,
      ].join('\n'),
      sources: buildSources(topSources, 'general'),
    }
  }

  // 4. No indexed docs or no match — fallback with helpful message
  const docCount = availableDocs.length
  if (docCount === 0) {
    return {
      content: [
        `## No documents indexed yet`,
        '',
        'Your knowledge base is empty. To get RAG-powered answers:',
        '',
        '1. 📄 Go to **Documents** in the sidebar',
        '2. Upload your files (PDF, DOCX, TXT, CSV, Excel…)',
        '3. Wait for indexing to complete',
        '4. Come back and ask your questions!',
        '',
        'Or **attach a file** directly in this chat using the 📎 button below.',
      ].join('\n'),
      sources: [],
    }
  }

  return {
    content: [
      `## Searching ${docCount} indexed document${docCount > 1 ? 's' : ''}…`,
      '',
      `I searched your knowledge base but couldn't find a strong match for *"${query}"* in:`,
      availableDocs.map(d => `- \`${d.name}\` (${d.dept})`).join('\n'),
      '',
      '**Try rephrasing your question**, or ask about topics covered in your documents such as:',
      '- Vacation & PTO policies',
      '- GDPR compliance requirements',
      '- Financial performance metrics',
      '- Employee onboarding process',
      '- Security audit findings',
    ].join('\n'),
    sources: [],
  }
}

function extractSection(content: string, keywords: string[]): string {
  const lines = content.split('\n')
  let best = ''
  let bestScore = 0
  // Find the section with the most keyword hits
  for (let i = 0; i < lines.length; i++) {
    const window = lines.slice(i, i + 15).join('\n')
    const score = keywords.filter(k => window.toLowerCase().includes(k)).length
    if (score > bestScore) {
      bestScore = score
      best = window
    }
  }
  return best || content.slice(0, 600)
}

function buildGroundedAnswer(
  title: string,
  section: string,
  sources: { doc: IndexedDoc; kb: { content: string; pages: number }; score: number }[]
): string {
  return [
    `## ${title}`,
    '',
    `*Retrieved from ${sources.length} document${sources.length > 1 ? 's' : ''} in your knowledge base:*`,
    '',
    section.trim(),
    '',
    sources.length > 1
      ? `\n*Additional sources: ${sources.slice(1).map(s => `\`${s.doc.name}\``).join(', ')}*`
      : '',
  ].join('\n')
}

function buildSources(
  sources: { doc: IndexedDoc; kb: { content: string; pages: number }; score: number }[],
  topic: string
): Source[] {
  return sources.slice(0, 3).map((s, i) => {
    const excerptMap: Record<string, string> = {
      vacation: 'Full-time employees accrue paid time off based on their years of service.',
      gdpr: 'All employees must complete mandatory annual GDPR training and adhere to the six core principles.',
      financial: 'Total revenue reached $48.2M, an 18% year-over-year increase.',
      onboarding: 'The 90-day onboarding program integrates new employees into their roles and company culture.',
      security: 'Annual security audit conducted. Overall security posture: STRONG. 0 critical findings.',
      sales: 'Enterprise tier targets 500+ employee companies with deal size $50K-500K ARR.',
      roadmap: 'Q1 2025 initiatives include AI-powered summarization and multi-language support.',
      general: s.kb.content.slice(0, 150),
    }
    return {
      citation_number: i + 1,
      doc_filename: s.doc.name,
      page_number: s.kb.pages > 0 ? Math.floor(Math.random() * Math.min(s.kb.pages, 20)) + 1 : null,
      excerpt: excerptMap[topic] || s.kb.content.slice(0, 150),
      relevance_score: Math.round((0.97 - i * 0.06) * 100) / 100,
    }
  })
}

// ── Local storage docs reader ───────────────────────────────────────────────
function loadIndexedDocs(): IndexedDoc[] {
  try {
    const raw = localStorage.getItem('rag_indexed_docs')
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  // Default mock docs (same as Documents page default)
  return [
    { id: 1, name: 'Q3-2024-Financial-Report.pdf', type: 'PDF', size: '2.4 MB', status: 'indexed', pages: 48, dept: 'Finance', uploaded: '2h ago' },
    { id: 2, name: 'Employee-Handbook-2024.docx', type: 'DOCX', size: '1.1 MB', status: 'indexed', pages: 124, dept: 'HR', uploaded: '1d ago' },
    { id: 3, name: 'GDPR-Compliance-Policy.pdf', type: 'PDF', size: '856 KB', status: 'indexed', pages: 32, dept: 'Legal', uploaded: '2d ago' },
    { id: 4, name: 'Product-Roadmap-H1-2025.pptx', type: 'PPTX', size: '5.2 MB', status: 'processing', pages: 64, dept: 'Product', uploaded: '10m ago' },
    { id: 5, name: 'Security-Audit-Report-2024.pdf', type: 'PDF', size: '3.8 MB', status: 'indexed', pages: 89, dept: 'IT', uploaded: '3d ago' },
    { id: 6, name: 'Sales-Playbook-EMEA.docx', type: 'DOCX', size: '920 KB', status: 'indexed', pages: 56, dept: 'Sales', uploaded: '4d ago' },
    { id: 7, name: 'Vendor-Contracts-2024.pdf', type: 'PDF', size: '12.1 MB', status: 'error', pages: 0, dept: 'Legal', uploaded: '5m ago' },
  ]
}

// ── Component ───────────────────────────────────────────────────────────────
export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConvId, setCurrentConvId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const [indexedDocs, setIndexedDocs] = useState<IndexedDoc[]>([])
  const [showDocs, setShowDocs] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setIndexedDocs(loadIndexedDocs())
  }, [])

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

  const streamResponse = useCallback(async (
    assistantId: string,
    resp: { content: string; sources: Source[] }
  ) => {
    const chars = resp.content.split('')
    let accumulated = ''
    for (const ch of chars) {
      await new Promise(r => setTimeout(r, 5 + Math.random() * 5))
      accumulated += ch
      const snap = accumulated
      setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: snap } : m))
    }
    await new Promise(r => setTimeout(r, 150))
    setMessages(prev => prev.map(m =>
      m.id === assistantId ? { ...m, isStreaming: false, sources: resp.sources } : m
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
      content: content || `Attached: ${attachedFiles.map(f => f.name).join(', ')}`,
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

    // Small delay to simulate retrieval
    await new Promise(r => setTimeout(r, 400))
    const resp = ragAnswer(content, currentFiles, indexedDocs)
    await streamResponse(assistantId, resp)
  }, [input, currentConvId, isStreaming, attachedFiles, indexedDocs, streamResponse])

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
            name: file.name, type: file.type,
            content: (ev.target?.result as string) || '', size: sizeStr,
          }])
        }
        reader.readAsText(file)
      } else {
        setAttachedFiles(prev => [...prev, { name: file.name, type: file.type, content: '', size: sizeStr }])
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

  const indexedCount = indexedDocs.filter(d => d.status === 'indexed').length

  return (
    <div className="flex h-full gap-0 -m-6">
      {/* Conversations Sidebar */}
      <div className="w-60 flex-shrink-0 border-r border-slate-800 bg-slate-950/50 flex flex-col h-full overflow-hidden">
        <div className="p-3 border-b border-slate-800 space-y-2">
          <button onClick={startNewChat}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all shadow-lg shadow-indigo-600/20">
            <Plus className="w-4 h-4" /> New Chat
          </button>
          {/* Knowledge base indicator */}
          <button
            onClick={() => setShowDocs(v => !v)}
            className={cn(
              'w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs transition-all border',
              indexedCount > 0
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20'
                : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:text-white'
            )}>
            <Database className="w-3.5 h-3.5" />
            <span className="flex-1 text-left">{indexedCount} docs indexed</span>
            <ChevronDown className={cn('w-3 h-3 transition-transform', showDocs && 'rotate-180')} />
          </button>
        </div>

        {/* Document list panel */}
        <AnimatePresence>
          {showDocs && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-b border-slate-800"
            >
              <div className="p-2 space-y-1 max-h-48 overflow-y-auto">
                {indexedDocs.map(doc => (
                  <div key={doc.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs">
                    {doc.status === 'indexed' && <CheckCircle className="w-3 h-3 text-emerald-400 flex-shrink-0" />}
                    {doc.status === 'processing' && <Loader2 className="w-3 h-3 text-amber-400 animate-spin flex-shrink-0" />}
                    {doc.status === 'error' && <AlertCircle className="w-3 h-3 text-red-400 flex-shrink-0" />}
                    <span className={cn('truncate', doc.status === 'indexed' ? 'text-slate-300' : 'text-slate-500')}>
                      {doc.name}
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 && (
            <div className="text-center text-slate-600 text-xs py-6">No conversations yet</div>
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
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.4, ease: 'easeOut' }}
                className="w-16 h-16 rounded-2xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center mb-6 shadow-lg shadow-indigo-500/20"
              >
                <Brain className="w-8 h-8 text-indigo-400" />
              </motion.div>
              <motion.h2
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="text-2xl font-bold text-white mb-2"
              >
                How can I help?
              </motion.h2>
              <motion.p
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 }}
                className="text-slate-400 text-sm mb-2 text-center max-w-md"
              >
                Ask questions about your {indexedCount} indexed document{indexedCount !== 1 ? 's' : ''}.
              </motion.p>
              {indexedCount > 0 && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                  className="text-xs text-emerald-400 mb-8"
                >
                  ✓ Knowledge base ready · {indexedCount} documents indexed
                </motion.p>
              )}
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25 }}
                className="grid grid-cols-2 gap-3 max-w-xl w-full"
              >
                {SUGGESTED.map((q, i) => (
                  <motion.button
                    key={q}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + i * 0.05 }}
                    onClick={() => sendMessage(q)}
                    className="text-left px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700 text-slate-300 hover:text-white hover:border-indigo-500/50 hover:bg-slate-800 transition-all text-sm group"
                  >
                    <span className="block truncate">{q}</span>
                  </motion.button>
                ))}
              </motion.div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
              {messages.map((msg, i) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn('flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start')}
                >
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
                                  className="w-1.5 h-1.5 rounded-full bg-indigo-400 inline-block"
                                  animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
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
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: 'auto' }}
                              exit={{ opacity: 0, height: 0 }}
                              className="mt-2 space-y-2 overflow-hidden"
                            >
                              {msg.sources.map(src => (
                                <div key={src.citation_number} className="p-3 rounded-lg bg-slate-900/80 border border-slate-700/50 text-xs">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <span className="w-5 h-5 rounded bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold flex-shrink-0 text-[10px]">
                                      {src.citation_number}
                                    </span>
                                    <span className="text-slate-300 font-medium truncate">{src.doc_filename}</span>
                                    {src.page_number && <span className="text-slate-500 flex-shrink-0">p.{src.page_number}</span>}
                                    <span className="ml-auto text-emerald-400 flex-shrink-0">{Math.round(src.relevance_score * 100)}%</span>
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
                </motion.div>
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
                {attachedFiles.map((f, idx) => (
                  <span key={idx} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-500/20 border border-indigo-500/20 text-indigo-300 text-xs">
                    <FileText className="w-3 h-3" /> {f.name}
                    <span className="text-indigo-500 ml-1">{f.size}</span>
                    {f.content && <span className="text-emerald-400 ml-1">✓ readable</span>}
                    <button onClick={() => setAttachedFiles(prev => prev.filter((_, j) => j !== idx))} className="ml-0.5 hover:text-white">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-end gap-3 p-3 rounded-2xl bg-slate-800/60 border border-slate-700 focus-within:border-indigo-500/50 transition-all">
              <button onClick={() => fileInputRef.current?.click()}
                className="p-1.5 text-slate-500 hover:text-indigo-400 transition-colors flex-shrink-0 mb-0.5" title="Attach file">
                <Paperclip className="w-4 h-4" />
              </button>
              <input ref={fileInputRef} type="file" multiple
                accept=".pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.json,.html,.log"
                className="hidden" onChange={handleFileAttach} />
              <textarea ref={textareaRef} value={input}
                onChange={e => { setInput(e.target.value); adjustTextarea() }}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about your documents…"
                rows={1}
                className="flex-1 bg-transparent text-white placeholder-slate-500 text-sm resize-none focus:outline-none min-h-[24px] max-h-[200px] py-0.5" />
              <div className="flex items-center gap-2 flex-shrink-0 mb-0.5">
                <button onClick={() => sendMessage()}
                  disabled={(!input.trim() && attachedFiles.length === 0) || isStreaming}
                  className="w-8 h-8 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center justify-center transition-all shadow-lg shadow-indigo-600/30">
                  {isStreaming
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Send className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <p className="text-center text-xs text-slate-600 mt-2">
              RAG answers from {indexedCount} indexed document{indexedCount !== 1 ? 's' : ''} · Sources cited
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

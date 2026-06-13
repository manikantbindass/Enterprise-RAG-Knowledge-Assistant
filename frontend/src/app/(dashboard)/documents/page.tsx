'use client'
import { useState, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Upload, FileText, File, Search, Filter, CheckCircle, Clock,
  AlertCircle, Trash2, Eye, X, ChevronDown, Database
} from 'lucide-react'
import {
  useAppStore, buildChunks, extractTextContent, getFileType,
  formatSize, relativeTime, RagDocument
} from '@/lib/store'

// ─── Constants ────────────────────────────────────────────────────────────────

const DEPARTMENTS = ['Legal', 'HR', 'Finance', 'IT', 'Sales', 'Product', 'Engineering', 'Marketing']

const DEPT_COLORS: Record<string, string> = {
  Legal:       '#6366f1',
  HR:          '#ec4899',
  Finance:     '#10b981',
  IT:          '#0ea5e9',
  Sales:       '#f59e0b',
  Product:     '#8b5cf6',
  Engineering: '#14b8a6',
  Marketing:   '#f97316',
}

const STATUS_CONFIG = {
  indexed:    { label: 'Indexed',    color: '#10b981', bg: 'rgba(16,185,129,.15)', icon: CheckCircle },
  processing: { label: 'Processing', color: '#f59e0b', bg: 'rgba(245,158,11,.15)',  icon: Clock },
  uploading:  { label: 'Uploading',  color: '#0ea5e9', bg: 'rgba(14,165,233,.15)',  icon: Clock },
  error:      { label: 'Error',      color: '#ef4444', bg: 'rgba(239,68,68,.15)',    icon: AlertCircle },
}

type StatusFilter = 'All' | 'indexed' | 'processing' | 'error'

// ─── Pending upload state ─────────────────────────────────────────────────────

interface PendingFile {
  id: string
  file: File
  department: string
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DocumentsPage() {
  const { state, dispatch } = useAppStore()
  const { documents, settings } = state

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('All')
  const [dragging, setDragging] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  const [previewDoc, setPreviewDoc] = useState<RagDocument | null>(null)
  const [statusOpen, setStatusOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ─── Upload logic ────────────────────────────────────────────────────────────

  const processFile = useCallback(async (file: File, department: string) => {
    if (file.size > 50 * 1024 * 1024) {
      alert(`File "${file.name}" exceeds 50 MB limit.`)
      return
    }

    const id = `doc_${Date.now()}_${Math.random().toString(36).slice(2)}`
    const isText = /\.(txt|md|markdown|csv|json|xml|html|htm|log|yaml|yml|ts|tsx|js|jsx|py|java|c|cpp|h|css|sql|sh|bash|env|toml|ini|conf)$/i.test(file.name)

    const doc: RagDocument = {
      id,
      name: file.name,
      fileType: getFileType(file.name),
      mimeType: file.type || 'application/octet-stream',
      size: formatSize(file.size),
      sizeBytes: file.size,
      status: 'uploading',
      pages: 0,
      department,
      uploadedAt: new Date().toISOString(),
      content: '',
      chunks: [],
      canQuery: false,
    }

    dispatch({ type: 'ADD_DOC', doc })

    // Step 1 → processing after 500ms
    await new Promise(r => setTimeout(r, 500))
    dispatch({ type: 'UPDATE_DOC', id, patch: { status: 'processing' } })

    // Extract text concurrently while waiting
    const content = await extractTextContent(file)

    // Step 2 → indexed after 2000ms
    await new Promise(r => setTimeout(r, 2000))

    const pages = isText
      ? Math.max(1, Math.floor(content.split('\n').length / 2))
      : Math.floor(file.size / 2500) + 1

    const chunks = isText ? buildChunks(content, settings.chunkSize) : []

    dispatch({
      type: 'UPDATE_DOC',
      id,
      patch: {
        status: 'indexed',
        content,
        chunks,
        pages,
        canQuery: isText && chunks.length > 0,
      },
    })
  }, [dispatch, settings.chunkSize])

  const handleFilesDropped = useCallback((files: FileList | File[]) => {
    const arr = Array.from(files)
    const pending: PendingFile[] = arr.map(f => ({
      id: `pf_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      file: f,
      department: 'Engineering',
    }))
    setPendingFiles(prev => [...prev, ...pending])
  }, [])

  const confirmUpload = useCallback((pf: PendingFile) => {
    processFile(pf.file, pf.department)
    setPendingFiles(prev => prev.filter(p => p.id !== pf.id))
  }, [processFile])

  const confirmAll = useCallback(() => {
    pendingFiles.forEach(pf => processFile(pf.file, pf.department))
    setPendingFiles([])
  }, [pendingFiles, processFile])

  const cancelPending = useCallback((id: string) => {
    setPendingFiles(prev => prev.filter(p => p.id !== id))
  }, [])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(true)
  }, [])

  const onDragLeave = useCallback(() => setDragging(false), [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length > 0) handleFilesDropped(e.dataTransfer.files)
  }, [handleFilesDropped])

  const onFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFilesDropped(e.target.files)
    }
    e.target.value = ''
  }, [handleFilesDropped])

  // ─── Filter ──────────────────────────────────────────────────────────────────

  const filtered = documents.filter(d => {
    const matchSearch =
      search === '' ||
      d.name.toLowerCase().includes(search.toLowerCase()) ||
      d.department.toLowerCase().includes(search.toLowerCase())
    const matchStatus = statusFilter === 'All' || d.status === statusFilter
    return matchSearch && matchStatus
  })

  // ─── Stats ───────────────────────────────────────────────────────────────────

  const total      = documents.length
  const indexed    = documents.filter(d => d.status === 'indexed').length
  const processing = documents.filter(d => d.status === 'processing' || d.status === 'uploading').length
  const errors     = documents.filter(d => d.status === 'error').length

  // ─── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="docs-page">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="docs-header">
        <div>
          <h1 className="docs-title">Knowledge Base</h1>
          <p className="docs-subtitle">Upload and manage documents for RAG retrieval</p>
        </div>
        <button
          id="upload-btn"
          className="btn-primary"
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload size={16} />
          Upload Files
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: 'none' }}
          onChange={onFileInputChange}
        />
      </div>

      {/* ── Stats bar ──────────────────────────────────────────────────────── */}
      {total > 0 && (
        <div className="stats-bar">
          <StatCard label="Total" value={total}      color="#a78bfa" />
          <StatCard label="Indexed"    value={indexed}    color="#10b981" />
          <StatCard label="Processing" value={processing} color="#f59e0b" />
          <StatCard label="Errors"     value={errors}     color="#ef4444" />
        </div>
      )}

      {/* ── Drag-drop zone (always visible if empty) ───────────────────────── */}
      {total === 0 && pendingFiles.length === 0 ? (
        <EmptyDropZone
          dragging={dragging}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
        />
      ) : (
        <DropBanner
          dragging={dragging}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
        />
      )}

      {/* ── Pending department picker ───────────────────────────────────────── */}
      <AnimatePresence>
        {pendingFiles.length > 0 && (
          <motion.div
            className="pending-panel"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
          >
            <div className="pending-header">
              <span className="pending-title">📋 Ready to upload — pick departments</span>
              <div className="pending-actions">
                <button className="btn-ghost" onClick={() => setPendingFiles([])}>Cancel all</button>
                <button className="btn-primary" onClick={confirmAll}>Upload all</button>
              </div>
            </div>
            {pendingFiles.map(pf => (
              <PendingRow
                key={pf.id}
                pf={pf}
                onDeptChange={(dept) =>
                  setPendingFiles(prev =>
                    prev.map(p => p.id === pf.id ? { ...p, department: dept } : p)
                  )
                }
                onConfirm={() => confirmUpload(pf)}
                onCancel={() => cancelPending(pf.id)}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Search + Filter ─────────────────────────────────────────────────── */}
      {total > 0 && (
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={15} className="search-icon" />
            <input
              id="doc-search"
              className="search-input"
              placeholder="Search by name or department…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button className="search-clear" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            )}
          </div>

          <div className="filter-wrap">
            <Filter size={14} />
            <button
              id="status-filter-btn"
              className="filter-btn"
              onClick={() => setStatusOpen(o => !o)}
            >
              {statusFilter === 'All' ? 'All statuses' : STATUS_CONFIG[statusFilter].label}
              <ChevronDown size={13} />
            </button>
            <AnimatePresence>
              {statusOpen && (
                <motion.div
                  className="dropdown"
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                >
                  {(['All', 'indexed', 'processing', 'error'] as const).map(s => (
                    <button
                      key={s}
                      className={`dropdown-item ${statusFilter === s ? 'active' : ''}`}
                      onClick={() => { setStatusFilter(s); setStatusOpen(false) }}
                    >
                      {s === 'All' ? 'All statuses' : STATUS_CONFIG[s].label}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* ── Document list ───────────────────────────────────────────────────── */}
      {filtered.length > 0 && (
        <div className="doc-list">
          <AnimatePresence initial={false}>
            {filtered.map(doc => (
              <DocRow
                key={doc.id}
                doc={doc}
                onDelete={() => dispatch({ type: 'DELETE_DOC', id: doc.id })}
                onPreview={() => setPreviewDoc(doc)}
              />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* ── No-results state (docs exist but search filters everything out) ── */}
      {total > 0 && filtered.length === 0 && (
        <div className="no-results">
          <Search size={36} opacity={0.3} />
          <p>No documents match your search</p>
          <button className="btn-ghost" onClick={() => { setSearch(''); setStatusFilter('All') }}>
            Clear filters
          </button>
        </div>
      )}

      {/* ── Preview modal ───────────────────────────────────────────────────── */}
      <AnimatePresence>
        {previewDoc && (
          <PreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
        )}
      </AnimatePresence>

      <style>{styles}</style>
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="stat-card">
      <span className="stat-value" style={{ color }}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

function EmptyDropZone({
  dragging, onDragOver, onDragLeave, onDrop, onClick
}: {
  dragging: boolean
  onDragOver: React.DragEventHandler
  onDragLeave: React.DragEventHandler
  onDrop: React.DragEventHandler
  onClick: () => void
}) {
  return (
    <motion.div
      className={`empty-zone ${dragging ? 'dragging' : ''}`}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={onClick}
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
    >
      <div className="empty-icon-wrap">
        <motion.div
          animate={{ y: dragging ? -8 : 0 }}
          transition={{ type: 'spring', stiffness: 300 }}
        >
          <Database size={52} strokeWidth={1.2} />
        </motion.div>
      </div>
      <h2 className="empty-title">
        {dragging ? 'Drop files here' : 'No documents yet'}
      </h2>
      <p className="empty-sub">
        Drag &amp; drop any files here, or click to browse.<br />
        Supports PDF, DOCX, TXT, MD, CSV, JSON, code files and more.
      </p>
      <div className="empty-badges">
        {['PDF', 'DOCX', 'TXT', 'MD', 'CSV', 'JSON', 'PY', 'TS'].map(ext => (
          <span key={ext} className="ext-badge">{ext}</span>
        ))}
        <span className="ext-badge muted">+more</span>
      </div>
      <div className="empty-cta">
        <Upload size={15} />
        Choose files to upload
      </div>
    </motion.div>
  )
}

function DropBanner({
  dragging, onDragOver, onDragLeave, onDrop, onClick
}: {
  dragging: boolean
  onDragOver: React.DragEventHandler
  onDragLeave: React.DragEventHandler
  onDrop: React.DragEventHandler
  onClick: () => void
}) {
  return (
    <div
      className={`drop-banner ${dragging ? 'dragging' : ''}`}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={onClick}
    >
      <Upload size={14} />
      {dragging ? 'Release to upload' : 'Drag & drop more files here'}
    </div>
  )
}

function PendingRow({
  pf, onDeptChange, onConfirm, onCancel
}: {
  pf: PendingFile
  onDeptChange: (dept: string) => void
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="pending-row">
      <File size={16} style={{ flexShrink: 0, color: '#a78bfa' }} />
      <span className="pending-name">{pf.file.name}</span>
      <span className="pending-size">{formatSize(pf.file.size)}</span>
      <div className="dept-tags">
        {DEPARTMENTS.map(d => (
          <button
            key={d}
            className={`dept-tag ${pf.department === d ? 'active' : ''}`}
            style={pf.department === d ? { background: DEPT_COLORS[d], borderColor: DEPT_COLORS[d] } : {}}
            onClick={() => onDeptChange(d)}
          >
            {d}
          </button>
        ))}
      </div>
      <div className="pending-btns">
        <button className="btn-ghost sm" onClick={onCancel}><X size={13} /></button>
        <button className="btn-primary sm" onClick={onConfirm}>Upload</button>
      </div>
    </div>
  )
}

function DocRow({
  doc, onDelete, onPreview
}: {
  doc: RagDocument
  onDelete: () => void
  onPreview: () => void
}) {
  const sc = STATUS_CONFIG[doc.status]
  const Icon = sc.icon

  return (
    <motion.div
      className="doc-row"
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.2 }}
    >
      {/* File type badge */}
      <div className="file-type-badge">
        <FileText size={13} />
        {doc.fileType}
      </div>

      {/* Name + meta */}
      <div className="doc-meta">
        <span className="doc-name" title={doc.name}>{doc.name}</span>
        <div className="doc-sub">
          <span>{doc.size}</span>
          <span>·</span>
          <span>{doc.pages > 0 ? `${doc.pages} page${doc.pages !== 1 ? 's' : ''}` : '—'}</span>
          <span>·</span>
          <span>{relativeTime(doc.uploadedAt)}</span>
        </div>
      </div>

      {/* Department badge */}
      <span
        className="dept-badge"
        style={{ background: `${DEPT_COLORS[doc.department] ?? '#6366f1'}22`, color: DEPT_COLORS[doc.department] ?? '#6366f1', borderColor: `${DEPT_COLORS[doc.department] ?? '#6366f1'}44` }}
      >
        {doc.department}
      </span>

      {/* Status badge */}
      <span className="status-badge" style={{ background: sc.bg, color: sc.color }}>
        {doc.status === 'processing' || doc.status === 'uploading' ? (
          <span className="spinner" style={{ borderTopColor: sc.color }} />
        ) : (
          <Icon size={12} />
        )}
        {sc.label}
      </span>

      {/* Actions */}
      <div className="doc-actions">
        <button
          id={`preview-${doc.id}`}
          className="action-btn"
          title="Preview"
          onClick={onPreview}
          disabled={doc.status === 'uploading' || doc.status === 'processing'}
        >
          <Eye size={15} />
        </button>
        <button
          id={`delete-${doc.id}`}
          className="action-btn danger"
          title="Delete"
          onClick={onDelete}
        >
          <Trash2 size={15} />
        </button>
      </div>
    </motion.div>
  )
}

function PreviewModal({ doc, onClose }: { doc: RagDocument; onClose: () => void }) {
  const isBinary = !doc.content

  return (
    <motion.div
      className="modal-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="modal"
        initial={{ scale: 0.95, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 20 }}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <div className="modal-title">{doc.name}</div>
            <div className="modal-sub">{doc.size} · {doc.fileType} · {doc.department}</div>
          </div>
          <button className="modal-close" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="modal-body">
          {isBinary ? (
            <div className="binary-msg">
              <Database size={36} opacity={0.4} />
              <p>Full text extraction requires the backend API (<code>docker compose up</code>).</p>
              <p className="binary-sub">
                Binary file detected ({doc.fileType}). Once the backend is running, upload this file again to extract searchable content.
              </p>
            </div>
          ) : (
            <pre className="preview-text">{doc.content}</pre>
          )}
        </div>

        {!isBinary && (
          <div className="modal-footer">
            <span>{doc.chunks.length} chunk{doc.chunks.length !== 1 ? 's' : ''} · {doc.content.split('\n').length} lines</span>
            <span style={{ color: '#10b981' }}>✓ Ready for RAG queries</span>
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = `
  .docs-page {
    padding: 2rem;
    max-width: 1100px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    min-height: 100%;
  }

  /* Header */
  .docs-header {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .docs-header > div:first-child { flex: 1; }
  .docs-title {
    font-size: 1.6rem;
    font-weight: 700;
    background: linear-gradient(135deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 .25rem;
  }
  .docs-subtitle { font-size: .85rem; color: #94a3b8; margin: 0; }

  /* Buttons */
  .btn-primary {
    display: inline-flex;
    align-items: center;
    gap: .45rem;
    padding: .5rem 1.1rem;
    background: linear-gradient(135deg, #7c3aed, #4f46e5);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: .85rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .2s, transform .15s;
    white-space: nowrap;
  }
  .btn-primary:hover { opacity: .88; transform: translateY(-1px); }
  .btn-primary.sm { padding: .3rem .7rem; font-size: .8rem; }

  .btn-ghost {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    padding: .45rem .9rem;
    background: transparent;
    color: #94a3b8;
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 8px;
    font-size: .83rem;
    cursor: pointer;
    transition: color .2s, border-color .2s;
  }
  .btn-ghost:hover { color: #e2e8f0; border-color: rgba(255,255,255,.25); }
  .btn-ghost.sm { padding: .25rem .55rem; }

  /* Stats bar */
  .stats-bar {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: .75rem;
  }
  .stat-card {
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 10px;
    padding: .85rem 1rem;
    display: flex;
    flex-direction: column;
    gap: .2rem;
  }
  .stat-value { font-size: 1.6rem; font-weight: 700; line-height: 1; }
  .stat-label { font-size: .75rem; color: #64748b; text-transform: uppercase; letter-spacing: .06em; }

  /* Empty drop zone */
  .empty-zone {
    border: 2px dashed rgba(167,139,250,.3);
    border-radius: 18px;
    padding: 4rem 2rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    cursor: pointer;
    background: rgba(167,139,250,.03);
    transition: border-color .2s, background .2s;
    text-align: center;
  }
  .empty-zone.dragging,
  .empty-zone:hover {
    border-color: rgba(167,139,250,.7);
    background: rgba(167,139,250,.07);
  }
  .empty-icon-wrap {
    width: 88px; height: 88px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, rgba(124,58,237,.25), rgba(79,70,229,.25));
    color: #a78bfa;
  }
  .empty-title { font-size: 1.4rem; font-weight: 700; color: #e2e8f0; margin: 0; }
  .empty-sub { font-size: .88rem; color: #64748b; margin: 0; line-height: 1.6; }
  .empty-badges { display: flex; gap: .4rem; flex-wrap: wrap; justify-content: center; }
  .ext-badge {
    padding: .2rem .55rem;
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 5px;
    font-size: .72rem;
    color: #94a3b8;
    font-weight: 600;
    letter-spacing: .04em;
  }
  .ext-badge.muted { color: #4b5563; }
  .empty-cta {
    display: inline-flex; align-items: center; gap: .5rem;
    padding: .6rem 1.4rem;
    background: linear-gradient(135deg, #7c3aed22, #4f46e522);
    border: 1px solid rgba(167,139,250,.35);
    border-radius: 9px;
    color: #a78bfa;
    font-size: .85rem;
    font-weight: 600;
    margin-top: .5rem;
  }

  /* Drop banner (compact) */
  .drop-banner {
    display: flex; align-items: center; gap: .6rem;
    padding: .7rem 1.25rem;
    border: 1.5px dashed rgba(167,139,250,.25);
    border-radius: 10px;
    color: #64748b;
    font-size: .83rem;
    cursor: pointer;
    transition: border-color .2s, color .2s, background .2s;
    background: rgba(167,139,250,.02);
  }
  .drop-banner:hover, .drop-banner.dragging {
    border-color: rgba(167,139,250,.55);
    color: #a78bfa;
    background: rgba(167,139,250,.05);
  }

  /* Pending panel */
  .pending-panel {
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(167,139,250,.25);
    border-radius: 12px;
    overflow: hidden;
  }
  .pending-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: .85rem 1.1rem;
    background: rgba(167,139,250,.06);
    border-bottom: 1px solid rgba(255,255,255,.06);
    gap: 1rem;
    flex-wrap: wrap;
  }
  .pending-title { font-size: .88rem; font-weight: 600; color: #c4b5fd; }
  .pending-actions { display: flex; gap: .5rem; }
  .pending-row {
    display: flex; align-items: center; gap: .75rem;
    padding: .75rem 1.1rem;
    border-bottom: 1px solid rgba(255,255,255,.04);
    flex-wrap: wrap;
  }
  .pending-row:last-child { border-bottom: none; }
  .pending-name { font-size: .84rem; font-weight: 500; color: #e2e8f0; flex: 1; min-width: 120px; word-break: break-all; }
  .pending-size { font-size: .78rem; color: #64748b; white-space: nowrap; }
  .dept-tags { display: flex; gap: .3rem; flex-wrap: wrap; }
  .dept-tag {
    padding: .18rem .55rem;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 5px;
    font-size: .72rem;
    font-weight: 600;
    cursor: pointer;
    color: #94a3b8;
    background: transparent;
    transition: all .15s;
  }
  .dept-tag:hover { border-color: rgba(255,255,255,.3); color: #e2e8f0; }
  .dept-tag.active { color: #fff; }
  .pending-btns { display: flex; gap: .4rem; }

  /* Toolbar */
  .toolbar {
    display: flex; align-items: center; gap: .75rem; flex-wrap: wrap;
  }
  .search-wrap {
    position: relative; flex: 1; min-width: 200px;
    display: flex; align-items: center;
  }
  .search-icon {
    position: absolute; left: .75rem; color: #475569; pointer-events: none;
  }
  .search-input {
    width: 100%;
    padding: .55rem .75rem .55rem 2.2rem;
    background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.09);
    border-radius: 9px;
    color: #e2e8f0;
    font-size: .85rem;
    outline: none;
    transition: border-color .2s;
  }
  .search-input::placeholder { color: #475569; }
  .search-input:focus { border-color: rgba(167,139,250,.5); }
  .search-clear {
    position: absolute; right: .6rem;
    background: none; border: none; cursor: pointer; color: #64748b;
    display: flex; align-items: center;
    transition: color .15s;
  }
  .search-clear:hover { color: #e2e8f0; }

  .filter-wrap {
    position: relative;
    display: flex; align-items: center; gap: .4rem;
    color: #64748b; font-size: .83rem;
  }
  .filter-btn {
    display: flex; align-items: center; gap: .35rem;
    padding: .52rem .85rem;
    background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.09);
    border-radius: 9px;
    color: #94a3b8; font-size: .83rem;
    cursor: pointer;
    transition: border-color .2s;
  }
  .filter-btn:hover { border-color: rgba(255,255,255,.2); color: #e2e8f0; }
  .dropdown {
    position: absolute; top: calc(100% + 6px); right: 0;
    min-width: 150px;
    background: #1e2130;
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 9px;
    padding: .3rem;
    z-index: 50;
    box-shadow: 0 12px 32px rgba(0,0,0,.5);
  }
  .dropdown-item {
    display: block; width: 100%; text-align: left;
    padding: .45rem .75rem;
    background: none; border: none;
    color: #94a3b8; font-size: .83rem;
    cursor: pointer; border-radius: 6px;
    transition: background .15s, color .15s;
  }
  .dropdown-item:hover { background: rgba(255,255,255,.07); color: #e2e8f0; }
  .dropdown-item.active { background: rgba(167,139,250,.15); color: #a78bfa; }

  /* Document list */
  .doc-list {
    display: flex; flex-direction: column; gap: .5rem;
  }
  .doc-row {
    display: flex; align-items: center; gap: .85rem;
    padding: .85rem 1.1rem;
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 11px;
    transition: border-color .2s, background .2s;
    flex-wrap: wrap;
  }
  .doc-row:hover {
    border-color: rgba(255,255,255,.14);
    background: rgba(255,255,255,.05);
  }
  .file-type-badge {
    display: flex; align-items: center; gap: .3rem;
    padding: .22rem .6rem;
    background: rgba(167,139,250,.12);
    border: 1px solid rgba(167,139,250,.25);
    border-radius: 6px;
    font-size: .7rem; font-weight: 700;
    color: #a78bfa;
    white-space: nowrap; flex-shrink: 0;
  }
  .doc-meta { flex: 1; min-width: 150px; overflow: hidden; }
  .doc-name {
    display: block;
    font-size: .87rem; font-weight: 600; color: #e2e8f0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .doc-sub {
    display: flex; gap: .4rem;
    font-size: .75rem; color: #4b5563;
    margin-top: .15rem; flex-wrap: wrap;
  }
  .dept-badge {
    padding: .2rem .6rem;
    border: 1px solid;
    border-radius: 6px;
    font-size: .72rem; font-weight: 600;
    white-space: nowrap; flex-shrink: 0;
  }
  .status-badge {
    display: flex; align-items: center; gap: .35rem;
    padding: .22rem .65rem;
    border-radius: 6px;
    font-size: .75rem; font-weight: 600;
    white-space: nowrap; flex-shrink: 0;
  }
  .spinner {
    width: 11px; height: 11px;
    border: 2px solid transparent;
    border-radius: 50%;
    animation: spin .7s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .doc-actions { display: flex; gap: .35rem; margin-left: auto; flex-shrink: 0; }
  .action-btn {
    display: flex; align-items: center; justify-content: center;
    width: 30px; height: 30px;
    background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 7px;
    color: #64748b;
    cursor: pointer;
    transition: all .15s;
  }
  .action-btn:hover { background: rgba(255,255,255,.1); color: #e2e8f0; border-color: rgba(255,255,255,.18); }
  .action-btn.danger:hover { background: rgba(239,68,68,.12); color: #ef4444; border-color: rgba(239,68,68,.3); }
  .action-btn:disabled { opacity: .35; cursor: not-allowed; }

  /* No results */
  .no-results {
    display: flex; flex-direction: column; align-items: center; gap: .75rem;
    padding: 3rem; color: #4b5563; text-align: center;
  }
  .no-results p { margin: 0; font-size: .9rem; }

  /* Modal */
  .modal-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,.65);
    backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
    z-index: 1000; padding: 1.5rem;
  }
  .modal {
    background: #161827;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 16px;
    width: 100%; max-width: 720px;
    max-height: 80vh;
    display: flex; flex-direction: column;
    box-shadow: 0 24px 64px rgba(0,0,0,.6);
    overflow: hidden;
  }
  .modal-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    padding: 1.25rem 1.4rem;
    border-bottom: 1px solid rgba(255,255,255,.08);
    gap: 1rem;
  }
  .modal-title { font-size: 1rem; font-weight: 700; color: #e2e8f0; word-break: break-all; }
  .modal-sub { font-size: .78rem; color: #64748b; margin-top: .2rem; }
  .modal-close {
    display: flex; align-items: center; justify-content: center;
    width: 32px; height: 32px;
    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
    border-radius: 8px; color: #64748b;
    cursor: pointer; flex-shrink: 0;
    transition: all .15s;
  }
  .modal-close:hover { background: rgba(255,255,255,.12); color: #e2e8f0; }
  .modal-body { flex: 1; overflow-y: auto; padding: 1.25rem 1.4rem; }
  .preview-text {
    font-size: .8rem; line-height: 1.7;
    color: #94a3b8;
    white-space: pre-wrap; word-break: break-word;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    margin: 0;
  }
  .binary-msg {
    display: flex; flex-direction: column; align-items: center; gap: .85rem;
    padding: 2.5rem 1rem; text-align: center; color: #64748b;
  }
  .binary-msg p { margin: 0; font-size: .9rem; line-height: 1.6; color: #94a3b8; }
  .binary-msg code {
    background: rgba(255,255,255,.08); padding: .15rem .4rem;
    border-radius: 5px; font-size: .82rem; color: #a78bfa;
    font-family: monospace;
  }
  .binary-sub { font-size: .82rem; color: #4b5563; margin-top: .25rem; }
  .modal-footer {
    display: flex; align-items: center; justify-content: space-between;
    padding: .75rem 1.4rem;
    border-top: 1px solid rgba(255,255,255,.07);
    font-size: .77rem; color: #4b5563;
  }

  @media (max-width: 640px) {
    .docs-page { padding: 1rem; }
    .stats-bar { grid-template-columns: repeat(2, 1fr); }
    .doc-row { gap: .5rem; }
    .doc-actions { margin-left: 0; }
  }
`

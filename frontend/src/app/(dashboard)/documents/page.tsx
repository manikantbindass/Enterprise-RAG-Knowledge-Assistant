'use client'

import { useState, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Upload, FileText, File, Search, Filter, CheckCircle, Clock, AlertCircle, Trash2, Eye } from 'lucide-react'

const mockDocs = [
  { id: 1, name: 'Q3-2024-Financial-Report.pdf', type: 'PDF', size: '2.4 MB', status: 'indexed', pages: 48, dept: 'Finance', uploaded: '2h ago' },
  { id: 2, name: 'Employee-Handbook-2024.docx', type: 'DOCX', size: '1.1 MB', status: 'indexed', pages: 124, dept: 'HR', uploaded: '1d ago' },
  { id: 3, name: 'GDPR-Compliance-Policy.pdf', type: 'PDF', size: '856 KB', status: 'indexed', pages: 32, dept: 'Legal', uploaded: '2d ago' },
  { id: 4, name: 'Product-Roadmap-H1-2025.pptx', type: 'PPTX', size: '5.2 MB', status: 'processing', pages: 64, dept: 'Product', uploaded: '10m ago' },
  { id: 5, name: 'Security-Audit-Report-2024.pdf', type: 'PDF', size: '3.8 MB', status: 'indexed', pages: 89, dept: 'IT', uploaded: '3d ago' },
  { id: 6, name: 'Sales-Playbook-EMEA.docx', type: 'DOCX', size: '920 KB', status: 'indexed', pages: 56, dept: 'Sales', uploaded: '4d ago' },
  { id: 7, name: 'Vendor-Contracts-2024.pdf', type: 'PDF', size: '12.1 MB', status: 'error', pages: 0, dept: 'Legal', uploaded: '5m ago' },
]

const statusBadge: Record<string, { label: string; cls: string; icon: any }> = {
  indexed:    { label: 'Indexed',    cls: 'bg-emerald-400/10 text-emerald-400 border-emerald-400/20', icon: CheckCircle },
  processing: { label: 'Processing', cls: 'bg-amber-400/10 text-amber-400 border-amber-400/20',   icon: Clock },
  error:      { label: 'Error',      cls: 'bg-red-400/10 text-red-400 border-red-400/20',           icon: AlertCircle },
}

export default function DocumentsPage() {
  const [search, setSearch] = useState('')
  const [dragging, setDragging] = useState(false)
  const [docs, setDocs] = useState(mockDocs)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [showFilter, setShowFilter] = useState(false)

  // Persist docs to localStorage so Chat page can read them
  useEffect(() => {
    try { localStorage.setItem('rag_indexed_docs', JSON.stringify(docs)) } catch {}
  }, [docs])

  const filtered = docs.filter(d => {
    const matchesSearch = d.name.toLowerCase().includes(search.toLowerCase()) ||
      d.dept.toLowerCase().includes(search.toLowerCase())
    const matchesStatus = statusFilter === 'all' || d.status === statusFilter
    return matchesSearch && matchesStatus
  })

  // Simulate indexing: after 3s transition processing → indexed
  const addFiles = useCallback((files: File[]) => {
    const newDocs = files.map((f, i) => ({
      id: Date.now() + i,
      name: f.name,
      type: f.name.split('.').pop()?.toUpperCase() || 'FILE',
      size: f.size >= 1024 * 1024
        ? `${(f.size / 1024 / 1024).toFixed(1)} MB`
        : `${(f.size / 1024).toFixed(0)} KB`,
      status: 'processing' as const,
      pages: 0,
      dept: 'Uploads',
      uploaded: 'Just now',
    }))
    setDocs(prev => [...newDocs, ...prev])

    // After 3s, mark each as indexed with simulated page count
    newDocs.forEach(doc => {
      setTimeout(() => {
        setDocs(prev => prev.map(d =>
          d.id === doc.id
            ? { ...d, status: 'indexed', pages: Math.floor(Math.random() * 80 + 5), uploaded: 'Just now' }
            : d
        ))
      }, 3000 + Math.random() * 1000)
    })
    // docs state update triggers the useEffect which saves to localStorage
  }, [])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    addFiles(Array.from(e.dataTransfer.files))
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Documents</h1>
          <p className="text-slate-400 text-sm mt-1">{docs.length} documents · {docs.filter(d => d.status === 'indexed').length} indexed</p>
        </div>
        <label className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-all text-sm font-medium flex items-center gap-2 shadow-lg shadow-indigo-600/30 cursor-pointer">
          <Upload className="w-4 h-4" /> Upload Document
          <input type="file" multiple accept=".pdf,.docx,.doc,.txt,.csv,.xlsx,.md" className="hidden"
            onChange={e => {
              const files = Array.from(e.target.files || [])
              if (files.length) addFiles(files)
              e.target.value = '' // reset so same file can be re-uploaded
            }}
          />
        </label>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${
          dragging ? 'border-indigo-500 bg-indigo-500/10' : 'border-slate-700 hover:border-slate-600'
        }`}
      >
        <Upload className="w-8 h-8 text-slate-500 mx-auto mb-3" />
        <p className="text-slate-400 text-sm">Drag & drop files here, or <span className="text-indigo-400">click Upload</span></p>
        <p className="text-slate-600 text-xs mt-1">PDF, DOCX, TXT, CSV, XLSX, MD — up to 100MB</p>
      </div>

      {/* Search + Filter */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search documents or departments…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
        <button
          onClick={() => setShowFilter(v => !v)}
          className={`px-4 py-2.5 rounded-xl border text-sm flex items-center gap-2 transition-all ${showFilter || statusFilter !== 'all' ? 'bg-indigo-500/15 border-indigo-500/30 text-indigo-300' : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-white'}`}>
          <Filter className="w-4 h-4" />
          {statusFilter === 'all' ? 'Filter' : statusFilter.charAt(0).toUpperCase() + statusFilter.slice(1)}
        </button>
      </div>
      {showFilter && (
        <div className="flex gap-2 flex-wrap">
          {['all', 'indexed', 'processing', 'error'].map(s => (
            <button key={s} onClick={() => { setStatusFilter(s); setShowFilter(false) }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border ${statusFilter === s ? 'bg-indigo-500/20 border-indigo-500/30 text-indigo-300' : 'bg-slate-800/60 border-slate-700 text-slate-400 hover:text-white'}`}>
              {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      )}

      {/* Stats bar */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Documents', value: docs.length, color: 'text-white' },
          { label: 'Indexed', value: docs.filter(d => d.status === 'indexed').length, color: 'text-emerald-400' },
          { label: 'Processing', value: docs.filter(d => d.status === 'processing').length, color: 'text-amber-400' },
        ].map(s => (
          <div key={s.label} className="p-4 rounded-xl border border-slate-800 bg-slate-900/50">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-slate-500 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Documents Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-5 py-3 border-b border-slate-800 text-xs font-medium text-slate-500 uppercase tracking-wide">
          <div className="col-span-5">Document</div>
          <div className="col-span-2">Department</div>
          <div className="col-span-1">Size</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-1">Uploaded</div>
          <div className="col-span-1"></div>
        </div>

        <div className="divide-y divide-slate-800">
          {filtered.map((doc, i) => {
            const s = statusBadge[doc.status]
            const StatusIcon = s.icon
            return (
              <motion.div
                key={doc.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className="grid grid-cols-12 gap-4 px-5 py-4 items-center hover:bg-slate-800/30 transition-colors group"
              >
                <div className="col-span-5 flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-indigo-500/20 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-4 h-4 text-indigo-400" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm text-white font-medium truncate">{doc.name}</div>
                    <div className="text-xs text-slate-500">{doc.type} · {doc.pages > 0 ? `${doc.pages} pages` : '—'}</div>
                  </div>
                </div>
                <div className="col-span-2 text-sm text-slate-400">{doc.dept}</div>
                <div className="col-span-1 text-sm text-slate-400">{doc.size}</div>
                <div className="col-span-2">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${s.cls}`}>
                    <StatusIcon className="w-3 h-3" />
                    {s.label}
                  </span>
                </div>
                <div className="col-span-1 text-xs text-slate-500">{doc.uploaded}</div>
                <div className="col-span-1 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button className="p-1 text-slate-400 hover:text-white transition-colors" title="Preview"><Eye className="w-3.5 h-3.5" /></button>
                  <button className="p-1 text-slate-400 hover:text-red-400 transition-colors" title="Delete"
                    onClick={() => setDocs(prev => prev.filter(d => d.id !== doc.id))}
                  ><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </motion.div>
            )
          })}
        </div>

        {filtered.length === 0 && (
          <div className="py-16 text-center text-slate-500">
            <File className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No documents found</p>
          </div>
        )}
      </div>
    </div>
  )
}

'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Settings,
  Cpu,
  Key,
  Save,
  Eye,
  EyeOff,
  RefreshCw,
  Trash2,
  Download,
  AlertTriangle,
  CheckCircle,
  Server,
} from 'lucide-react'
import { useAppStore } from '@/lib/store'

// ─── Types ───────────────────────────────────────────────────────────────────

type Tab = 'general' | 'models' | 'api'

interface SavedState {
  [key: string]: boolean
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function SliderField({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  format,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (v: number) => void
  format?: (v: number) => string
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="settings-field">
      <div className="field-label-row">
        <span className="field-label">{label}</span>
        <span className="field-value">{format ? format(value) : value}</span>
      </div>
      <div className="slider-track-wrap">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="slider-input"
          style={{ '--pct': `${pct}%` } as React.CSSProperties}
        />
      </div>
      <div className="slider-hints">
        <span>{format ? format(min) : min}</span>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  )
}

function SaveFeedback({ show }: { show: boolean }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.span
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0 }}
          className="save-feedback"
        >
          <CheckCircle size={14} />
          Saved
        </motion.span>
      )}
    </AnimatePresence>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { state, dispatch } = useAppStore()
  const settings = state.settings ?? {}

  const [activeTab, setActiveTab] = useState<Tab>('general')
  const [saved, setSaved] = useState<SavedState>({})
  const [showApiKey, setShowApiKey] = useState(false)
  const [localApiKey, setLocalApiKey] = useState(settings.openaiApiKey ?? '')
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  // helper: flash saved indicator
  const flash = (key: string) => {
    setSaved((p) => ({ ...p, [key]: true }))
    setTimeout(() => setSaved((p) => ({ ...p, [key]: false })), 2000)
  }

  const updateSetting = (patch: Record<string, unknown>, flashKey?: string) => {
    dispatch({ type: 'UPDATE_SETTINGS', payload: patch })
    if (flashKey) flash(flashKey)
  }

  // ── General handlers ──────────────────────────────────────────────────────

  const handleExport = () => {
    const docs = state.documents ?? []
    const blob = new Blob([JSON.stringify(docs, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'knowledge-base-export.json'
    a.click()
    URL.revokeObjectURL(url)
    flash('export')
  }

  const handleClearAll = () => {
    if (!confirmClear) {
      setConfirmClear(true)
      return
    }
    localStorage.clear()
    dispatch({ type: 'RESET_STATE' })
    setConfirmClear(false)
    flash('clear')
  }

  // ── API handlers ──────────────────────────────────────────────────────────

  const handleSaveApiKey = () => {
    dispatch({ type: 'UPDATE_SETTINGS', payload: { openaiApiKey: localApiKey } })
    flash('apiKey')
  }

  const handleGenerateKey = () => {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    const rand = Array.from({ length: 24 }, () =>
      chars[Math.floor(Math.random() * chars.length)]
    ).join('')
    const key = `rag_${rand}`
    setLocalApiKey(key)
    dispatch({ type: 'UPDATE_SETTINGS', payload: { openaiApiKey: key } })
    flash('apiKey')
  }

  // ── Tabs config ───────────────────────────────────────────────────────────

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'general', label: 'General', icon: <Settings size={15} /> },
    { id: 'models', label: 'AI Models', icon: <Cpu size={15} /> },
    { id: 'api', label: 'API & Security', icon: <Key size={15} /> },
  ]

  const MODELS = [
    {
      id: 'gpt-4o',
      label: 'GPT-4o',
      provider: 'OpenAI',
      desc: 'Most capable, multimodal',
    },
    {
      id: 'claude-3-5-sonnet',
      label: 'Claude 3.5 Sonnet',
      provider: 'Anthropic',
      desc: 'Excellent reasoning, long context',
    },
    {
      id: 'gpt-3.5-turbo',
      label: 'GPT-3.5 Turbo',
      provider: 'OpenAI',
      desc: 'Fast, cost-effective',
    },
    {
      id: 'ollama',
      label: 'Local (Ollama)',
      provider: 'Self-hosted',
      desc: 'Private, runs on your machine',
    },
  ]

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <>
      <style>{`
        /* ── Layout ── */
        .settings-page {
          max-width: 780px;
          margin: 0 auto;
          padding: 2rem 1.5rem 4rem;
          font-family: 'Inter', system-ui, sans-serif;
        }

        .page-header {
          margin-bottom: 2rem;
        }
        .page-title {
          font-size: 1.75rem;
          font-weight: 700;
          color: #f1f5f9;
          margin: 0 0 .25rem;
        }
        .page-subtitle {
          color: #64748b;
          font-size: .9rem;
          margin: 0;
        }

        /* ── Tabs ── */
        .tab-bar {
          display: flex;
          gap: .5rem;
          margin-bottom: 2rem;
          background: rgba(255,255,255,.03);
          border: 1px solid rgba(255,255,255,.07);
          border-radius: 12px;
          padding: .375rem;
        }
        .tab-btn {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: .45rem;
          padding: .6rem .5rem;
          border: none;
          border-radius: 9px;
          background: transparent;
          color: #64748b;
          font-size: .85rem;
          font-weight: 500;
          cursor: pointer;
          transition: color .2s, background .2s;
          position: relative;
        }
        .tab-btn:hover { color: #a5b4fc; }
        .tab-btn.active {
          color: #a5b4fc;
          background: rgba(99,102,241,.18);
        }

        /* ── Glass card ── */
        .glass-card {
          background: rgba(255,255,255,.04);
          border: 1px solid rgba(255,255,255,.08);
          border-radius: 16px;
          padding: 1.75rem;
          margin-bottom: 1.25rem;
          backdrop-filter: blur(12px);
        }
        .card-title {
          font-size: 1rem;
          font-weight: 600;
          color: #e2e8f0;
          margin: 0 0 1.25rem;
          display: flex;
          align-items: center;
          gap: .5rem;
        }
        .card-title svg { color: #818cf8; }

        /* ── Form fields ── */
        .settings-field { margin-bottom: 1.4rem; }
        .settings-field:last-child { margin-bottom: 0; }
        .field-label {
          display: block;
          font-size: .825rem;
          font-weight: 500;
          color: #94a3b8;
          margin-bottom: .5rem;
          letter-spacing: .02em;
          text-transform: uppercase;
        }
        .field-label-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: .5rem;
        }
        .field-value {
          font-size: .85rem;
          font-weight: 600;
          color: #a5b4fc;
          background: rgba(99,102,241,.12);
          padding: .15rem .55rem;
          border-radius: 6px;
        }

        .text-input {
          width: 100%;
          background: rgba(255,255,255,.05);
          border: 1px solid rgba(255,255,255,.1);
          border-radius: 10px;
          padding: .65rem .9rem;
          color: #f1f5f9;
          font-size: .9rem;
          outline: none;
          transition: border-color .2s, box-shadow .2s;
          box-sizing: border-box;
        }
        .text-input:focus {
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99,102,241,.15);
        }
        .number-input {
          width: 140px;
          background: rgba(255,255,255,.05);
          border: 1px solid rgba(255,255,255,.1);
          border-radius: 10px;
          padding: .65rem .9rem;
          color: #f1f5f9;
          font-size: .9rem;
          outline: none;
          transition: border-color .2s, box-shadow .2s;
          box-sizing: border-box;
        }
        .number-input:focus {
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99,102,241,.15);
        }

        /* ── Slider ── */
        .slider-track-wrap { padding: .25rem 0; }
        .slider-input {
          -webkit-appearance: none;
          appearance: none;
          width: 100%;
          height: 6px;
          border-radius: 3px;
          background: linear-gradient(
            to right,
            #6366f1 0%,
            #6366f1 var(--pct, 0%),
            rgba(255,255,255,.1) var(--pct, 0%),
            rgba(255,255,255,.1) 100%
          );
          outline: none;
          cursor: pointer;
        }
        .slider-input::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: #818cf8;
          border: 2px solid #1e1b4b;
          box-shadow: 0 0 8px rgba(99,102,241,.6);
          transition: transform .15s;
        }
        .slider-input::-webkit-slider-thumb:hover { transform: scale(1.2); }
        .slider-hints {
          display: flex;
          justify-content: space-between;
          font-size: .75rem;
          color: #475569;
          margin-top: .3rem;
        }

        /* ── Buttons ── */
        .btn {
          display: inline-flex;
          align-items: center;
          gap: .45rem;
          padding: .6rem 1.1rem;
          border-radius: 10px;
          font-size: .85rem;
          font-weight: 500;
          cursor: pointer;
          border: none;
          transition: all .2s;
        }
        .btn-primary {
          background: linear-gradient(135deg, #6366f1, #818cf8);
          color: #fff;
          box-shadow: 0 4px 15px rgba(99,102,241,.3);
        }
        .btn-primary:hover {
          background: linear-gradient(135deg, #4f46e5, #6366f1);
          transform: translateY(-1px);
          box-shadow: 0 6px 20px rgba(99,102,241,.4);
        }
        .btn-ghost {
          background: rgba(255,255,255,.05);
          border: 1px solid rgba(255,255,255,.1);
          color: #94a3b8;
        }
        .btn-ghost:hover {
          background: rgba(255,255,255,.1);
          color: #e2e8f0;
        }
        .btn-danger {
          background: rgba(239,68,68,.12);
          border: 1px solid rgba(239,68,68,.25);
          color: #f87171;
        }
        .btn-danger:hover {
          background: rgba(239,68,68,.22);
          border-color: rgba(239,68,68,.5);
        }
        .btn-danger-confirm {
          background: #dc2626;
          border: none;
          color: #fff;
        }
        .btn-danger-confirm:hover { background: #b91c1c; }
        .btn-row {
          display: flex;
          gap: .75rem;
          flex-wrap: wrap;
          align-items: center;
          margin-top: 1rem;
        }

        /* ── Save feedback ── */
        .save-feedback {
          display: inline-flex;
          align-items: center;
          gap: .3rem;
          font-size: .8rem;
          color: #34d399;
          font-weight: 500;
        }

        /* ── Model radio cards ── */
        .model-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: .75rem;
        }
        @media (max-width: 520px) { .model-grid { grid-template-columns: 1fr; } }
        .model-card {
          position: relative;
          border: 1.5px solid rgba(255,255,255,.08);
          border-radius: 12px;
          padding: 1rem 1rem 1rem 2.75rem;
          cursor: pointer;
          transition: border-color .2s, background .2s;
          background: rgba(255,255,255,.03);
        }
        .model-card:hover {
          border-color: rgba(99,102,241,.4);
          background: rgba(99,102,241,.07);
        }
        .model-card.selected {
          border-color: #6366f1;
          background: rgba(99,102,241,.12);
          box-shadow: 0 0 0 1px rgba(99,102,241,.3) inset;
        }
        .model-radio {
          position: absolute;
          left: .85rem;
          top: 50%;
          transform: translateY(-50%);
          width: 16px;
          height: 16px;
          border-radius: 50%;
          border: 2px solid rgba(255,255,255,.2);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: border-color .2s;
        }
        .model-card.selected .model-radio {
          border-color: #6366f1;
        }
        .model-radio-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #6366f1;
        }
        .model-name {
          font-size: .9rem;
          font-weight: 600;
          color: #e2e8f0;
          margin-bottom: .15rem;
        }
        .model-provider {
          font-size: .75rem;
          color: #818cf8;
          margin-bottom: .25rem;
        }
        .model-desc { font-size: .78rem; color: #64748b; }

        /* ── Notice banner ── */
        .notice-banner {
          display: flex;
          gap: .75rem;
          align-items: flex-start;
          padding: .9rem 1rem;
          border-radius: 12px;
          background: rgba(99,102,241,.1);
          border: 1px solid rgba(99,102,241,.2);
          color: #a5b4fc;
          font-size: .85rem;
          line-height: 1.5;
          margin-top: 1.25rem;
        }
        .notice-banner svg { flex-shrink: 0; margin-top: 2px; color: #818cf8; }

        /* ── API key row ── */
        .api-key-row {
          display: flex;
          gap: .6rem;
          align-items: stretch;
        }
        .api-key-input-wrap {
          position: relative;
          flex: 1;
        }
        .api-key-input {
          width: 100%;
          background: rgba(255,255,255,.05);
          border: 1px solid rgba(255,255,255,.1);
          border-radius: 10px;
          padding: .65rem 2.6rem .65rem .9rem;
          color: #f1f5f9;
          font-size: .9rem;
          font-family: 'JetBrains Mono', monospace;
          outline: none;
          transition: border-color .2s, box-shadow .2s;
          box-sizing: border-box;
        }
        .api-key-input:focus {
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99,102,241,.15);
        }
        .eye-btn {
          position: absolute;
          right: .65rem;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          color: #64748b;
          cursor: pointer;
          display: flex;
          padding: 0;
          transition: color .2s;
        }
        .eye-btn:hover { color: #a5b4fc; }

        /* ── Security info ── */
        .info-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: .75rem;
        }
        .info-tile {
          background: rgba(255,255,255,.04);
          border: 1px solid rgba(255,255,255,.07);
          border-radius: 10px;
          padding: .85rem 1rem;
        }
        .info-tile-label { font-size: .75rem; color: #475569; margin-bottom: .3rem; text-transform: uppercase; letter-spacing: .05em; }
        .info-tile-value { font-size: .9rem; font-weight: 600; color: #e2e8f0; }
        .badge-green {
          display: inline-block;
          background: rgba(52,211,153,.15);
          color: #34d399;
          font-size: .75rem;
          padding: .1rem .5rem;
          border-radius: 20px;
          font-weight: 600;
        }

        /* ── Danger zone ── */
        .danger-zone {
          border: 1px solid rgba(239,68,68,.2);
          border-radius: 16px;
          padding: 1.5rem 1.75rem;
          background: rgba(239,68,68,.04);
        }
        .danger-title {
          font-size: .95rem;
          font-weight: 600;
          color: #f87171;
          margin: 0 0 .5rem;
          display: flex;
          align-items: center;
          gap: .5rem;
        }
        .danger-desc { font-size: .85rem; color: #64748b; margin-bottom: 1rem; }
      `}</style>

      <div className="settings-page">
        {/* Header */}
        <div className="page-header">
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">
            Manage your workspace, AI models, and security preferences
          </p>
        </div>

        {/* Tab Bar */}
        <div className="tab-bar" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={activeTab === t.id}
              className={`tab-btn${activeTab === t.id ? ' active' : ''}`}
              onClick={() => setActiveTab(t.id)}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* ── General Tab ─────────────────────────────────────────────────── */}
        <AnimatePresence mode="wait">
          {activeTab === 'general' && (
            <motion.div
              key="general"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              {/* Organization */}
              <div className="glass-card">
                <p className="card-title">
                  <Settings size={16} /> Workspace
                </p>
                <div className="settings-field">
                  <label className="field-label" htmlFor="org-name">
                    Organization Name
                  </label>
                  <input
                    id="org-name"
                    type="text"
                    className="text-input"
                    value={settings.orgName ?? ''}
                    placeholder="My Organization"
                    onChange={(e) =>
                      updateSetting({ orgName: e.target.value }, 'orgName')
                    }
                  />
                </div>
                <SaveFeedback show={!!saved.orgName} />
              </div>

              {/* Retrieval params */}
              <div className="glass-card">
                <p className="card-title">
                  <Settings size={16} /> Retrieval Parameters
                </p>

                <SliderField
                  label="Chunk Size"
                  value={settings.chunkSize ?? 500}
                  min={100}
                  max={1000}
                  onChange={(v) => updateSetting({ chunkSize: v }, 'chunkSize')}
                />
                <SliderField
                  label="Top-K Results"
                  value={settings.topK ?? 5}
                  min={1}
                  max={20}
                  onChange={(v) => updateSetting({ topK: v }, 'topK')}
                />
                <SliderField
                  label="Temperature"
                  value={settings.temperature ?? 0.7}
                  min={0}
                  max={1}
                  step={0.1}
                  format={(v) => v.toFixed(1)}
                  onChange={(v) =>
                    updateSetting({ temperature: v }, 'temperature')
                  }
                />
              </div>

              {/* Data management */}
              <div className="glass-card">
                <p className="card-title">
                  <Download size={16} /> Data Management
                </p>

                <div className="btn-row" style={{ marginTop: 0 }}>
                  <button className="btn btn-ghost" onClick={handleExport}>
                    <Download size={15} />
                    Export Knowledge Base
                  </button>
                  <SaveFeedback show={!!saved.export} />
                </div>

                <div className="btn-row" style={{ marginTop: '1rem' }}>
                  {!confirmClear ? (
                    <button
                      className="btn btn-danger"
                      onClick={() => setConfirmClear(true)}
                    >
                      <Trash2 size={15} />
                      Clear All Data
                    </button>
                  ) : (
                    <>
                      <button
                        className="btn btn-danger-confirm"
                        onClick={handleClearAll}
                      >
                        <AlertTriangle size={15} />
                        Confirm — Delete Everything
                      </button>
                      <button
                        className="btn btn-ghost"
                        onClick={() => setConfirmClear(false)}
                      >
                        Cancel
                      </button>
                    </>
                  )}
                  <SaveFeedback show={!!saved.clear} />
                </div>
              </div>
            </motion.div>
          )}

          {/* ── AI Models Tab ──────────────────────────────────────────────── */}
          {activeTab === 'models' && (
            <motion.div
              key="models"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              <div className="glass-card">
                <p className="card-title">
                  <Cpu size={16} /> Language Model
                </p>
                <div className="model-grid">
                  {MODELS.map((m) => (
                    <div
                      key={m.id}
                      className={`model-card${
                        (settings.model ?? 'gpt-4o') === m.id ? ' selected' : ''
                      }`}
                      onClick={() => updateSetting({ model: m.id }, 'model')}
                      role="radio"
                      aria-checked={(settings.model ?? 'gpt-4o') === m.id}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === ' ' || e.key === 'Enter')
                          updateSetting({ model: m.id }, 'model')
                      }}
                    >
                      <div className="model-radio">
                        {(settings.model ?? 'gpt-4o') === m.id && (
                          <div className="model-radio-dot" />
                        )}
                      </div>
                      <div className="model-name">{m.label}</div>
                      <div className="model-provider">{m.provider}</div>
                      <div className="model-desc">{m.desc}</div>
                    </div>
                  ))}
                </div>
                <SaveFeedback show={!!saved.model} />
              </div>

              {/* Max tokens */}
              <div className="glass-card">
                <p className="card-title">
                  <Cpu size={16} /> Generation Settings
                </p>
                <div className="settings-field">
                  <label className="field-label" htmlFor="max-tokens">
                    Max Tokens
                  </label>
                  <input
                    id="max-tokens"
                    type="number"
                    className="number-input"
                    min={128}
                    max={32768}
                    step={128}
                    value={settings.maxTokens ?? 2048}
                    onChange={(e) =>
                      updateSetting(
                        { maxTokens: parseInt(e.target.value, 10) },
                        'maxTokens'
                      )
                    }
                  />
                </div>
                <SaveFeedback show={!!saved.maxTokens} />
              </div>

              {/* Backend notice */}
              <div className="notice-banner">
                <Server size={16} />
                <div>
                  <strong>Backend Required</strong> — AI model selection takes
                  effect when connected to the Python backend. Frontend-only
                  mode uses document text search.
                </div>
              </div>
            </motion.div>
          )}

          {/* ── API & Security Tab ─────────────────────────────────────────── */}
          {activeTab === 'api' && (
            <motion.div
              key="api"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              {/* API key */}
              <div className="glass-card">
                <p className="card-title">
                  <Key size={16} /> API Key
                </p>
                <div className="settings-field">
                  <label className="field-label" htmlFor="api-key">
                    OpenAI API Key
                  </label>
                  <div className="api-key-row">
                    <div className="api-key-input-wrap">
                      <input
                        id="api-key"
                        type={showApiKey ? 'text' : 'password'}
                        className="api-key-input"
                        value={localApiKey}
                        placeholder="sk-… or rag_…"
                        onChange={(e) => setLocalApiKey(e.target.value)}
                        autoComplete="off"
                        spellCheck={false}
                      />
                      <button
                        className="eye-btn"
                        onClick={() => setShowApiKey((v) => !v)}
                        aria-label={showApiKey ? 'Hide key' : 'Show key'}
                        type="button"
                      >
                        {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    <button
                      className="btn btn-primary"
                      onClick={handleSaveApiKey}
                    >
                      <Save size={14} />
                      Save
                    </button>
                  </div>
                </div>

                <div className="btn-row" style={{ marginTop: '.5rem' }}>
                  <button className="btn btn-ghost" onClick={handleGenerateKey}>
                    <RefreshCw size={14} />
                    Auto-generate Key
                  </button>
                  <SaveFeedback show={!!saved.apiKey} />
                </div>
              </div>

              {/* Security info */}
              <div className="glass-card">
                <p className="card-title">
                  <Key size={16} /> Session &amp; Security
                </p>
                <div className="info-grid">
                  <div className="info-tile">
                    <div className="info-tile-label">User Role</div>
                    <div className="info-tile-value">
                      {state.user?.role ?? 'Admin'}
                    </div>
                  </div>
                  <div className="info-tile">
                    <div className="info-tile-label">Session Status</div>
                    <div className="info-tile-value">
                      <span className="badge-green">● Active</span>
                    </div>
                  </div>
                  <div className="info-tile">
                    <div className="info-tile-label">Auth Provider</div>
                    <div className="info-tile-value">Local</div>
                  </div>
                  <div className="info-tile">
                    <div className="info-tile-label">API Key Set</div>
                    <div className="info-tile-value">
                      {settings.openaiApiKey ? (
                        <span className="badge-green">✓ Yes</span>
                      ) : (
                        <span style={{ color: '#64748b' }}>No</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Danger zone */}
              <div className="danger-zone">
                <p className="danger-title">
                  <AlertTriangle size={16} /> Danger Zone
                </p>
                <p className="danger-desc">
                  Permanently delete your account and all associated data. This
                  action cannot be undone.
                </p>
                {!confirmDelete ? (
                  <button
                    className="btn btn-danger"
                    onClick={() => setConfirmDelete(true)}
                  >
                    <Trash2 size={15} />
                    Delete Account
                  </button>
                ) : (
                  <div className="btn-row" style={{ marginTop: 0 }}>
                    <button
                      className="btn btn-danger-confirm"
                      onClick={() => {
                        // In a real app: call delete API, then sign out
                        setConfirmDelete(false)
                      }}
                    >
                      <AlertTriangle size={15} />
                      Yes, Delete My Account
                    </button>
                    <button
                      className="btn btn-ghost"
                      onClick={() => setConfirmDelete(false)}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  )
}

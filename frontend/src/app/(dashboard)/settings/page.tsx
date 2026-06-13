'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { User, Bell, Shield, Key, Palette, Globe, Save, Eye, EyeOff } from 'lucide-react'

const tabs = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'api', label: 'API Keys', icon: Key },
  { id: 'appearance', label: 'Appearance', icon: Palette },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('profile')
  const [saved, setSaved] = useState(false)
  const [showKey, setShowKey] = useState(false)

  // Profile state
  const [name, setName] = useState('Admin User')
  const [email, setEmail] = useState('admin@company.com')
  const [org, setOrg] = useState('Acme Corp')
  const [bio, setBio] = useState('')

  // Notifications state
  const [notifs, setNotifs] = useState({
    docIndexed: true,
    docFailed: true,
    weeklyReport: false,
    budgetAlert: true,
    newUser: false,
  })

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-slate-400 text-sm mt-1">Manage your account and workspace preferences</p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar tabs */}
        <div className="w-48 flex-shrink-0">
          <nav className="space-y-1">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  activeTab === tab.id
                    ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/20'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 rounded-xl border border-slate-800 bg-slate-900/50 p-6">
          {activeTab === 'profile' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
              <h2 className="text-white font-semibold text-lg">Profile</h2>

              {/* Avatar */}
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-white text-2xl font-bold">
                  {name[0]}
                </div>
                <div>
                  <button className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white text-sm transition-all">
                    Change avatar
                  </button>
                  <p className="text-xs text-slate-500 mt-1">JPG, PNG or GIF. Max 2MB.</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Full name</label>
                  <input value={name} onChange={e => setName(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Email</label>
                  <input value={email} onChange={e => setEmail(e.target.value)} type="email"
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Organization</label>
                  <input value={org} onChange={e => setOrg(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Role</label>
                  <input value="Administrator" readOnly
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-800/30 border border-slate-700 text-slate-400 text-sm cursor-not-allowed" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Bio</label>
                <textarea value={bio} onChange={e => setBio(e.target.value)} rows={3} placeholder="Tell your team about yourself…"
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm resize-none" />
              </div>
            </motion.div>
          )}

          {activeTab === 'notifications' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
              <h2 className="text-white font-semibold text-lg">Notifications</h2>
              <div className="space-y-4">
                {[
                  { key: 'docIndexed', label: 'Document indexed', desc: 'When a document finishes indexing' },
                  { key: 'docFailed', label: 'Indexing failed', desc: 'When a document fails to process' },
                  { key: 'weeklyReport', label: 'Weekly digest', desc: 'Summary of usage and costs every Monday' },
                  { key: 'budgetAlert', label: 'Budget alerts', desc: 'When monthly spend exceeds 80% of limit' },
                  { key: 'newUser', label: 'New user joined', desc: 'When someone joins your workspace' },
                ].map(item => (
                  <div key={item.key} className="flex items-center justify-between p-4 rounded-xl bg-slate-800/40 border border-slate-800">
                    <div>
                      <div className="text-sm font-medium text-white">{item.label}</div>
                      <div className="text-xs text-slate-500 mt-0.5">{item.desc}</div>
                    </div>
                    <button
                      onClick={() => setNotifs(prev => ({ ...prev, [item.key]: !prev[item.key as keyof typeof prev] }))}
                      className={`relative w-11 h-6 rounded-full transition-colors ${notifs[item.key as keyof typeof notifs] ? 'bg-indigo-500' : 'bg-slate-700'}`}
                    >
                      <div className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform ${notifs[item.key as keyof typeof notifs] ? 'translate-x-5' : ''}`} />
                    </button>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {activeTab === 'security' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
              <h2 className="text-white font-semibold text-lg">Security</h2>
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-800">
                  <div className="text-sm font-medium text-white mb-3">Change Password</div>
                  <div className="space-y-3">
                    <input type="password" placeholder="Current password"
                      className="w-full px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                    <input type="password" placeholder="New password"
                      className="w-full px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                    <input type="password" placeholder="Confirm new password"
                      className="w-full px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                  </div>
                </div>
                <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-800 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-white">Two-Factor Authentication</div>
                    <div className="text-xs text-slate-500 mt-0.5">Add an extra layer of security</div>
                  </div>
                  <button className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-all">Enable 2FA</button>
                </div>
                <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-800">
                  <div className="text-sm font-medium text-white mb-2">Active Sessions</div>
                  <div className="text-xs text-slate-400">Current browser · Windows · Ahmedabad, IN</div>
                  <div className="text-xs text-emerald-400 mt-1">● Active now</div>
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'api' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
              <h2 className="text-white font-semibold text-lg">API Keys</h2>
              <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-800">
                <div className="text-sm font-medium text-white mb-3">Your API Key</div>
                <div className="flex items-center gap-2">
                  <input readOnly value={showKey ? 'rag_sk_live_x7k2mN9pQr4wL8vT3dZs6hJ1' : '•'.repeat(30)}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-slate-300 text-sm font-mono focus:outline-none" />
                  <button onClick={() => setShowKey(v => !v)}
                    className="p-2.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white transition-all">
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <div className="flex gap-2 mt-3">
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText('rag_sk_live_x7k2mN9pQr4wL8vT3dZs6hJ1')
                        .then(() => {
                          const btn = document.getElementById('copy-key-btn')
                          if (btn) { btn.textContent = '✓ Copied!'; setTimeout(() => { btn.textContent = 'Copy key' }, 2000) }
                        })
                        .catch(() => {})
                    }}
                    id="copy-key-btn"
                    className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white text-xs transition-all">Copy key</button>
                  <button className="px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 text-xs transition-all">Regenerate</button>
                </div>
              </div>
              <div className="p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
                <p className="text-xs text-amber-400">⚠ Never expose your API key in client-side code or public repositories.</p>
              </div>
            </motion.div>
          )}

          {activeTab === 'appearance' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
              <h2 className="text-white font-semibold text-lg">Appearance</h2>
              <div className="space-y-4">
                <div>
                  <div className="text-sm font-medium text-slate-300 mb-3">Theme</div>
                  <div className="grid grid-cols-3 gap-3">
                    {['Dark', 'Darker', 'Midnight'].map(t => (
                      <button key={t}
                        className={`p-4 rounded-xl border text-sm font-medium transition-all ${t === 'Dark' ? 'border-indigo-500 text-indigo-400 bg-indigo-500/10' : 'border-slate-700 text-slate-400 hover:border-slate-600'}`}>
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-medium text-slate-300 mb-3">Accent Color</div>
                  <div className="flex gap-3">
                    {['#6366F1', '#8B5CF6', '#06B6D4', '#10B981', '#F59E0B'].map(c => (
                      <button key={c}
                        style={{ background: c }}
                        className="w-8 h-8 rounded-full transition-transform hover:scale-110 focus:ring-2 focus:ring-white focus:outline-none" />
                    ))}
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 rounded-xl bg-slate-800/40 border border-slate-800">
                  <div>
                    <div className="text-sm font-medium text-white">Compact mode</div>
                    <div className="text-xs text-slate-500 mt-0.5">Reduce spacing for more content</div>
                  </div>
                  <div className="relative w-11 h-6 rounded-full bg-slate-700">
                    <div className="absolute top-1 left-1 w-4 h-4 rounded-full bg-white" />
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* Save button */}
          <div className="mt-6 pt-6 border-t border-slate-800 flex justify-end">
            <button onClick={handleSave}
              className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition-all flex items-center gap-2 shadow-lg shadow-indigo-600/30">
              <Save className="w-4 h-4" />
              {saved ? '✓ Saved!' : 'Save changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

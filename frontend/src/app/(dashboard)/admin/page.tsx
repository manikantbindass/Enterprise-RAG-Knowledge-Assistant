'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Users, Shield, Activity, Plus, Search, Trash2, CheckCircle, AlertCircle, Clock, BarChart3 } from 'lucide-react'
import { useAppStore, relativeTime, isToday, AppUser } from '@/lib/store'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.08, duration: 0.45, ease: 'easeOut' } }),
}

function initials(name: string) {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

function RoleBadge({ role }: { role: string }) {
  const colors: Record<string, string> = {
    admin: 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40',
    manager: 'bg-purple-500/20 text-purple-300 border border-purple-500/40',
    user: 'bg-slate-500/20 text-slate-300 border border-slate-500/40',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${colors[role] ?? colors.user}`}>
      {role}
    </span>
  )
}

interface InviteForm {
  name: string
  email: string
  role: 'user' | 'manager' | 'admin'
  department: string
}

export default function AdminPage() {
  const { state, dispatch } = useAppStore()
  const [activeTab, setActiveTab] = useState<'users' | 'security' | 'analytics'>('users')
  const [search, setSearch] = useState('')
  const [showInvite, setShowInvite] = useState(false)
  const [form, setForm] = useState<InviteForm>({ name: '', email: '', role: 'user', department: '' })
  const [formError, setFormError] = useState('')

  // Current logged-in user from localStorage
  const currentUserRaw = typeof window !== 'undefined' ? localStorage.getItem('rag_user') : null
  const currentUser: AppUser | null = currentUserRaw ? JSON.parse(currentUserRaw) : null

  // Users list: always include current user at top, then store users
  const storeUsers: AppUser[] = state.users ?? []
  const allUsers: AppUser[] = currentUser
    ? [currentUser, ...storeUsers.filter(u => u.id !== currentUser.id)]
    : storeUsers

  const filtered = allUsers.filter(u => {
    const q = search.toLowerCase()
    return (
      u.name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.department ?? '').toLowerCase().includes(q)
    )
  })

  function handleInvite() {
    if (!form.name.trim()) { setFormError('Name is required.'); return }
    if (!form.email.trim()) { setFormError('Email is required.'); return }
    setFormError('')
    const newUser: AppUser = {
      id: `user_${Date.now()}`,
      name: form.name.trim(),
      email: form.email.trim(),
      role: form.role,
      department: form.department.trim() || undefined,
      active: true,
      queryCount: 0,
      joinedAt: new Date().toISOString(),
    }
    dispatch({ type: 'ADD_USER', payload: newUser })
    setForm({ name: '', email: '', role: 'user', department: '' })
    setShowInvite(false)
  }

  function toggleActive(id: string) {
    dispatch({ type: 'TOGGLE_USER_ACTIVE', payload: { id } })
  }

  function deleteUser(id: string) {
    dispatch({ type: 'DELETE_USER', payload: { id } })
  }

  // Analytics
  const logs = state.queryLogs ?? []
  const documents = state.documents ?? []
  const totalQueries = logs.length
  const queriesToday = logs.filter(q => isToday(q.timestamp)).length
  const indexedDocs = documents.filter((d: any) => d.status === 'indexed').length
  const avgResponse =
    logs.length > 0
      ? Math.round(logs.reduce((s: number, q: any) => s + (q.responseMs ?? 0), 0) / logs.length)
      : 0

  // Top 5 topics by first word of query
  const topicMap: Record<string, number> = {}
  logs.forEach((q: any) => {
    const word = (q.query ?? '').trim().split(/\s+/)[0]?.toLowerCase()
    if (word) topicMap[word] = (topicMap[word] ?? 0) + 1
  })
  const topTopics = Object.entries(topicMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  // Leaderboard
  const leaderboard = [...allUsers].sort((a, b) => (b.queryCount ?? 0) - (a.queryCount ?? 0))

  const tabs = [
    { id: 'users', label: 'Users', icon: Users },
    { id: 'security', label: 'Security', icon: Shield },
    { id: 'analytics', label: 'Usage Analytics', icon: Activity },
  ] as const

  return (
    <div className="min-h-screen bg-[#0a0c14] text-white p-6 md:p-10">
      <motion.div initial="hidden" animate="visible" variants={fadeUp} custom={0}>
        <h1 className="text-3xl font-bold text-white mb-1">Admin Panel</h1>
        <p className="text-slate-400 text-sm mb-8">Manage users, security controls, and system analytics.</p>
      </motion.div>

      {/* Tab Bar */}
      <motion.div initial="hidden" animate="visible" variants={fadeUp} custom={1}
        className="flex gap-2 mb-8 border-b border-white/10 pb-0">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-t-lg text-sm font-semibold transition-all duration-200
              ${activeTab === tab.id
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/40'
                : 'text-slate-400 hover:text-white hover:bg-white/5'}`}
          >
            <tab.icon size={15} />
            {tab.label}
          </button>
        ))}
      </motion.div>

      {/* ───────── USERS ───────── */}
      {activeTab === 'users' && (
        <motion.div initial="hidden" animate="visible" variants={fadeUp} custom={2}>
          {/* Toolbar */}
          <div className="flex flex-col sm:flex-row gap-3 mb-6">
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search by name, email, or department…"
                className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                           placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/40 transition"
              />
            </div>
            <button
              onClick={() => setShowInvite(true)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500
                         text-sm font-semibold text-white transition-all duration-200 shadow-lg shadow-indigo-900/40 whitespace-nowrap"
            >
              <Plus size={15} /> Invite User
            </button>
          </div>

          {/* User List */}
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <Users size={40} className="mb-4 opacity-30" />
              <p className="text-base">No users in the system. Invite your first team member.</p>
            </div>
          ) : (
            <div className="rounded-2xl border border-white/10 overflow-hidden bg-white/[0.03]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-slate-400 text-xs uppercase tracking-wider">
                    <th className="px-5 py-3 text-left font-semibold">User</th>
                    <th className="px-5 py-3 text-left font-semibold hidden md:table-cell">Role</th>
                    <th className="px-5 py-3 text-left font-semibold hidden lg:table-cell">Department</th>
                    <th className="px-5 py-3 text-left font-semibold hidden lg:table-cell">Queries</th>
                    <th className="px-5 py-3 text-left font-semibold hidden xl:table-cell">Joined</th>
                    <th className="px-5 py-3 text-center font-semibold">Status</th>
                    <th className="px-5 py-3 text-center font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((user, i) => (
                    <motion.tr
                      key={user.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="border-b border-white/5 hover:bg-white/[0.04] transition-colors"
                    >
                      {/* Avatar + name + email */}
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-indigo-600/30 border border-indigo-500/40
                                          flex items-center justify-center text-indigo-300 font-bold text-xs flex-shrink-0">
                            {initials(user.name)}
                          </div>
                          <div>
                            <p className="font-semibold text-white leading-tight">
                              {user.name}
                              {currentUser && user.id === currentUser.id && (
                                <span className="ml-2 text-xs text-indigo-400 font-normal">(you)</span>
                              )}
                            </p>
                            <p className="text-slate-400 text-xs">{user.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3 hidden md:table-cell">
                        <RoleBadge role={user.role} />
                      </td>
                      <td className="px-5 py-3 text-slate-300 hidden lg:table-cell">
                        {user.department ?? <span className="text-slate-600">—</span>}
                      </td>
                      <td className="px-5 py-3 text-slate-300 hidden lg:table-cell">
                        {user.queryCount ?? 0}
                      </td>
                      <td className="px-5 py-3 text-slate-400 text-xs hidden xl:table-cell">
                        {user.joinedAt ? relativeTime(user.joinedAt) : '—'}
                      </td>
                      <td className="px-5 py-3 text-center">
                        <button
                          onClick={() => toggleActive(user.id)}
                          className={`px-3 py-1 rounded-full text-xs font-semibold border transition-all duration-200
                            ${user.active !== false
                              ? 'bg-green-500/15 text-green-400 border-green-500/30 hover:bg-green-500/25'
                              : 'bg-slate-700/40 text-slate-500 border-slate-600/40 hover:bg-slate-700/60'}`}
                        >
                          {user.active !== false ? 'Active' : 'Inactive'}
                        </button>
                      </td>
                      <td className="px-5 py-3 text-center">
                        <button
                          onClick={() => deleteUser(user.id)}
                          disabled={currentUser?.id === user.id}
                          title={currentUser?.id === user.id ? "Can't delete yourself" : 'Delete user'}
                          className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10
                                     disabled:opacity-25 disabled:cursor-not-allowed transition-all duration-200"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </motion.div>
      )}

      {/* ───────── SECURITY ───────── */}
      {activeTab === 'security' && (
        <motion.div initial="hidden" animate="visible" variants={fadeUp} custom={2}
          className="grid gap-4 max-w-2xl">
          <h2 className="text-lg font-bold text-white flex items-center gap-2 mb-2">
            <Shield size={18} className="text-indigo-400" /> Security Controls
          </h2>
          {[
            {
              label: 'Auth Protection',
              desc: 'Middleware protects all routes',
              status: 'active' as const,
            },
            {
              label: 'Session Cookies',
              desc: 'HttpOnly secure session cookies',
              status: 'active' as const,
            },
            {
              label: 'RBAC',
              desc: 'Role-based access control enforced',
              status: 'active' as const,
            },
            {
              label: 'Audit Logging',
              desc: `${logs.length} quer${logs.length === 1 ? 'y' : 'ies'} logged`,
              status: 'active' as const,
            },
            {
              label: 'API Rate Limiting',
              desc: 'Requires backend',
              status: 'backend' as const,
            },
            {
              label: 'PII Masking',
              desc: 'Requires backend',
              status: 'backend' as const,
            },
            {
              label: 'Prompt Injection Defense',
              desc: 'Requires backend',
              status: 'backend' as const,
            },
          ].map((ctrl, i) => (
            <motion.div
              key={ctrl.label}
              initial={{ opacity: 0, x: -16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06 }}
              className="flex items-center justify-between px-5 py-4 rounded-xl bg-white/[0.04]
                         border border-white/10 hover:border-white/20 transition-all duration-200"
            >
              <div className="flex items-center gap-3">
                {ctrl.status === 'active' ? (
                  <CheckCircle size={18} className="text-green-400 flex-shrink-0" />
                ) : (
                  <Clock size={18} className="text-amber-400 flex-shrink-0" />
                )}
                <div>
                  <p className="font-semibold text-white text-sm">{ctrl.label}</p>
                  <p className="text-slate-400 text-xs">{ctrl.desc}</p>
                </div>
              </div>
              {ctrl.status === 'active' ? (
                <span className="px-3 py-1 rounded-full text-xs font-semibold
                                 bg-green-500/15 text-green-400 border border-green-500/30">
                  Active
                </span>
              ) : (
                <span className="px-3 py-1 rounded-full text-xs font-semibold
                                 bg-amber-500/15 text-amber-400 border border-amber-500/30">
                  Requires backend
                </span>
              )}
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* ───────── USAGE ANALYTICS ───────── */}
      {activeTab === 'analytics' && (
        <motion.div initial="hidden" animate="visible" variants={fadeUp} custom={2} className="space-y-8">
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Total Queries', value: totalQueries, icon: BarChart3, color: 'indigo' },
              { label: 'Queries Today', value: queriesToday, icon: Activity, color: 'purple' },
              { label: 'Docs in KB', value: indexedDocs, icon: Shield, color: 'sky' },
              { label: 'Avg Response', value: `${avgResponse} ms`, icon: Clock, color: 'emerald' },
            ].map((kpi, i) => (
              <motion.div
                key={kpi.label}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.07 }}
                className="rounded-2xl bg-white/[0.04] border border-white/10 p-5
                           hover:border-indigo-500/40 hover:bg-white/[0.07] transition-all duration-300"
              >
                <p className="text-slate-400 text-xs mb-3">{kpi.label}</p>
                <p className="text-3xl font-bold text-white">{kpi.value}</p>
              </motion.div>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Top Topics */}
            <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-6">
              <h3 className="text-sm font-bold text-slate-300 mb-4 flex items-center gap-2">
                <BarChart3 size={14} className="text-indigo-400" /> Top 5 Topics
              </h3>
              {topTopics.length === 0 ? (
                <p className="text-slate-500 text-sm py-6 text-center">No queries yet.</p>
              ) : (
                <div className="space-y-3">
                  {topTopics.map(([topic, count], i) => {
                    const max = topTopics[0][1]
                    const pct = Math.round((count / max) * 100)
                    return (
                      <div key={topic}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-300 capitalize font-medium">{topic}</span>
                          <span className="text-slate-500">{count} queries</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ delay: i * 0.1, duration: 0.6, ease: 'easeOut' }}
                            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500"
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Leaderboard */}
            <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-6">
              <h3 className="text-sm font-bold text-slate-300 mb-4 flex items-center gap-2">
                <Users size={14} className="text-indigo-400" /> User Query Leaderboard
              </h3>
              {leaderboard.length === 0 ? (
                <p className="text-slate-500 text-sm py-6 text-center">No users yet.</p>
              ) : (
                <div className="space-y-3">
                  {leaderboard.slice(0, 8).map((user, i) => (
                    <div key={user.id} className="flex items-center gap-3">
                      <span className={`w-5 text-xs font-bold text-center ${
                        i === 0 ? 'text-yellow-400' : i === 1 ? 'text-slate-300' : i === 2 ? 'text-orange-400' : 'text-slate-600'
                      }`}>
                        {i + 1}
                      </span>
                      <div className="w-7 h-7 rounded-full bg-indigo-600/30 border border-indigo-500/30
                                      flex items-center justify-center text-indigo-300 font-bold text-xs flex-shrink-0">
                        {initials(user.name)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-xs font-semibold truncate">{user.name}</p>
                        <p className="text-slate-500 text-xs truncate">{user.email}</p>
                      </div>
                      <span className="text-indigo-300 text-xs font-semibold">
                        {user.queryCount ?? 0}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}

      {/* ───────── INVITE MODAL ───────── */}
      {showInvite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={e => { if (e.target === e.currentTarget) setShowInvite(false) }}>
          <motion.div
            initial={{ opacity: 0, scale: 0.93, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="bg-[#12151f] border border-white/15 rounded-2xl p-7 w-full max-w-md shadow-2xl"
          >
            <h2 className="text-lg font-bold text-white mb-5 flex items-center gap-2">
              <Plus size={18} className="text-indigo-400" /> Invite Team Member
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-xs text-slate-400 mb-1.5 font-medium">Full Name <span className="text-red-400">*</span></label>
                <input
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Jane Smith"
                  className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                             placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1
                             focus:ring-indigo-500/40 transition"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1.5 font-medium">Email <span className="text-red-400">*</span></label>
                <input
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  placeholder="jane@company.com"
                  type="email"
                  className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                             placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1
                             focus:ring-indigo-500/40 transition"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1.5 font-medium">Role</label>
                <select
                  value={form.role}
                  onChange={e => setForm(f => ({ ...f, role: e.target.value as InviteForm['role'] }))}
                  className="w-full px-4 py-2.5 rounded-xl bg-[#0f1219] border border-white/10 text-sm text-white
                             focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/40 transition"
                >
                  <option value="user">User</option>
                  <option value="manager">Manager</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1.5 font-medium">Department</label>
                <input
                  value={form.department}
                  onChange={e => setForm(f => ({ ...f, department: e.target.value }))}
                  placeholder="Engineering, HR, Finance…"
                  className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                             placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1
                             focus:ring-indigo-500/40 transition"
                />
              </div>

              {formError && (
                <div className="flex items-center gap-2 text-red-400 text-xs bg-red-500/10 px-3 py-2 rounded-lg border border-red-500/20">
                  <AlertCircle size={13} /> {formError}
                </div>
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => { setShowInvite(false); setFormError('') }}
                className="flex-1 px-4 py-2.5 rounded-xl bg-white/5 border border-white/10
                           text-sm text-slate-300 hover:text-white hover:bg-white/10 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleInvite}
                className="flex-1 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500
                           text-sm font-semibold text-white transition shadow-lg shadow-indigo-900/40"
              >
                Send Invite
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  )
}

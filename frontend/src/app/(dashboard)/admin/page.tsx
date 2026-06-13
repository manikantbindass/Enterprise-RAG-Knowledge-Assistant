'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { Users, Shield, Activity, DollarSign, Trash2, UserCheck, UserX, Search, Plus } from 'lucide-react'

const mockUsers = [
  { id: 1, name: 'Sarah Kim', email: 'sarah@acme.com', role: 'admin', dept: 'Legal', status: 'active', joined: '3 months ago', queries: 1240 },
  { id: 2, name: 'John Doe', email: 'john@acme.com', role: 'user', dept: 'Finance', status: 'active', joined: '1 month ago', queries: 890 },
  { id: 3, name: 'Mike Ross', email: 'mike@acme.com', role: 'user', dept: 'IT', status: 'active', joined: '2 months ago', queries: 654 },
  { id: 4, name: 'Emma Li', email: 'emma@acme.com', role: 'manager', dept: 'HR', status: 'active', joined: '5 months ago', queries: 432 },
  { id: 5, name: 'Alex T.', email: 'alex@acme.com', role: 'user', dept: 'Sales', status: 'inactive', joined: '2 weeks ago', queries: 21 },
  { id: 6, name: 'Nina Patel', email: 'nina@acme.com', role: 'user', dept: 'Product', status: 'active', joined: '1 week ago', queries: 87 },
]

const roleBadge: Record<string, string> = {
  admin:   'bg-indigo-400/10 text-indigo-400 border-indigo-400/20',
  manager: 'bg-violet-400/10 text-violet-400 border-violet-400/20',
  user:    'bg-slate-400/10 text-slate-400 border-slate-400/20',
}

export default function AdminPage() {
  const [users, setUsers] = useState(mockUsers)
  const [search, setSearch] = useState('')
  const [activeSection, setActiveSection] = useState('users')
  const [showInvite, setShowInvite] = useState(false)
  const [inviteForm, setInviteForm] = useState({ name: '', email: '', role: 'user', dept: '' })
  const [inviteSent, setInviteSent] = useState(false)

  const handleInvite = (e: React.FormEvent) => {
    e.preventDefault()
    const newUser = {
      id: Date.now(),
      name: inviteForm.name,
      email: inviteForm.email,
      role: inviteForm.role,
      dept: inviteForm.dept || 'General',
      status: 'active' as const,
      joined: 'Just now',
      queries: 0,
    }
    setUsers(prev => [newUser, ...prev])
    setInviteSent(true)
    setTimeout(() => {
      setShowInvite(false)
      setInviteSent(false)
      setInviteForm({ name: '', email: '', role: 'user', dept: '' })
    }, 1500)
  }

  const sections = [
    { id: 'users', label: 'User Management', icon: Users },
    { id: 'security', label: 'Security & Access', icon: Shield },
    { id: 'usage', label: 'Usage & Costs', icon: Activity },
  ]

  const filtered = users.filter(u =>
    u.name.toLowerCase().includes(search.toLowerCase()) ||
    u.email.toLowerCase().includes(search.toLowerCase()) ||
    u.dept.toLowerCase().includes(search.toLowerCase())
  )

  const toggleStatus = (id: number) => {
    setUsers(prev => prev.map(u => u.id === id ? { ...u, status: u.status === 'active' ? 'inactive' : 'active' } : u))
  }

  const deleteUser = (id: number) => {
    setUsers(prev => prev.filter(u => u.id !== id))
  }

  return (
    <>
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Admin Panel</h1>
          <p className="text-slate-400 text-sm mt-1">Manage users, security, and workspace settings</p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
          <Shield className="w-4 h-4 text-indigo-400" />
          <span className="text-xs text-indigo-400 font-medium">Administrator</span>
        </div>
      </div>

      {/* Section Tabs */}
      <div className="flex gap-2">
        {sections.map(s => (
          <button key={s.id} onClick={() => setActiveSection(s.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              activeSection === s.id
                ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/20'
                : 'text-slate-400 hover:text-white bg-slate-800/40 border border-slate-800'
            }`}>
            <s.icon className="w-4 h-4" />
            {s.label}
          </button>
        ))}
      </div>

      {/* User Management */}
      {activeSection === 'users' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: 'Total Users', value: users.length, color: 'text-white' },
              { label: 'Active', value: users.filter(u => u.status === 'active').length, color: 'text-emerald-400' },
              { label: 'Admins', value: users.filter(u => u.role === 'admin').length, color: 'text-indigo-400' },
              { label: 'Inactive', value: users.filter(u => u.status === 'inactive').length, color: 'text-slate-400' },
            ].map(s => (
              <div key={s.label} className="p-4 rounded-xl border border-slate-800 bg-slate-900/50">
                <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                <div className="text-xs text-slate-500 mt-1">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Search + Invite */}
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input type="text" placeholder="Search users…" value={search} onChange={e => setSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
            </div>
            <button onClick={() => setShowInvite(true)} className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all flex items-center gap-2">
              <Plus className="w-4 h-4" /> Invite User
            </button>
          </div>

          {/* Users Table */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden">
            <div className="grid grid-cols-12 gap-4 px-5 py-3 border-b border-slate-800 text-xs font-medium text-slate-500 uppercase tracking-wide">
              <div className="col-span-3">User</div>
              <div className="col-span-2">Department</div>
              <div className="col-span-2">Role</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-1">Queries</div>
              <div className="col-span-1">Joined</div>
              <div className="col-span-1"></div>
            </div>
            <div className="divide-y divide-slate-800">
              {filtered.map((user, i) => (
                <motion.div key={user.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.03 }}
                  className="grid grid-cols-12 gap-4 px-5 py-4 items-center hover:bg-slate-800/30 transition-colors group"
                >
                  <div className="col-span-3 flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                      {user.name[0]}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm text-white font-medium truncate">{user.name}</div>
                      <div className="text-xs text-slate-500 truncate">{user.email}</div>
                    </div>
                  </div>
                  <div className="col-span-2 text-sm text-slate-400">{user.dept}</div>
                  <div className="col-span-2">
                    <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium border ${roleBadge[user.role]}`}>
                      {user.role}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${user.status === 'active' ? 'text-emerald-400' : 'text-slate-500'}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${user.status === 'active' ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                      {user.status}
                    </span>
                  </div>
                  <div className="col-span-1 text-sm text-slate-400">{user.queries.toLocaleString()}</div>
                  <div className="col-span-1 text-xs text-slate-500">{user.joined}</div>
                  <div className="col-span-1 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => toggleStatus(user.id)} title={user.status === 'active' ? 'Deactivate' : 'Activate'}
                      className="p-1 text-slate-400 hover:text-amber-400 transition-colors">
                      {user.status === 'active' ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                    </button>
                    <button onClick={() => deleteUser(user.id)} title="Remove user"
                      className="p-1 text-slate-400 hover:text-red-400 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>
      )}

      {/* Security & Access */}
      {activeSection === 'security' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          {[
            { title: 'SSO / SAML', desc: 'Configure single sign-on with your identity provider', status: 'Configured', color: 'emerald' },
            { title: 'RBAC Policies', desc: 'Role-based access control rules for documents and queries', status: 'Active', color: 'emerald' },
            { title: 'IP Allowlist', desc: 'Restrict access to specific IP ranges', status: 'Disabled', color: 'slate' },
            { title: 'Audit Logging', desc: 'Full audit trail of all user actions and queries', status: 'Active', color: 'emerald' },
            { title: 'PII Masking', desc: 'Automatically redact PII in query results', status: 'Active', color: 'emerald' },
            { title: 'Prompt Injection Defense', desc: 'Block malicious prompt injection attempts', status: 'Active', color: 'emerald' },
          ].map(item => (
            <div key={item.title} className="flex items-center justify-between p-4 rounded-xl border border-slate-800 bg-slate-900/50">
              <div>
                <div className="text-sm font-medium text-white">{item.title}</div>
                <div className="text-xs text-slate-500 mt-0.5">{item.desc}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs font-medium ${item.color === 'emerald' ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {item.status}
                </span>
                <button className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white text-xs transition-all">
                  Configure
                </button>
              </div>
            </div>
          ))}
        </motion.div>
      )}

      {/* Usage & Costs */}
      {activeSection === 'usage' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'MTD Spend', value: '$54.50', sub: 'of $500 budget', icon: DollarSign, color: 'text-amber-400' },
              { label: 'Total Queries', value: '48,291', sub: 'this month', icon: Activity, color: 'text-indigo-400' },
              { label: 'Avg Latency', value: '1.4s', sub: 'p95: 2.8s', icon: Activity, color: 'text-emerald-400' },
            ].map(m => (
              <div key={m.label} className="p-5 rounded-xl border border-slate-800 bg-slate-900/50">
                <m.icon className={`w-5 h-5 ${m.color} mb-3`} />
                <div className="text-2xl font-bold text-white">{m.value}</div>
                <div className="text-xs text-slate-500 mt-1">{m.label}</div>
                <div className="text-xs text-slate-600 mt-0.5">{m.sub}</div>
              </div>
            ))}
          </div>
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50">
            <div className="text-sm font-medium text-white mb-4">Cost breakdown by service</div>
            <div className="space-y-3">
              {[
                { label: 'LLM (GPT-4o)', amount: '$38.90', pct: 71 },
                { label: 'Embeddings (OpenAI)', amount: '$12.40', pct: 23 },
                { label: 'Storage (MinIO/S3)', amount: '$3.20', pct: 6 },
              ].map(c => (
                <div key={c.label}>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="text-slate-400">{c.label}</span>
                    <span className="text-white font-medium">{c.amount}</span>
                  </div>
                  <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${c.pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </div>

      {/* Invite User Modal */}
      {showInvite && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl p-6 shadow-2xl"
          >
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-white font-semibold text-lg">Invite User</h3>
              <button onClick={() => setShowInvite(false)} className="p-1 text-slate-400 hover:text-white transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            {inviteSent ? (
              <div className="text-center py-6">
                <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                </div>
                <p className="text-white font-medium">User added!</p>
                <p className="text-slate-400 text-sm mt-1">{inviteForm.name} has been added to the team.</p>
              </div>
            ) : (
              <form onSubmit={handleInvite} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Full name</label>
                  <input value={inviteForm.name} onChange={e => setInviteForm(f => ({ ...f, name: e.target.value }))} required placeholder="Jane Smith"
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Work email</label>
                  <input type="email" value={inviteForm.email} onChange={e => setInviteForm(f => ({ ...f, email: e.target.value }))} required placeholder="jane@company.com"
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">Role</label>
                    <select value={inviteForm.role} onChange={e => setInviteForm(f => ({ ...f, role: e.target.value }))}
                      className="w-full px-4 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm">
                      <option value="user">User</option>
                      <option value="manager">Manager</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">Department</label>
                    <input value={inviteForm.dept} onChange={e => setInviteForm(f => ({ ...f, dept: e.target.value }))} placeholder="e.g. Legal"
                      className="w-full px-4 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm" />
                  </div>
                </div>
                <div className="flex gap-3 pt-2">
                  <button type="button" onClick={() => setShowInvite(false)}
                    className="flex-1 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-300 hover:text-white text-sm font-medium transition-all">Cancel</button>
                  <button type="submit"
                    className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition-all">Add User</button>
                </div>
              </form>
            )}
          </motion.div>
        </div>
      )}
    </>
  )
}

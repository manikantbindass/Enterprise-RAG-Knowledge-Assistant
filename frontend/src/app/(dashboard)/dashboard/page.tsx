'use client'

import { motion } from 'framer-motion'
import { FileText, Search, MessageSquare, Users, TrendingUp, DollarSign, Clock, CheckCircle } from 'lucide-react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import Link from 'next/link'

// Mock data — replace with React Query hooks
const queryData = Array.from({ length: 30 }, (_, i) => ({
  day: `Day ${i + 1}`,
  queries: Math.floor(Math.random() * 500 + 100),
  cost: parseFloat((Math.random() * 5 + 1).toFixed(2)),
}))

const deptData = [
  { dept: 'Legal', docs: 1240 },
  { dept: 'HR', docs: 890 },
  { dept: 'Finance', docs: 760 },
  { dept: 'IT', docs: 540 },
  { dept: 'Sales', docs: 420 },
]

const recentActivity = [
  { user: 'Sarah K.', query: 'What is the vacation policy for remote employees?', latency: '1.2s', time: '2m ago', status: 'success' },
  { user: 'John D.', query: 'Summarize Q3 financial report highlights', latency: '1.8s', time: '5m ago', status: 'success' },
  { user: 'Mike R.', query: 'GDPR compliance requirements for EU data', latency: '2.1s', time: '12m ago', status: 'success' },
  { user: 'Emma L.', query: 'New employee onboarding checklist', latency: '0.9s', time: '18m ago', status: 'success' },
  { user: 'Alex T.', query: 'Contract termination notice period', latency: '1.4s', time: '25m ago', status: 'success' },
]

const metrics = [
  { label: 'Total Documents', value: '24,891', icon: FileText, change: '+12%', color: 'indigo' },
  { label: 'Indexed Today', value: '347', icon: CheckCircle, change: '+8%', color: 'emerald' },
  { label: 'Queries Today', value: '8,432', icon: Search, change: '+23%', color: 'violet' },
  { label: 'Active Users', value: '1,204', icon: Users, change: '+5%', color: 'amber' },
]

const colorMap: Record<string, string> = {
  indigo: 'from-indigo-500/20 to-indigo-600/5 border-indigo-500/20 text-indigo-400',
  emerald: 'from-emerald-500/20 to-emerald-600/5 border-emerald-500/20 text-emerald-400',
  violet: 'from-violet-500/20 to-violet-600/5 border-violet-500/20 text-violet-400',
  amber: 'from-amber-500/20 to-amber-600/5 border-amber-500/20 text-amber-400',
}

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 text-sm mt-1">Welcome back! Here's what's happening.</p>
        </div>
        <div className="flex gap-3">
          <Link href="/documents" className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-600 transition-all text-sm font-medium flex items-center gap-2">
            <FileText className="w-4 h-4" /> Upload Documents
          </Link>
          <Link href="/chat" className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-all text-sm font-medium flex items-center gap-2 shadow-lg shadow-indigo-600/30">
            <MessageSquare className="w-4 h-4" /> Start Chat
          </Link>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((m, i) => (
          <motion.div
            key={m.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className={`p-5 rounded-xl border bg-gradient-to-br ${colorMap[m.color]} backdrop-blur-sm`}
          >
            <div className="flex items-center justify-between mb-3">
              <m.icon className="w-5 h-5 opacity-80" />
              <span className="text-xs text-emerald-400 font-medium bg-emerald-400/10 px-2 py-0.5 rounded-full">{m.change}</span>
            </div>
            <div className="text-2xl font-bold text-white">{m.value}</div>
            <div className="text-xs text-slate-400 mt-1">{m.label}</div>
          </motion.div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Queries over time */}
        <div className="lg:col-span-2 p-5 rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Queries Over Time</h2>
            <div className="flex items-center gap-2 text-slate-400 text-xs">
              <TrendingUp className="w-3 h-3 text-indigo-400" /> Last 30 days
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={queryData}>
              <defs>
                <linearGradient id="queryGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366F1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" />
              <XAxis dataKey="day" tick={{ fill: '#64748B', fontSize: 11 }} tickLine={false} axisLine={false} interval={4} />
              <YAxis tick={{ fill: '#64748B', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: '#1E293B', border: '1px solid #334155', borderRadius: '8px', color: '#F1F5F9' }} />
              <Area type="monotone" dataKey="queries" stroke="#6366F1" fill="url(#queryGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Docs by dept */}
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur-sm">
          <h2 className="text-white font-semibold mb-4">Documents by Department</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={deptData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#64748B', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis dataKey="dept" type="category" tick={{ fill: '#94A3B8', fontSize: 11 }} tickLine={false} axisLine={false} width={50} />
              <Tooltip contentStyle={{ background: '#1E293B', border: '1px solid #334155', borderRadius: '8px', color: '#F1F5F9' }} />
              <Bar dataKey="docs" fill="#6366F1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cost + Activity Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Cost tracking */}
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur-sm">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-amber-400" /> Monthly Costs
          </h2>
          <div className="space-y-3">
            {[
              { label: 'Embedding (OpenAI)', amount: '$12.40', pct: 24 },
              { label: 'LLM (GPT-4o)', amount: '$38.90', pct: 76 },
              { label: 'Storage (S3)', amount: '$3.20', pct: 6 },
            ].map(c => (
              <div key={c.label}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-400">{c.label}</span>
                  <span className="text-white font-medium">{c.amount}</span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${c.pct}%` }} />
                </div>
              </div>
            ))}
            <div className="pt-2 border-t border-slate-800 flex justify-between text-sm">
              <span className="text-slate-400">Total this month</span>
              <span className="text-white font-bold">$54.50 / $500</span>
            </div>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="lg:col-span-2 p-5 rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur-sm">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" /> Recent Activity
          </h2>
          <div className="space-y-3">
            {recentActivity.map((a, i) => (
              <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 hover:bg-slate-800 transition-colors">
                <div className="w-7 h-7 rounded-full bg-indigo-500/20 text-indigo-400 flex items-center justify-center text-xs font-bold flex-shrink-0">
                  {a.user[0]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">{a.query}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{a.user}</div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0 text-xs">
                  <span className="text-slate-400">{a.latency}</span>
                  <span className="text-slate-600">{a.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

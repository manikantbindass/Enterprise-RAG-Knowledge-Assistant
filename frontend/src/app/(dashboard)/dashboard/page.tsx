'use client'
import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { FileText, Search, Users, Zap, Upload, MessageSquare, TrendingUp, ArrowRight, Database } from 'lucide-react'
import { useAppStore, isToday, relativeTime } from '@/lib/store'
import Link from 'next/link'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, delay: i * 0.08, ease: 'easeOut' },
  }),
}

export default function DashboardPage() {
  const { state } = useAppStore()
  const { documents, queryLogs, users } = state

  const isEmpty = documents.length === 0 && queryLogs.length === 0

  // ── Stat values ──────────────────────────────────────────────────────────
  const totalDocs = documents.length
  const indexedToday = useMemo(
    () => documents.filter((d) => isToday(d.uploadedAt)).length,
    [documents]
  )
  const queriesToday = useMemo(
    () => queryLogs.filter((q) => isToday(q.timestamp)).length,
    [queryLogs]
  )
  const activeUsers = users.length > 0 ? users.length : queryLogs.length > 0 ? 1 : 0

  // ── Queries over time (last 30 days) ─────────────────────────────────────
  const queriesOverTime = useMemo(() => {
    const days: Record<string, number> = {}
    const now = new Date()
    for (let i = 29; i >= 0; i--) {
      const d = new Date(now)
      d.setDate(d.getDate() - i)
      const key = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      days[key] = 0
    }
    queryLogs.forEach((q) => {
      const d = new Date(q.timestamp)
      const diff = Math.floor((now.getTime() - d.getTime()) / 86400000)
      if (diff >= 0 && diff < 30) {
        const key = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        if (key in days) days[key]++
      }
    })
    return Object.entries(days).map(([date, count]) => ({ date, count }))
  }, [queryLogs])

  // ── Docs by department ───────────────────────────────────────────────────
  const docsByDept = useMemo(() => {
    const map: Record<string, number> = {}
    documents.forEach((d) => {
      const dept = d.department || 'General'
      map[dept] = (map[dept] || 0) + 1
    })
    return Object.entries(map)
      .map(([dept, count]) => ({ dept, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8)
  }, [documents])

  // ── Recent activity ───────────────────────────────────────────────────────
  const recentActivity = useMemo(
    () => [...queryLogs].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 5),
    [queryLogs]
  )

  // ── Monthly cost estimate ─────────────────────────────────────────────────
  const llmCost = (queryLogs.length * 0.004).toFixed(2)
  const embeddingCost = (documents.length * 0.002).toFixed(2)
  const totalCost = (parseFloat(llmCost) + parseFloat(embeddingCost)).toFixed(2)

  // ── Stat cards config ─────────────────────────────────────────────────────
  const stats = [
    {
      label: 'Total Documents',
      value: totalDocs,
      icon: FileText,
      color: 'from-indigo-500 to-indigo-600',
      bg: 'bg-indigo-500/10',
      border: 'border-indigo-500/20',
    },
    {
      label: 'Indexed Today',
      value: indexedToday,
      icon: Database,
      color: 'from-violet-500 to-violet-600',
      bg: 'bg-violet-500/10',
      border: 'border-violet-500/20',
    },
    {
      label: 'Queries Today',
      value: queriesToday,
      icon: Search,
      color: 'from-sky-500 to-sky-600',
      bg: 'bg-sky-500/10',
      border: 'border-sky-500/20',
    },
    {
      label: 'Active Users',
      value: activeUsers,
      icon: Users,
      color: 'from-emerald-500 to-emerald-600',
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/20',
    },
  ]

  // ── Empty state ───────────────────────────────────────────────────────────
  if (isEmpty) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8 flex flex-col">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-10"
        >
          <h1 className="text-3xl font-bold text-white mb-2">Dashboard</h1>
          <p className="text-slate-400">Your knowledge assistant workspace</p>
        </motion.div>

        {/* Empty hero */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="flex flex-col items-center justify-center flex-1 text-center py-16"
        >
          <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/30 flex items-center justify-center mb-6 shadow-lg shadow-indigo-500/10">
            <Zap className="w-12 h-12 text-indigo-400" />
          </div>
          <h2 className="text-2xl font-semibold text-white mb-3">Your workspace is ready</h2>
          <p className="text-slate-400 max-w-md mb-12 leading-relaxed">
            Start by uploading documents to your knowledge base or jump straight into a conversation. Stats and charts will appear here as you use the assistant.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 w-full max-w-xl">
            {[
              {
                href: '/documents',
                icon: Upload,
                title: 'Upload Your First Document',
                desc: 'Add PDFs, Word docs, or text files to the knowledge base.',
                gradient: 'from-indigo-500 to-violet-500',
                border: 'border-indigo-500/30 hover:border-indigo-400/60',
              },
              {
                href: '/chat',
                icon: MessageSquare,
                title: 'Start a Conversation',
                desc: 'Ask questions and get AI-powered answers from your docs.',
                gradient: 'from-emerald-500 to-teal-500',
                border: 'border-emerald-500/30 hover:border-emerald-400/60',
              },
            ].map((card, i) => (
              <motion.div
                key={card.href}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="show"
              >
                <Link href={card.href}>
                  <div
                    className={`group relative rounded-2xl bg-slate-900/80 border ${card.border} p-6 text-left transition-all duration-300 hover:bg-slate-800/80 hover:shadow-xl cursor-pointer`}
                  >
                    <div
                      className={`w-12 h-12 rounded-xl bg-gradient-to-br ${card.gradient} flex items-center justify-center mb-4 shadow-lg`}
                    >
                      <card.icon className="w-6 h-6 text-white" />
                    </div>
                    <h3 className="text-white font-semibold mb-1">{card.title}</h3>
                    <p className="text-slate-400 text-sm leading-relaxed">{card.desc}</p>
                    <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-white group-hover:translate-x-1 transition-all duration-200 mt-3" />
                  </div>
                </Link>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    )
  }

  // ── Full dashboard ────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-950 text-white p-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mb-8"
      >
        <h1 className="text-3xl font-bold text-white mb-1">Dashboard</h1>
        <p className="text-slate-400">Real-time overview of your knowledge assistant</p>
      </motion.div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            custom={i}
            variants={fadeUp}
            initial="hidden"
            animate="show"
            className={`rounded-2xl bg-slate-900/70 border ${s.border} p-5 flex flex-col gap-3 backdrop-blur-sm`}
          >
            <div className={`w-10 h-10 rounded-xl ${s.bg} flex items-center justify-center`}>
              <s.icon className={`w-5 h-5 bg-gradient-to-br ${s.color} bg-clip-text`} style={{ color: 'transparent', WebkitBackgroundClip: 'text' }} />
            </div>
            <div>
              <p className="text-3xl font-bold text-white tabular-nums">{s.value.toLocaleString()}</p>
              <p className="text-slate-400 text-sm mt-0.5">{s.label}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Queries over time */}
        <motion.div
          custom={4}
          variants={fadeUp}
          initial="hidden"
          animate="show"
          className="rounded-2xl bg-slate-900/70 border border-slate-700/40 p-6"
        >
          <div className="flex items-center gap-2 mb-5">
            <TrendingUp className="w-4 h-4 text-indigo-400" />
            <h2 className="text-white font-semibold">Queries Over Time</h2>
            <span className="ml-auto text-xs text-slate-500">Last 30 days</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={queriesOverTime} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                interval={6}
              />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 10, color: '#f1f5f9' }}
                labelStyle={{ color: '#94a3b8' }}
                cursor={{ stroke: '#6366f1', strokeWidth: 1 }}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, fill: '#6366f1' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Docs by department */}
        <motion.div
          custom={5}
          variants={fadeUp}
          initial="hidden"
          animate="show"
          className="rounded-2xl bg-slate-900/70 border border-slate-700/40 p-6"
        >
          <div className="flex items-center gap-2 mb-5">
            <FileText className="w-4 h-4 text-violet-400" />
            <h2 className="text-white font-semibold">Documents by Department</h2>
          </div>
          {docsByDept.length === 0 ? (
            <div className="flex items-center justify-center h-[200px] text-slate-500 text-sm">
              No department data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={docsByDept} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="dept"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 10, color: '#f1f5f9' }}
                  labelStyle={{ color: '#94a3b8' }}
                  cursor={{ fill: '#6366f110' }}
                />
                <Bar dataKey="count" fill="#7c3aed" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </motion.div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent activity */}
        <motion.div
          custom={6}
          variants={fadeUp}
          initial="hidden"
          animate="show"
          className="lg:col-span-2 rounded-2xl bg-slate-900/70 border border-slate-700/40 p-6"
        >
          <div className="flex items-center gap-2 mb-5">
            <Search className="w-4 h-4 text-sky-400" />
            <h2 className="text-white font-semibold">Recent Activity</h2>
          </div>
          {recentActivity.length === 0 ? (
            <p className="text-slate-500 text-sm">No queries yet. Start a conversation!</p>
          ) : (
            <ul className="space-y-3">
              {recentActivity.map((q, i) => (
                <motion.li
                  key={q.id}
                  custom={i}
                  variants={fadeUp}
                  initial="hidden"
                  animate="show"
                  className="flex items-start gap-3 p-3 rounded-xl bg-slate-800/50 border border-slate-700/30"
                >
                  <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Search className="w-3.5 h-3.5 text-sky-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-slate-200 text-sm font-medium truncate">{q.query}</p>
                    <p className="text-slate-500 text-xs mt-0.5">{relativeTime(q.timestamp)}</p>
                  </div>
                </motion.li>
              ))}
            </ul>
          )}
        </motion.div>

        {/* Monthly costs */}
        <motion.div
          custom={7}
          variants={fadeUp}
          initial="hidden"
          animate="show"
          className="rounded-2xl bg-slate-900/70 border border-slate-700/40 p-6"
        >
          <div className="flex items-center gap-2 mb-5">
            <Zap className="w-4 h-4 text-emerald-400" />
            <h2 className="text-white font-semibold">Monthly Costs</h2>
          </div>
          <div className="space-y-4">
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-400 text-sm">LLM (queries)</span>
              <span className="text-white font-mono text-sm">${llmCost}</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-400 text-sm">Embeddings (docs)</span>
              <span className="text-white font-mono text-sm">${embeddingCost}</span>
            </div>
            <div className="flex justify-between items-center py-3 rounded-xl bg-emerald-500/10 px-3 border border-emerald-500/20">
              <span className="text-emerald-300 text-sm font-semibold">Estimated Total</span>
              <span className="text-emerald-300 font-mono font-bold">${totalCost}</span>
            </div>
            <p className="text-slate-600 text-xs leading-relaxed">
              Estimate: $0.004/query · $0.002/doc. Actual costs depend on model and usage.
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  )
}

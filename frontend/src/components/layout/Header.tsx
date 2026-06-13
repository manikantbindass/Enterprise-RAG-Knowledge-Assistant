'use client'

import { useEffect, useState } from 'react'
import { Bell, Database, MessageSquare } from 'lucide-react'
import Link from 'next/link'
import { useAppStore } from '@/lib/store'
import { cn } from '@/lib/utils'

interface StoredUser {
  name: string
  email: string
  role: string
}

export default function Header() {
  const [user, setUser] = useState<StoredUser | null>(null)
  const { state } = useAppStore()

  useEffect(() => {
    try {
      const raw = localStorage.getItem('rag_user')
      if (raw) setUser(JSON.parse(raw))
    } catch {
      setUser(null)
    }
  }, [])

  const initials = user?.name
    ? user.name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()
    : 'U'

  const displayName = user?.name?.split(' ')[0] || 'User'

  const indexedDocs = state.documents.filter(d => d.status === 'indexed').length
  const totalConvs = state.conversations.length

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-950/50 backdrop-blur-sm flex items-center px-6 gap-4 flex-shrink-0">
      {/* Quick stats */}
      <div className="flex items-center gap-4">
        <Link href="/documents"
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
            indexedDocs > 0
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/15'
              : 'bg-slate-800/60 text-slate-500 border border-slate-700 hover:text-white'
          )}>
          <Database className="w-3.5 h-3.5" />
          {indexedDocs > 0 ? `${indexedDocs} doc${indexedDocs !== 1 ? 's' : ''} indexed` : 'No docs yet'}
        </Link>

        {totalConvs > 0 && (
          <Link href="/chat"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 hover:bg-indigo-500/15 transition-all">
            <MessageSquare className="w-3.5 h-3.5" />
            {totalConvs} chat{totalConvs !== 1 ? 's' : ''}
          </Link>
        )}
      </div>

      <div className="flex-1" />

      <div className="ml-auto flex items-center gap-3">
        <button className="relative p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all">
          <Bell className="w-5 h-5" />
          {/* Notification dot only if something needs attention */}
          {indexedDocs === 0 && (
            <span className="absolute top-1 right-1 w-2 h-2 bg-amber-500 rounded-full" />
          )}
        </button>
        <div className="h-6 w-px bg-slate-700" />
        <div className="flex items-center gap-2 p-1 pr-3 rounded-lg hover:bg-slate-800 cursor-pointer transition-all">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-white text-xs font-bold">
            {initials}
          </div>
          <span className="text-sm text-white font-medium">{displayName}</span>
        </div>
      </div>
    </header>
  )
}

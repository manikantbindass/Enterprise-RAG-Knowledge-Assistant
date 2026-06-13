'use client'

import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'

interface StoredUser {
  name: string
  email: string
  role: string
}

export default function Header() {
  const [user, setUser] = useState<StoredUser | null>(null)

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

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-950/50 backdrop-blur-sm flex items-center px-6 gap-4 flex-shrink-0">
      <div className="flex-1" />
      <div className="ml-auto flex items-center gap-3">
        <button className="relative p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-indigo-500 rounded-full" />
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

'use client'

import { Bell, Search } from 'lucide-react'

export default function Header() {
  return (
    <header className="h-16 border-b border-slate-800 bg-slate-950/50 backdrop-blur-sm flex items-center px-6 gap-4 flex-shrink-0">
      <div className="flex-1 max-w-lg relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
        <input
          type="text"
          placeholder="Search documents, conversations..."
          className="w-full pl-9 pr-4 py-2 bg-slate-800/60 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
        />
        <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500 bg-slate-700 px-1.5 py-0.5 rounded">⌘K</kbd>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <button className="relative p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-indigo-500 rounded-full" />
        </button>
        <div className="h-6 w-px bg-slate-700" />
        <div className="flex items-center gap-2 p-1 pr-3 rounded-lg hover:bg-slate-800 cursor-pointer transition-all">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-white text-xs font-bold">A</div>
          <span className="text-sm text-white font-medium">Admin</span>
        </div>
      </div>
    </header>
  )
}

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ThemeMode } from '@/types'

interface UIState {
  sidebarCollapsed: boolean
  theme: ThemeMode
  commandPaletteOpen: boolean
  notificationDrawerOpen: boolean
  mobileMenuOpen: boolean
  activeModal: string | null
  notificationCount: number
}

interface UIActions {
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  setTheme: (theme: ThemeMode) => void
  toggleTheme: () => void
  setCommandPaletteOpen: (open: boolean) => void
  toggleCommandPalette: () => void
  setNotificationDrawerOpen: (open: boolean) => void
  setMobileMenuOpen: (open: boolean) => void
  setActiveModal: (modal: string | null) => void
  setNotificationCount: (count: number) => void
  decrementNotifications: () => void
}

export type UIStore = UIState & UIActions

export const useUIStore = create<UIStore>()(
  persist(
    (set, get) => ({
      // ─── State ───────────────────────────────────────────
      sidebarCollapsed: false,
      theme: 'dark',
      commandPaletteOpen: false,
      notificationDrawerOpen: false,
      mobileMenuOpen: false,
      activeModal: null,
      notificationCount: 3,

      // ─── Actions ──────────────────────────────────────────
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),

      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setTheme: (theme) => {
        set({ theme })
        if (typeof document !== 'undefined') {
          if (theme === 'dark') {
            document.documentElement.classList.remove('light')
          } else if (theme === 'light') {
            document.documentElement.classList.add('light')
          } else {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
            document.documentElement.classList.toggle('light', !prefersDark)
          }
        }
      },

      toggleTheme: () => {
        const current = get().theme
        get().setTheme(current === 'dark' ? 'light' : 'dark')
      },

      setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),

      toggleCommandPalette: () =>
        set((state) => ({ commandPaletteOpen: !state.commandPaletteOpen })),

      setNotificationDrawerOpen: (notificationDrawerOpen) => set({ notificationDrawerOpen }),

      setMobileMenuOpen: (mobileMenuOpen) => set({ mobileMenuOpen }),

      setActiveModal: (activeModal) => set({ activeModal }),

      setNotificationCount: (notificationCount) => set({ notificationCount }),

      decrementNotifications: () =>
        set((state) => ({
          notificationCount: Math.max(0, state.notificationCount - 1),
        })),
    }),
    {
      name: 'ui-storage',
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
      }),
    }
  )
)

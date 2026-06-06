import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Organization, User } from '@/types'

interface AuthState {
  user: User | null
  organization: Organization | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

interface AuthActions {
  login: (user: User, org: Organization, accessToken: string, refreshToken: string) => void
  logout: () => void
  setUser: (user: User) => void
  setOrganization: (org: Organization) => void
  setLoading: (loading: boolean) => void
  updateToken: (accessToken: string) => void
}

export type AuthStore = AuthState & AuthActions

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      // ─── State ───────────────────────────────────────────
      user: null,
      organization: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,

      // ─── Actions ──────────────────────────────────────────
      login: (user, organization, accessToken, refreshToken) => {
        if (typeof window !== 'undefined') {
          localStorage.setItem('accessToken', accessToken)
          localStorage.setItem('refreshToken', refreshToken)
        }
        set({
          user,
          organization,
          accessToken,
          refreshToken,
          isAuthenticated: true,
          isLoading: false,
        })
      },

      logout: () => {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('accessToken')
          localStorage.removeItem('refreshToken')
        }
        set({
          user: null,
          organization: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
        })
      },

      setUser: (user) => set({ user }),

      setOrganization: (organization) => set({ organization }),

      setLoading: (isLoading) => set({ isLoading }),

      updateToken: (accessToken) => {
        if (typeof window !== 'undefined') {
          localStorage.setItem('accessToken', accessToken)
        }
        set({ accessToken })
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        organization: state.organization,
        isAuthenticated: state.isAuthenticated,
        // Don't persist tokens in zustand-persist (they're in localStorage directly)
      }),
    }
  )
)

// ─── Selectors ────────────────────────────────────────────────
export const selectUser = (state: AuthStore) => state.user
export const selectOrg = (state: AuthStore) => state.organization
export const selectIsAdmin = (state: AuthStore) =>
  state.user?.role === 'admin'
export const selectIsAuthenticated = (state: AuthStore) => state.isAuthenticated

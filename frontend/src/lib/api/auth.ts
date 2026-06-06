import { useMutation } from '@tanstack/react-query'
import apiClient from '../api'
import type { AuthTokens, LoginRequest, LoginResponse, User } from '@/types'

// ─── Login ─────────────────────────────────────────────────────
async function login(request: LoginRequest): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/auth/login', request)
  return data
}

export function useLogin() {
  return useMutation({
    mutationFn: login,
    onSuccess: ({ tokens }) => {
      localStorage.setItem('accessToken', tokens.accessToken)
      localStorage.setItem('refreshToken', tokens.refreshToken)
    },
  })
}

// ─── Logout ────────────────────────────────────────────────────
async function logout(): Promise<void> {
  await apiClient.post('/auth/logout').catch(() => {})
}

export function useLogout() {
  return useMutation({
    mutationFn: logout,
    onSettled: () => {
      localStorage.removeItem('accessToken')
      localStorage.removeItem('refreshToken')
      window.location.href = '/'
    },
  })
}

// ─── Refresh Token ─────────────────────────────────────────────
async function refreshToken(refreshTkn: string): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>('/auth/refresh', {
    refreshToken: refreshTkn,
  })
  return data
}

// ─── Get Current User ──────────────────────────────────────────
async function getMe(): Promise<LoginResponse> {
  const { data } = await apiClient.get<LoginResponse>('/auth/me')
  return data
}

export { getMe, refreshToken }

// ─── Register ──────────────────────────────────────────────────
interface RegisterRequest {
  name: string
  email: string
  password: string
  organizationName?: string
  inviteCode?: string
}

async function register(request: RegisterRequest): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/auth/register', request)
  return data
}

export function useRegister() {
  return useMutation({
    mutationFn: register,
    onSuccess: ({ tokens }) => {
      localStorage.setItem('accessToken', tokens.accessToken)
      localStorage.setItem('refreshToken', tokens.refreshToken)
    },
  })
}

// ─── Change Password ───────────────────────────────────────────
async function changePassword(current: string, newPass: string): Promise<void> {
  await apiClient.post('/auth/change-password', {
    currentPassword: current,
    newPassword: newPass,
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: ({ current, newPass }: { current: string; newPass: string }) =>
      changePassword(current, newPass),
  })
}

// ─── SSO ───────────────────────────────────────────────────────
export function getSSOUrl(provider: 'google' | 'azure'): string {
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
  return `${base}/auth/sso/${provider}`
}

// ─── Update Profile ────────────────────────────────────────────
async function updateProfile(updates: Partial<Pick<User, 'name' | 'avatar'>>): Promise<User> {
  const { data } = await apiClient.patch<User>('/auth/profile', updates)
  return data
}

export function useUpdateProfile() {
  return useMutation({ mutationFn: updateProfile })
}

// ─── Toggle MFA ────────────────────────────────────────────────
async function toggleMfa(enable: boolean): Promise<{ qrCode?: string; backupCodes?: string[] }> {
  const { data } = await apiClient.post('/auth/mfa/toggle', { enable })
  return data
}

export function useToggleMfa() {
  return useMutation({ mutationFn: toggleMfa })
}

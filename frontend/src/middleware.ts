import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// Routes that require authentication
const PROTECTED_PREFIXES = ['/dashboard', '/chat', '/documents', '/admin', '/settings']

// Routes that should redirect to dashboard if already logged in
const AUTH_ROUTES = ['/', '/register', '/forgot-password']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Check for auth cookie or token — we use a simple cookie set on login
  // For the mock auth, we rely on the 'rag_session' cookie
  const hasSession = request.cookies.has('rag_session')

  const isProtected = PROTECTED_PREFIXES.some(prefix => pathname.startsWith(prefix))
  const isAuthRoute = AUTH_ROUTES.includes(pathname)

  // Redirect unauthenticated users away from protected routes
  if (isProtected && !hasSession) {
    const url = request.nextUrl.clone()
    url.pathname = '/'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  // Redirect authenticated users away from auth routes (optional UX improvement)
  if (isAuthRoute && hasSession && pathname !== '/forgot-password') {
    const url = request.nextUrl.clone()
    url.pathname = '/dashboard'
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - api routes
     * - _next/static, _next/image
     * - favicon.ico
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
}

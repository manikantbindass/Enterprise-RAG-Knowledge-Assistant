import type { Metadata } from 'next'
import './globals.css'
import './workspace.css'
import { Toaster } from 'react-hot-toast'
import Providers from './providers'


export const metadata: Metadata = {
  title: { default: 'Enterprise RAG Assistant', template: '%s | Enterprise RAG' },
  description: 'AI-powered knowledge assistant for enterprise document search and Q&A with source citations.',
  keywords: ['RAG', 'enterprise', 'knowledge base', 'AI', 'document search'],
  authors: [{ name: 'Enterprise RAG Team' }],
  robots: 'noindex, nofollow', // internal enterprise app
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <Providers>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: {
                background: '#1E293B',
                color: '#F1F5F9',
                border: '1px solid #334155',
                borderRadius: '12px',
              },
            }}
          />
        </Providers>
      </body>
    </html>
  )
}

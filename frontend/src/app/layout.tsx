import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Toaster } from 'react-hot-toast'
import Providers from './providers'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

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
      <body className={`${inter.variable} font-inter bg-background text-text-primary antialiased`}>
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

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { ToastProvider } from './lib/toast'
import { ConfirmProvider } from './components/ui'
import { Root } from './Root'

const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 5_000, gcTime: 5 * 60_000 } } })

// Saqlangan mavzuni miltillamasdan qo'llash
try { document.documentElement.setAttribute('data-theme', localStorage.getItem('theme') || (window as any).__BOOT__?.brand?.theme || 'light') } catch { /* ignore */ }

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter basename="/app">
        <ToastProvider>
          <ConfirmProvider>
            <Root />
          </ConfirmProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)

if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {}) })
}

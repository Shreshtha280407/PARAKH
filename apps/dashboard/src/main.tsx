import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './assessment.css'
import App from './App.tsx'
import { loadRuntimeConfig } from './api'

// Resolve the real API origin (build-time default or runtime override)
// before the app makes its first request -- see api.ts's loadRuntimeConfig.
loadRuntimeConfig().finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})

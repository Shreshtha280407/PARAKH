import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // bind 0.0.0.0 -- required for the dev server to be reachable from outside a container
    port: 5173,
  },
  preview: {
    host: true,
    port: 4173,
  },
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // In local dev, forward API calls to a backend running on the host.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})

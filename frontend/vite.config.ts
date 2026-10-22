import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      // SPHURA_API lets a dev point the proxy at another backend (e.g. a mock) without editing this file.
      '/api': { target: process.env.SPHURA_API ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    // Markdown/math/highlighting is one big but cacheable vendor chunk.
    chunkSizeWarningLimit: 900,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'markdown',
              test: /node_modules[\\/](react-markdown|remark-[^\\/]+|rehype-[^\\/]+|micromark[^\\/]*|mdast-[^\\/]+|hast-[^\\/]+|unist-[^\\/]+|unified|vfile[^\\/]*|katex|highlight\.js|lowlight|property-information|space-separated-tokens|comma-separated-tokens|decode-named-character-reference|character-entities[^\\/]*|html-url-attributes|devlop|bail|trough|is-plain-obj|zwitch|longest-streak|markdown-table|ccount|escape-string-regexp|trim-lines|estree-util-is-identifier-name|style-to-js|style-to-object|inline-style-parser|web-namespaces|hastscript|parse-entities|stringify-entities)[\\/]/,
            },
            { name: 'react', test: /node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom)[\\/]/ },
            { name: 'ui', test: /node_modules[\\/](radix-ui|@radix-ui|framer-motion|motion-dom|motion-utils|lucide-react|react-icons|sonner|cmdk)[\\/]/ },
          ],
        },
      },
    },
  },
})

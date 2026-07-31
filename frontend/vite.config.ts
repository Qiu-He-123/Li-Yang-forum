import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  base: '/',
  plugins: [
    vue(),
    // Element Plus 按需引入：仅打包实际使用的组件 + 对应样式
    // 用户端页面（首页/圈子/帖子）不使用 EP 组件 → 0 KB EP 代码
    // 管理端页面（/admin/*）使用 EP 组件 → 按需加载，不再全量引入
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: 'src/types/auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: 'src/types/components.d.ts',
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: [
      'qiuhe.w1.luyouxia.net',
      'localhost',
      '127.0.0.1',
    ],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
      '/uploads': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
  build: {
    // 代码分割：将第三方库拆分为独立 chunk，利用浏览器长期缓存
    rollupOptions: {
      output: {
        manualChunks: {
          // Vue 核心（vue + vue-router + pinia），变更频率极低
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          // axios 网络库
          'axios': ['axios'],
        },
      },
    },
    // 提高块大小警告阈值
    chunkSizeWarningLimit: 600,
    // 生产环境删除 console.log（保留 console.error/warn）
    minify: 'esbuild',
  },
})

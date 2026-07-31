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
  // esbuild 转译选项：生产环境移除 console.log/debugger（保留 error/warn/info）
  // 减少 bundle 体积 + 避免线上日志泄露内部逻辑
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
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
          // 注意：element-plus 不在此处声明 → 走 unplugin-vue-components 按需引入，
          // 仅打包实际使用的 EP 组件到对应 admin 页面 chunk；用户端页面 0 KB EP 代码
        },
      },
    },
    // 提高块大小警告阈值
    chunkSizeWarningLimit: 600,
    // 生产环境：esbuild 比 terser 快 5-10 倍，压缩率略低但可接受
    minify: 'esbuild',
    // 现代浏览器目标：ES2020 已支持 95%+ 用户，省去大量 polyfill
    target: 'es2020',
    // Vite 默认开启 modulePreload：首屏加载时并行 preload 路由依赖 chunk，
    // 切换路由时立即下载并执行（无需等点击才发起），减少"点击→加载"延迟
    modulePreload: { polyfill: true },
    // 不输出 gzip 大小报告（构建加速，不影响产物）
    reportCompressedSize: false,
  },
})

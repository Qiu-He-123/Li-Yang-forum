import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 白天/暗色主题：保存在 localStorage，设置页切换，全局 html[data-theme] 生效 */
export const useThemeStore = defineStore('theme', () => {
  const theme = ref<'light' | 'dark'>('light')

  function apply(value: 'light' | 'dark') {
    theme.value = value
    const el = document.documentElement
    el.dataset.theme = value
    // Element Plus 暗色模式需要 html.dark
    el.classList.toggle('dark', value === 'dark')
    try {
      localStorage.setItem('ly:theme', value)
    } catch {
      /* ignore */
    }
  }

  function init() {
    let saved: string | null = null
    try {
      saved = localStorage.getItem('ly:theme')
    } catch {
      /* ignore */
    }
    apply(saved === 'dark' ? 'dark' : 'light')
  }

  return { theme, apply, init }
})

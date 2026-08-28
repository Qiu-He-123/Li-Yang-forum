/**
 * 原生 Toast 通知系统（替代 ElMessage）
 * 用法：
 *   import { toast } from '@/components/native/Toast'
 *   toast.success('已保存')
 *   toast.error('网络错误')
 *   toast.info('提示信息')
 */
import { createApp, reactive, TransitionGroup, h, ref } from 'vue'
import Icon from './Icon.vue'

interface ToastItem {
  id: number
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
  duration: number
}

const state = reactive({
  list: [] as ToastItem[],
})

let _id = 0
function push(type: ToastItem['type'], message: string, duration = 2500) {
  const id = ++_id
  state.list.push({ id, type, message, duration })
  setTimeout(() => {
    remove(id)
  }, duration)
}

function remove(id: number) {
  const idx = state.list.findIndex((t) => t.id === id)
  if (idx >= 0) state.list.splice(idx, 1)
}

const iconMap = {
  success: 'check-circle',
  error: 'circle-alert',
  info: 'info',
  warning: 'triangle-alert',
}

const colorMap = {
  success: '#34c759',
  error: '#ff3b30',
  info: '#007aff',
  warning: '#ff9500',
}

export const toast = {
  success: (msg: string, duration?: number) => push('success', msg, duration),
  error: (msg: string, duration?: number) => push('error', msg, duration),
  info: (msg: string, duration?: number) => push('info', msg, duration),
  warning: (msg: string, duration?: number) => push('warning', msg, duration),
  remove,
}

// Toast 容器组件
const ToastContainer = {
  name: 'ToastContainer',
  setup() {
    return () =>
      h(
        TransitionGroup,
        {
          tag: 'div',
          class: 'toast-container',
          name: 'toast',
        },
        () =>
          state.list.map((item) =>
            h(
              'div',
              {
                key: item.id,
                class: `toast-item toast-${item.type}`,
                onClick: () => remove(item.id),
              },
              [
                h(Icon, {
                  name: iconMap[item.type],
                  size: 18,
                  color: colorMap[item.type],
                }),
                h('span', { class: 'toast-message' }, item.message),
              ],
            ),
          ),
      )
  },
}

// 全局挂载 Toast 容器
let mounted = false
export function mountToast() {
  if (mounted) return
  mounted = true
  const div = document.createElement('div')
  div.id = 'toast-root'
  document.body.appendChild(div)
  createApp(ToastContainer).mount(div)

  // 注入样式
  const style = document.createElement('style')
  style.textContent = `
.toast-container {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
  align-items: center;
}
.toast-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: rgba(28, 28, 30, 0.95);
  color: white;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  box-shadow: 0 8px 16px -4px rgba(0,0,0,0.2), 0 4px 8px -2px rgba(0,0,0,0.1);
  pointer-events: auto;
  cursor: pointer;
  max-width: 90vw;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.toast-message {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.toast-enter-active, .toast-leave-active {
  transition: all 0.3s cubic-bezier(0.32, 0.72, 0, 1);
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(-12px) scale(0.95);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.95);
}
`
  document.head.appendChild(style)
}

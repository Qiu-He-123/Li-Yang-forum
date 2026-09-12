/**
 * 「点我提问」AI 悬浮按钮的全局开关与位置
 * - 开关 + 位置均持久化到 localStorage（本机生效）
 * - 组件间通过本模块共享响应式状态，改动即时同步
 */
import { ref, watch } from 'vue'

const ENABLED_KEY = 'ai_fab_enabled'
const POS_KEY = 'ai_fab_pos'

const aiFabEnabled = ref<boolean>(localStorage.getItem(ENABLED_KEY) !== '0')

watch(aiFabEnabled, (v) => {
  localStorage.setItem(ENABLED_KEY, v ? '1' : '0')
})

export function setAiFabEnabled(v: boolean) {
  aiFabEnabled.value = v
}

export function getAiFabEnabled() {
  return aiFabEnabled.value
}

/** 持久化按钮拖动位置（px） */
export interface AiFabPos {
  left: number
  top: number
}

export function getAiFabPos(): AiFabPos | null {
  try {
    const raw = localStorage.getItem(POS_KEY)
    return raw ? (JSON.parse(raw) as AiFabPos) : null
  } catch {
    return null
  }
}

export function setAiFabPos(pos: AiFabPos) {
  try {
    localStorage.setItem(POS_KEY, JSON.stringify(pos))
  } catch {
    /* 静默 */
  }
}

export { aiFabEnabled }
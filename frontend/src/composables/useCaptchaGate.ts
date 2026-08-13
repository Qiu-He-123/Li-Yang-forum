import { reactive } from 'vue'

/**
 * 全局验证码闸门（单例）。
 *
 * 两种用途：
 * - challenge：高频访问触发（GET 超阈值），验证通过后自动重试原请求
 * - download：APK 下载前验证，通过后拿到一次性下载令牌
 *
 * CaptchaGate.vue 在 App.vue 全局挂载，任何组件都可调用 openCaptchaGate()。
 */
export type CaptchaGateMode = 'challenge' | 'download'

export interface CaptchaGateResult {
  ok: boolean
  downloadToken?: string
}

interface CaptchaGateState {
  visible: boolean
  mode: CaptchaGateMode
  title: string
  resolve: ((result: CaptchaGateResult) => void) | null
}

const state = reactive<CaptchaGateState>({
  visible: false,
  mode: 'challenge',
  title: '请完成验证码验证',
  resolve: null,
})

export function openCaptchaGate(mode: CaptchaGateMode = 'challenge'): Promise<CaptchaGateResult> {
  state.mode = mode
  state.title = mode === 'download' ? '下载前请完成验证' : '访问过于频繁，请完成验证'
  state.visible = true
  return new Promise((resolve) => {
    state.resolve = resolve
  })
}

export function resolveCaptchaGate(result: CaptchaGateResult) {
  state.visible = false
  if (state.resolve) state.resolve(result)
  state.resolve = null
}

export function useCaptchaGate() {
  return state
}

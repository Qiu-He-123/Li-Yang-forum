/**
 * 数据刷新渐变过渡 composable。
 *
 * 用法：
 *   const { fadeActive, triggerFade } = useFadeUpdate()
 *   // 模板中：<div :class="{ 'swr-updated': fadeActive }">...</div>
 *   // 数据刷新后调用 triggerFade()，CSS 自动播放文字/图片渐变动画
 *
 * 效果：SWR 刷新数据后，保留旧 DOM 不销毁（保持滚动位置），
 * Vue 响应式原地更新文本/图片内容，CSS 动画让这个更新过程可见：
 * - 文字：旧文字快速淡出 → 新文字快速淡入（带轻微上下位移）
 * - 图片：旧图左滑消失 → 新图右滑进入
 */
import { ref } from 'vue'

export function useFadeUpdate() {
  /** 是否正在播放渐变动画 */
  const fadeActive = ref(false)
  let fadeTimer: ReturnType<typeof setTimeout> | null = null

  /** 触发渐变动画：添加 swr-updated 类，400ms 后自动移除 */
  function triggerFade() {
    // 先移除再添加，确保连续触发时动画能重新播放
    fadeActive.value = false
    // 用 microtask 确保 Vue 检测到 class 变化
    requestAnimationFrame(() => {
      fadeActive.value = true
      if (fadeTimer) clearTimeout(fadeTimer)
      fadeTimer = setTimeout(() => {
        fadeActive.value = false
      }, 450)
    })
  }

  return { fadeActive, triggerFade }
}

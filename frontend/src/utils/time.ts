/**
 * 时间格式化工具
 *
 * 后端返回的 ISO 字符串带 +08:00 时区（北京时间），
 * 前端 new Date() 会自动按本地时区解析，无需额外处理。
 *
 * 提供：
 * - formatRelative(iso): 刚刚 / X 分钟前 / X 小时前 / 昨天 HH:MM / MM-DD HH:MM / YYYY-MM-DD HH:MM
 * - formatDateTime(iso): 2026-07-27 22:33
 * - formatDate(iso): 07-27
 * - formatTime(iso): 22:33
 */

/**
 * 相对时间格式化（用于帖子列表、评论、通知等）
 * - < 1 分钟 → "刚刚"
 * - < 1 小时 → "X 分钟前"
 * - < 24 小时 → "X 小时前"
 * - 昨天 → "昨天 HH:MM"
 * - 今年 → "MM-DD HH:MM"
 * - 跨年 → "YYYY-MM-DD HH:MM"
 */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const sec = Math.floor(diff / 1000)
  const min = Math.floor(sec / 60)
  const hour = Math.floor(min / 60)
  const day = Math.floor(hour / 24)

  // 未来时间或 1 分钟内 → 刚刚
  if (diff < 0 || sec < 60) return '刚刚'
  // 1 小时内 → X 分钟前
  if (min < 60) return `${min} 分钟前`
  // 24 小时内 → X 小时前
  if (hour < 24) return `${hour} 小时前`

  // 获取日期部分（本地）
  const dDate = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const nowDate = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const dayDiff = Math.floor((nowDate.getTime() - dDate.getTime()) / (24 * 60 * 60 * 1000))

  // 昨天 → 昨天 HH:MM
  if (dayDiff === 1) {
    return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  // 今年内 → MM-DD HH:MM
  if (d.getFullYear() === now.getFullYear()) {
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  // 跨年 → YYYY-MM-DD HH:MM
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 完整日期时间：2026-07-27 22:33
 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 仅日期：07-27（今年）或 2025-12-31（跨年）
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  if (d.getFullYear() === now.getFullYear()) {
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  }
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/**
 * 仅时间：22:33
 */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function pad(n: number): string {
  return n < 10 ? '0' + n : String(n)
}

import router from '../router'

/**
 * 语义化返回：返回键回到用户"心理上的上一页"，而不是历史记录里的上一页。
 * - 聊天 → 会话列表（/notifications）
 * - 帖子 → 首页（/）
 * - 从通知/深链接进来时，返回直接回目标页；正常浏览时仍走浏览器历史
 */
const DETAIL_BACK_TARGETS: Array<[prefix: string, target: string]> = [
  ['/chat/', '/notifications'],
  ['/post/', '/'],
]

export function isDetailPath(path: string): boolean {
  return DETAIL_BACK_TARGETS.some(([prefix]) => path.startsWith(prefix))
}

export function detailBackTarget(path: string): string {
  for (const [prefix, target] of DETAIL_BACK_TARGETS) {
    if (path.startsWith(prefix)) return target
  }
  return '/'
}

/**
 * 进入详情前调用：把当前历史条目替换成返回目标。
 * 之后按返回（App 返回键 / 浏览器返回）会直接回到目标页，而不是退回中间页。
 */
export function prepareBackTarget(target: string) {
  try {
    history.replaceState(history.state, '', target)
  } catch {
    /* ignore */
  }
}

/**
 * 深链接 / 扫码 / 直接打开详情页时调用（此时历史里没有上一页）：
 * 补一条「返回目标」历史，让返回键从详情页直接回首页 / 会话列表。
 */
export async function ensureDeepEntryBackTarget(path: string): Promise<void> {
  const state = history.state as { back?: string | null } | null
  if (state?.back != null) return // 有上一页，正常浏览，不做处理
  if (!isDetailPath(path)) return
  const target = detailBackTarget(path)
  await router.replace(target)
  await router.push(path)
}

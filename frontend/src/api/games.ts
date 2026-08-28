import { http, type LoadingAxiosRequestConfig } from './http'

/** 游戏信息（用户侧列表 / 后台管理共用字段） */
export interface GameItem {
  id: number
  name: string
  slug: string
  type: 'single' | 'multi'
  description: string
  icon_url: string
  reward_coins: number
  daily_limit: number
  affinity_daily_limit: number
  is_active: boolean
  sort_order: number
  source: string
  status: string
  created_by: number | null
}

/** 领取金币奖励返回 */
export interface GameRewardResp {
  awarded: number
  coins: number
  new_best: boolean
  daily_remaining: number
  reward_coins: number
  daily_limit: number
  gained_affinity?: number
  affinity_remaining?: number
  affinity_limit?: number
  coins_daily_remaining?: number
}

/** 用户在某游戏的金币领取状态 */
export interface GameMyStatus {
  reward_coins: number
  daily_limit: number
  claimed_today: number
  affinity_daily_limit: number
  affinity_today: number
  best_score: number
}

function unwrap<T>(resp: { data: { code: number; msg: string; data: T } }): T {
  return resp.data.data
}

/** 游戏列表（仅已上架） */
export async function listGames(config: LoadingAxiosRequestConfig = {}) {
  const resp = await http.get<unknown, { data: { code: number; msg: string; data: { items: GameItem[] } } }>('/games', config)
  return resp.data.data.items
}

/** 领取游戏金币奖励（track=true 新纪录才发；track=false 手动领取；pet_product_id 同局发好感） */
export async function claimGameReward(
  slug: string,
  bestScore = 0,
  track = false,
  config: LoadingAxiosRequestConfig = {},
  petProductId?: number,
) {
  const resp = await http.post<unknown, { data: { code: number; msg: string; data: GameRewardResp } }>(
    `/games/${slug}/reward`,
    { best_score: bestScore, track, pet_product_id: petProductId ?? null },
    config,
  )
  return resp.data.data
}

/** 当前用户在某游戏的金币领取状态 */
export async function getGameMyStatus(slug: string, config: LoadingAxiosRequestConfig = {}) {
  const resp = await http.get<unknown, { data: { code: number; msg: string; data: GameMyStatus } }>(
    `/games/${slug}/my-status`,
    config,
  )
  return resp.data.data
}

/** 获取用户自制游戏的在线 HTML 源码 */
export async function getGameHtml(slug: string, config: LoadingAxiosRequestConfig = {}) {
  const resp = await http.get<unknown, { data: { code: number; msg: string; data: { slug: string; name: string; html: string } } }>(
    `/games/${slug}/play`,
    config,
  )
  return resp.data.data
}

/** 用户「制作游戏」提交（上传 HTML，后台审核） */
export async function submitUserGame(payload: { name: string; type: 'single' | 'multi'; description: string; file: File }) {
  const fd = new FormData()
  fd.append('name', payload.name)
  fd.append('type', payload.type)
  fd.append('description', payload.description)
  fd.append('file', payload.file)
  const resp = await http.post<unknown, { data: { code: number; msg: string; data: GameItem } }>('/games/submit', fd)
  return unwrap(resp)
}

// ================= 后台管理 =================

/** 后台：全部游戏（含未上架/待审核），支持关键词过滤 */
export async function adminListGames(keyword = '', config: LoadingAxiosRequestConfig = {}) {
  const resp = await http.get<unknown, { data: { code: number; msg: string; data: { items: GameItem[] } } }>(
    '/admin/games',
    { params: keyword ? { keyword } : {}, ...config },
  )
  return resp.data.data.items
}

/** 后台：新增游戏 */
export async function adminCreateGame(payload: {
  name: string
  slug: string
  type: 'single' | 'multi'
  description?: string
  icon_url?: string
  reward_coins: number
  daily_limit: number
  affinity_daily_limit?: number
  sort_order?: number
}) {
  const resp = await http.post<unknown, { data: { code: number; msg: string; data: GameItem } }>('/admin/games', payload)
  return unwrap(resp)
}

/** 后台：更新游戏（金币奖励/每日上限/上下架/审核状态等） */
export async function adminUpdateGame(gameId: number, payload: Partial<{
  name: string
  type: 'single' | 'multi'
  description: string
  icon_url: string
  reward_coins: number
  daily_limit: number
  affinity_daily_limit?: number
  sort_order: number
  is_active: boolean
  status: 'active' | 'pending' | 'rejected'
}>) {
  const resp = await http.put<unknown, { data: { code: number; msg: string; data: GameItem } }>(`/admin/games/${gameId}`, payload)
  return unwrap(resp)
}

/** 后台：删除游戏 */
export async function adminDeleteGame(gameId: number) {
  await http.delete<unknown, { data: { code: number; msg: string; data: null } }>(`/admin/games/${gameId}`)
}

import { http, type LoadingAxiosRequestConfig } from './http'

export interface WechatStatus {
  bound: boolean
  status: string | null
  wxid: string | null
  wechat_id: string | null
  nickname: string | null
  sync_enabled: boolean
  sync_enabled_at: string | null
  bound_at: string | null
  synced_count: number
  coins: number
  onboarding_done: boolean
}

export interface BindGuide {
  wechat_id: string
}

export interface BindResult {
  step: string
  verify_code: string
  wechat_id: string
  wxid: string
  nickname: string
}

export interface WechatMomentMedia {
  type: number
  url?: string
  /** 视频封面（本地缓存明文封面，可选） */
  thumb_url?: string
}

export interface WechatMomentItem {
  id: number
  tid: string
  content: string
  create_time: string | null
  media: WechatMomentMedia[]
  media_pending?: boolean
  imported: boolean
}

export interface WechatFeedItem {
  id: number
  content: string
  image_urls: string[]
  video_urls?: string[]
  author: string
  author_id: number
  author_avatar_url: string
  like_count: number
  comment_count: number
  created_at: string
  ai_status: string
  source: string
  category: string
  is_pinned: boolean
  pinned_until: string | null
  wechat_created_at: string | null
}

export function bindWechat(query: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: BindResult } }>(
    '/wechat/bind',
    { query },
  )
}

export function getBindGuide() {
  return http.get<unknown, { data: { code: number; msg: string; data: BindGuide } }>('/wechat/bind-guide')
}

export function verifyBindCode(code: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: { matched: boolean; reason?: string; coins?: number; wrong_code?: boolean } } }>(
    '/wechat/bind/verify-code',
    { code },
  )
}

export function getWechatStatus() {
  return http.get<unknown, { data: { code: number; msg: string; data: WechatStatus } }>('/wechat/status')
}

export function setWechatSync(enabled: boolean) {
  return http.patch<unknown, { data: { code: number; msg: string; data: WechatStatus } }>(
    '/wechat/sync-config',
    { enabled },
  )
}

export function unbindWechat() {
  return http.post<unknown, { data: { code: number; msg: string; data: { unbound: boolean; wxid: string | null } } }>(
    '/wechat/unbind',
  )
}

export function listMyMoments(page = 1, pageSize = 100) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: WechatMomentItem[]; total: number } } }>(
    '/wechat/moments',
    { params: { page, page_size: pageSize } },
  )
}

export function importMoments(payload: {
  tids: string[]
  pinned_tids: string[]
  pin_days: number
}) {
  return http.post<unknown, { data: { code: number; msg: string; data: { cost: number; post_ids: number[] } } }>(
    '/wechat/import',
    payload,
  )
}

export function refreshWechatMoments() {
  return http.post<unknown, { data: { code: number; msg: string; data: { refreshing: boolean } } }>(
    '/wechat/refresh',
  )
}

export function getWechatFeed(page = 1, pageSize = 20, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: WechatFeedItem[]; total: number } } }>(
    '/wechat/feed',
    { ...config, params: { page, page_size: pageSize } },
  )
}

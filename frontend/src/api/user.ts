import { http } from './http'
import type { LoadingAxiosRequestConfig } from './http'
import type { Post, Profile } from '../types/api'

export interface ProfileUpdatePayload {
  nickname?: string
  avatar_url?: string
  background_url?: string
  bio?: string
  /** @deprecated 已弃用，改用 birthday */
  grade?: string
  /** 生日（ISO 字符串 YYYY-MM-DD，设置后动态计算年龄，替代 grade） */
  birthday?: string | null
  gender?: 'male' | 'female' | 'unknown'
}

export function fetchMe(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Profile } }>('/users/me', config)
}

export function updateMe(payload: ProfileUpdatePayload) {
  return http.patch<unknown, { data: { code: number; msg: string; data: Profile } }>('/users/me', payload)
}

export function fetchUser(userId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Profile } }>(`/users/${userId}`, config)
}

/** 分页结果结构 */
export interface PaginatedPosts {
  items: Post[]
  total: number
  page: number
  page_size: number
}

export function fetchUserPosts(userId: number, page = 1, pageSize = 20, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PaginatedPosts | Post[] } }>(
    `/users/${userId}/posts`,
    { ...config, params: { page, page_size: pageSize } },
  )
}

/** 获赞列表：点赞过该用户帖子的用户列表 */
export function fetchUserLikers(userId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: any[] } }>(`/users/${userId}/likers`)
}

// 仅返回 id 列表，用于帖子卡片 active 态回填
export function fetchMyLikes(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { post_ids: number[]; comment_ids: number[] } } }>('/users/me/likes', config)
}

export function fetchMyFavorites(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { post_ids: number[] } } }>('/users/me/favorites', config)
}

// T5-1 / T5-3 / T5-4：返回分页 Post 列表，用于个人主页 Tab 与独立页面
export function fetchMyLikedPosts(page = 1, pageSize = 20, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PaginatedPosts | Post[] } }>(
    '/users/me/likes/posts',
    { ...config, params: { page, page_size: pageSize } },
  )
}

export function fetchMyFavoritePosts(page = 1, pageSize = 20, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PaginatedPosts | Post[] } }>(
    '/users/me/favorites/posts',
    { ...config, params: { page, page_size: pageSize } },
  )
}

export function fetchMyDrafts() {
  return http.get<unknown, { data: { code: number; msg: string; data: Post[] } }>('/users/me/drafts')
}

// ============ 封号状态 & 申诉 ============

export interface BanStatus {
  is_banned: boolean
  ban_until: string | null
  ban_reason: string | null
  violation_count: number
  warning_score: number
  warn_threshold: number
  temp_ban_threshold: number
  temp_ban_hours: number
  perm_ban_threshold: number
}

export function fetchBanStatus(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: BanStatus } }>('/users/me/ban-status', config)
}

// ============ 警告值系统 ============

export interface WarningStatus {
  score: number
  level: 'normal' | 'warn' | 'ban' | 'danger'
  warn_threshold: number
  temp_ban_threshold: number
  temp_ban_hours: number
  perm_ban_threshold: number
  next_threshold: number
  next_action: string
  reduce_hint: string
}

export interface WarningLogItem {
  id: number
  user_id: number
  delta: number
  score_after: number
  reason: string
  source: string
  related_type: string | null
  related_id: number | null
  operator_id: number | null
  created_at: string | null
}

export interface WarningLogPage {
  items: WarningLogItem[]
  total: number
  page: number
  page_size: number
}

export function fetchMyWarningStatus(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: WarningStatus } }>('/users/me/warning', config)
}

export function fetchMyWarningLogs(params: { page?: number; page_size?: number } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: WarningLogPage } }>('/users/me/warning-logs', { params })
}

export interface UserAppeal {
  id: number
  ban_record_id: number | null
  reason: string
  status: string
  reviewed_at: string | null
  review_comment: string | null
  created_at: string
}

export function createAppeal(reason: string, banRecordId?: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: UserAppeal } }>('/users/me/appeals', {
    reason,
    ban_record_id: banRecordId,
  })
}

export function fetchMyAppeals(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: UserAppeal[] } }>('/users/me/appeals', config)
}

import { http } from './http'
import type { LoadingAxiosRequestConfig } from './http'
import type { Badge } from '../types/api'

// ============ 用户侧 ============

export interface MyBadgesData {
  owned: Badge[]
  wearing_badge: Badge | null
  wearing_badge_id: number | null
  total: number
  all_badges: Badge[]
}

export function fetchBadges(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Badge[] } }>(
    '/badges',
    config,
  )
}

export function fetchMyBadges(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: MyBadgesData } }>(
    '/badges/mine',
    config,
  )
}

export function claimBadge(code: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: Badge } }>(
    '/badges/claim',
    { code },
  )
}

export function wearBadge(badgeId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: Badge } }>(
    '/badges/wear',
    { badge_id: badgeId },
  )
}

export function unwearBadge() {
  return http.delete<unknown, { data: { code: number; msg: string; data: { wearing_badge: null } } }>(
    '/badges/wear',
  )
}

// ============ 后台管理 ============

export interface AdminBadge extends Badge {
  is_system: boolean
  code_count: number
  used_code_count: number
  owner_count: number
}

export interface BadgeCodeItem {
  id: number
  code: string
  badge_id: number
  badge_name: string | null
  badge_icon: string | null
  note: string | null
  batch_no: string | null
  created_at: string | null
  used_by: number | null
  used_nickname: string | null
  used_at: string | null
}

export function adminListBadges(keyword?: string) {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminBadge[] } }>(
    '/admin/badges',
    { params: { keyword } },
  )
}

export function adminCreateBadge(payload: {
  name: string
  code: string
  icon?: string
  description?: string
  is_active?: boolean
  sort_order?: number
  is_system?: boolean
}) {
  return http.post<unknown, { data: { code: number; msg: string; data: Badge } }>(
    '/admin/badges',
    payload,
  )
}

export function adminUpdateBadge(
  badgeId: number,
  payload: Partial<{
    name: string
    icon: string
    description: string
    is_active: boolean
    sort_order: number
  }>,
) {
  return http.patch<unknown, { data: { code: number; msg: string; data: Badge } }>(
    `/admin/badges/${badgeId}`,
    payload,
  )
}

export function adminDeleteBadge(badgeId: number) {
  return http.delete(`/admin/badges/${badgeId}`)
}

export function adminGenerateBadgeCodes(
  badgeId: number,
  payload: { count?: number; note?: string; batch_no?: string },
) {
  return http.post<
    unknown,
    {
      data: {
        code: number
        msg: string
        data: { badge: Badge; codes: string[]; batch_no: string }
      }
    }
  >(`/admin/badges/${badgeId}/codes`, payload)
}

export function adminListBadgeCodes(params: {
  badge_id?: number
  status?: 'used' | 'unused'
  page?: number
  page_size?: number
} = {}) {
  return http.get<
    unknown,
    {
      data: {
        code: number
        msg: string
        data: { items: BadgeCodeItem[]; total: number; page: number; page_size: number }
      }
    }
  >('/admin/badge-codes', { params })
}

export function adminDeleteBadgeCode(codeId: number) {
  return http.delete(`/admin/badge-codes/${codeId}`)
}

export function adminGrantBadge(userId: number, badgeId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { user_id: number; badge: Badge } } }>(
    '/admin/badges/grant',
    { user_id: userId, badge_id: badgeId },
  )
}

// ============ 徽章自动发放规则 ============

/** 支持的自动发放动作（与后端 badge_service.SUPPORTED_ACTIONS 一致） */
export const BADGE_ACTIONS: { value: string; label: string }[] = [
  { value: 'checkin_consecutive', label: '连续签到天数' },
  { value: 'approved_posts', label: '审核通过的帖子数' },
  { value: 'approved_comments', label: '审核通过的评论数' },
  { value: 'followers_count', label: '粉丝数' },
  { value: 'likes_received', label: '获赞总数' },
]

export interface BadgeRule {
  id: number
  action: string
  action_label: string
  badge_id: number
  badge_name: string | null
  badge_icon: string | null
  threshold: number
  description: string | null
  is_enabled: boolean
  created_at: string | null
}

export function adminListBadgeRules() {
  return http.get<unknown, { data: { code: number; msg: string; data: BadgeRule[] } }>(
    '/admin/badge-rules',
  )
}

export function adminCreateBadgeRule(payload: {
  action: string
  badge_id: number
  threshold: number
  description?: string
  is_enabled?: boolean
}) {
  return http.post<unknown, { data: { code: number; msg: string; data: BadgeRule } }>(
    '/admin/badge-rules',
    payload,
  )
}

export function adminUpdateBadgeRule(
  ruleId: number,
  payload: Partial<{ badge_id: number; threshold: number; description: string; is_enabled: boolean }>,
) {
  return http.patch<unknown, { data: { code: number; msg: string; data: BadgeRule } }>(
    `/admin/badge-rules/${ruleId}`,
    payload,
  )
}

export function adminDeleteBadgeRule(ruleId: number) {
  return http.delete(`/admin/badge-rules/${ruleId}`)
}

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

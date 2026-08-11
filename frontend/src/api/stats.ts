import { http } from './http'
import type { LoadingAxiosRequestConfig } from './http'
import type { Badge } from '../types/api'

export interface OnlineUserItem {
  id: number
  nickname: string
  avatar_url: string | null
  badge: Badge | null
  school: string | null
  connected_at: string | null
}

export interface OnlineGuestItem {
  id: string
  nickname: string
  avatar_url: null
  badge: null
  school: null
  connected_at: string | null
}

interface Paged<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export function fetchOnlineUsers(
  page = 1,
  pageSize = 20,
  q = '',
  config: LoadingAxiosRequestConfig = {},
) {
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (q) params.q = q
  return http.get<unknown, { data: { code: number; msg: string; data: Paged<OnlineUserItem> } }>(
    '/stats/online-users',
    { ...config, params },
  )
}

export function fetchOnlineGuests(
  page = 1,
  pageSize = 20,
  config: LoadingAxiosRequestConfig = {},
) {
  return http.get<unknown, { data: { code: number; msg: string; data: Paged<OnlineGuestItem> } }>(
    '/stats/online-guests',
    { ...config, params: { page, page_size: pageSize } },
  )
}

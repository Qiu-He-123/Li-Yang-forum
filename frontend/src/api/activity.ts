import { http, type LoadingAxiosRequestConfig } from './http'

export interface Activity {
  id: number
  title: string
  description: string
  location: string | null
  cover_url: string | null
  start_at: string | null
  end_at: string | null
  organizer: string | null
  contact: string | null
  max_participants: number | null
  participant_count: number
  is_active: boolean
  joined: boolean
  created_at: string | null
}

export interface ActivityListResp {
  items: Activity[]
  total: number
  page: number
  page_size: number
}

/** 活动列表（登录用户附带 joined 状态） */
export function listActivities(page = 1, pageSize = 20, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: ActivityListResp } }>(
    '/activities',
    { ...config, params: { page, page_size: pageSize } },
  )
}

/** 活动详情 */
export function fetchActivity(id: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Activity } }>(
    `/activities/${id}`,
    config,
  )
}

/** 报名 / 取消报名 */
export function joinActivity(id: number, action: 'join' | 'cancel' = 'join') {
  return http.post<unknown, { data: { code: number; msg: string; data: Activity } }>(
    `/activities/${id}/join`,
    { action },
  )
}

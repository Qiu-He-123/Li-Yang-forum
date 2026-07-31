import { http } from './http'
import type { LoadingAxiosRequestConfig } from './http'
import type { NotificationItem } from '../types/api'

export type NotificationType = 'interaction' | 'comment' | 'like' | 'follow' | 'system' | 'announcement' | 'mention'

export interface NotificationListResp {
  items: NotificationItem[]
  total: number
  page: number
  page_size: number
}

export interface NotificationDetail extends NotificationItem {
  post_id: number | null
}

/** 通知列表（可按 type 过滤 + 分页） */
export function listNotifications(type?: NotificationType, page = 1, pageSize = 20) {
  return http.get<unknown, { data: { code: number; msg: string; data: NotificationListResp } }>('/notifications', {
    params: { ...(type ? { type } : {}), page, page_size: pageSize },
  })
}

/** 单条通知详情 */
export function fetchNotificationDetail(id: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: NotificationDetail } }>(`/notifications/${id}`)
}

/** 标记单条已读 */
export function markNotificationRead(id: number) {
  return http.patch<unknown, { data: { code: number; msg: string; data: { id: number; is_read: boolean } } }>(
    `/notifications/${id}/read`,
  )
}

/** 全部已读（可按 type） */
export function markAllNotificationsRead(type?: NotificationType) {
  return http.patch<unknown, { data: { code: number; msg: string; data: { updated: number } } }>(
    '/notifications/read-all',
    type ? { type } : {},
  )
}

/** 未读通知数（含私信未读数） */
export function fetchUnreadCount() {
  const config: LoadingAxiosRequestConfig = {
    showGlobalLoading: false,
    showGlobalError: false,
  }
  return http.get<
    unknown,
    { data: { code: number; msg: string; data: { unread: number; by_type: Record<string, number>; dm_unread: number } } }
  >('/notifications/unread-count', config)
}

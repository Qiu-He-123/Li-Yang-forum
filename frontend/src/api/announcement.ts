import { http, type LoadingAxiosRequestConfig } from './http'
import type { Announcement } from '../types/api'

export function listAnnouncements(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Announcement[] } }>('/announcements', config)
}

/** 登录后获取未读公告（用于弹窗） */
export function listUnreadAnnouncements(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Announcement[] } }>('/announcements/unread', config)
}

/** 我的-公告页：列出该用户可见的所有公告（带 is_read 状态） */
export function listMyAnnouncements(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Announcement[] } }>('/announcements/mine', config)
}

/** 标记公告已读（点击"我知道了"按钮） */
export function markAnnouncementRead(id: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { ok: boolean } } }>(`/announcements/${id}/read`)
}

/** 首页统计：在线人数 + 今日发帖 + 注册人数 */
export function fetchHomeStats(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { online_count: number; logged_in_count: number; visitor_count: number; today_post_count: number; total_users: number } } }>('/stats/home', config)
}

/** 漂流瓶页统计：在线人数 + 匹配中人数 + 投放数 + 今日拾取数 */
export function fetchBottleStats(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { online_count: number; matching_count: number; total_bottles: number; today_picks: number } } }>('/stats/bottle', config)
}

/** 上报一次网站访问（App 挂载时调用一次，后台用于访问次数 / 独立 IP 统计） */
export function recordVisit() {
  const config: LoadingAxiosRequestConfig = {
    showGlobalLoading: false,
    showGlobalError: false,
  }
  return http.post<unknown, { data: { code: number; msg: string; data: { recorded: boolean } } }>(
    '/stats/visit',
    undefined,
    config,
  )
}

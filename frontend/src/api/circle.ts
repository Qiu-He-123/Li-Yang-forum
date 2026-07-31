import { http, type LoadingAxiosRequestConfig } from './http'
import type { Circle, CircleDetail, Post } from '../types/api'

/** 圈子列表（含 is_joined 状态） */
export function listCircles(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Circle[] } }>('/circles', config)
}

/** 圈子详情 */
export function fetchCircle(slug: string) {
  return http.get<unknown, { data: { code: number; msg: string; data: CircleDetail } }>(`/circles/${slug}`)
}

/**
 * 圈子内帖子列表
 * 后端返回结构：{ items: Post[]; total: number; page: number; page_size: number; circle: Circle }
 */
export function listCirclePosts(
  slug: string,
  params: { type?: 'all' | 'essence' | 'image' | 'video'; page?: number; page_size?: number } = {},
) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: Post[]; total: number; page: number; page_size: number; circle: Circle } } }>(`/circles/${slug}/posts`, { params })
}

/** 加入圈子（幂等） */
export function joinCircle(slug: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: { id: number; slug: string; name: string; is_joined: boolean; member_count: number } } }>(
    `/circles/${slug}/join`,
  )
}

/** 退出圈子 */
export function leaveCircle(slug: string) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { id: number; slug: string; name: string; is_joined: boolean; member_count: number } } }>(
    `/circles/${slug}/join`,
  )
}

/** 我的足迹：我浏览过的圈子列表 */
export function listViewedCircles(limit = 20, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Circle[] } }>(
    '/circles/my/views/list',
    { ...config, params: { limit } },
  )
}

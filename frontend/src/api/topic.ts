import { http, type LoadingAxiosRequestConfig } from './http'
import type { Post } from '../types/api'

/** 话题实体 */
export interface Topic {
  id: number
  name: string
  post_count: number
  description: string | null
  creator_id: number | null
  is_followed?: boolean
}

/** 搜索话题（用于发帖时 # 话题联想） */
export function searchTopics(q: string, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Topic[] } }>('/topics/search', {
    ...config,
    params: { q },
  })
}

/** 热门话题列表（按 post_count 降序） */
export function hotTopics(limit = 10, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Topic[] } }>('/topics/hot', {
    ...config,
    params: { limit },
  })
}

/** 话题详情 */
export function getTopicDetail(id: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: Topic } }>(`/topics/${id}`)
}

/** 话题下的帖子列表 */
export function listTopicPosts(id: number, page = 1, page_size = 20) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: Post[]; total: number; page: number; page_size: number } } }>(
    `/topics/${id}/posts`,
    { params: { page, page_size } },
  )
}

/** 关注 / 取消关注话题（幂等切换） */
export function followTopic(id: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { is_followed: boolean } } }>(
    `/topics/${id}/follow`,
  )
}

import { http, type LoadingAxiosRequestConfig } from './http'
import type { Post } from '../types/api'
import type { PollCreate } from './poll'

export type PostView = 'all' | 'school' | 'hot' | 'latest'

export interface PostListParams {
  view?: PostView
  page?: number
  page_size?: number
  q?: string
  category?: string
  tag?: string
}

export interface PostCreatePayload {
  content: string
  title?: string | null
  is_original?: boolean
  /** 帖子是否含 AI 生成内容 */
  has_ai_content?: boolean
  image_urls: string[]
  is_anonymous: boolean
  /** 是否私密发布（不传时后端默认公开） */
  is_public?: boolean
  school_id: number
  category: string
  is_draft: boolean
  /** 阶段二：话题名（可空） */
  topic_name?: string | null
  /** 阶段二：位置（可空，最长 50 字） */
  location?: string | null
  /** 阶段二：@好友的用户 id 列表 */
  mention_user_ids?: number[]
  /** 阶段二：投票载荷 */
  poll?: PollCreate | null
}

export function listPosts(params: PostListParams = {}, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Post[] } }>('/posts', { ...config, params })
}

// P1：单帖详情
export function fetchPost(postId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: Post } }>(`/posts/${postId}`)
}

export function createPost(payload: PostCreatePayload, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: Post } }>(
    '/posts',
    payload,
    config,
  )
}

export function updatePost(postId: number, payload: Partial<PostCreatePayload>, config: LoadingAxiosRequestConfig = {}) {
  return http.patch(`/posts/${postId}`, payload, config)
}

export function deletePost(postId: number) {
  return http.delete(`/posts/${postId}`)
}

/** 相关推荐 */
export function fetchRelatedPosts(postId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Post[] } }>(
    `/posts/${postId}/related`,
    config,
  )
}

/** 分享计数（幂等 +1） */
export function sharePost(postId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { share_count: number } } }>(
    `/posts/${postId}/share`,
  )
}

/** 浏览计数（+1） */
export function viewPost(postId: number) {
  const config: LoadingAxiosRequestConfig = {
    showGlobalLoading: false,
    showGlobalError: false,
  }
  return http.post<unknown, { data: { code: number; msg: string; data: { view_count: number } } }>(
    `/posts/${postId}/view`,
    null,
    config,
  )
}

/** 阶段二：草稿列表（GET /posts/drafts） */
export function listDrafts() {
  return http.get<unknown, { data: { code: number; msg: string; data: Post[] } }>('/posts/drafts')
}

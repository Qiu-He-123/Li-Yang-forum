import { http, type LoadingAxiosRequestConfig } from './http'
import type { CommentItem } from '../types/api'

// T8-3：评论列表支持分页，返回 {items, total, page, page_size}
export function listComments(
  postId: number,
  page = 1,
  pageSize = 20,
  config: LoadingAxiosRequestConfig = {},
) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: CommentItem[]; total: number; page: number; page_size: number } } }>(
    `/posts/${postId}/comments`,
    { ...config, params: { page, page_size: pageSize } },
  )
}

export function createComment(postId: number, payload: { content: string; parent_id?: number | null }) {
  return http.post<unknown, { data: { code: number; msg: string; data: CommentItem & { post_comment_count: number } } }>(
    `/posts/${postId}/comments`,
    payload,
  )
}

export function deleteComment(postId: number, commentId: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { post_comment_count: number } } }>(
    `/posts/${postId}/comments/${commentId}`,
  )
}

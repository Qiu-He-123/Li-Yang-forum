import { http } from './http'
import type { ApiResponse } from '../types/api'

export interface FeedbackReply {
  id: number
  feedback_id: number
  replier_id: number
  replier_name: string | null
  content: string
  created_at: string
}

export interface Feedback {
  id: number
  user_id: number
  user_name: string | null
  category: string
  title: string
  content: string
  contact: string | null
  status: string // pending/replied/closed
  image_urls: string[] | null
  replies: FeedbackReply[]
  created_at: string
}

export interface FeedbackListResp {
  total: number
  items: Feedback[]
}

export interface FeedbackCreatePayload {
  category?: string
  title: string
  content: string
  contact?: string
  image_urls?: string[]
}

/** 创建意见反馈 */
export function createFeedback(payload: FeedbackCreatePayload) {
  return http.post<unknown, { data: ApiResponse<Feedback> }>('/feedback', payload)
}

/** 当前用户的反馈列表（分页） */
export function listMyFeedbacks(page = 1, pageSize = 20) {
  return http.get<unknown, { data: ApiResponse<FeedbackListResp> }>('/feedback', {
    params: { page, page_size: pageSize },
  })
}

/** 管理员：全部反馈列表（分页，可按状态过滤） */
export function listAllFeedbacks(page = 1, pageSize = 20, status?: string) {
  return http.get<unknown, { data: ApiResponse<FeedbackListResp> }>('/feedback/all', {
    params: { page, page_size: pageSize, status },
  })
}

/** 反馈详情 */
export function getFeedback(id: number) {
  return http.get<unknown, { data: ApiResponse<Feedback> }>(`/feedback/${id}`)
}

/** 管理员：回复反馈 */
export function replyFeedback(id: number, content: string) {
  return http.post<unknown, { data: ApiResponse<FeedbackReply> }>(`/feedback/${id}/reply`, {
    content,
  })
}

/** 关闭反馈（用户/管理员） */
export function closeFeedback(id: number) {
  return http.patch<unknown, { data: ApiResponse<{ closed: boolean; id: number }> }>(
    `/feedback/${id}/close`,
  )
}

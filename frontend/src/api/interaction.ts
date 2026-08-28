import { http } from './http'
import type { LikeResult, ReportResult } from '../types/api'

export type LikeTargetType = 'post' | 'comment'

export function likeTarget(targetType: LikeTargetType, targetId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: LikeResult } }>(`/likes/${targetType}/${targetId}`)
}

export function unlikeTarget(targetType: LikeTargetType, targetId: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: LikeResult } }>(`/likes/${targetType}/${targetId}`)
}

export function favoritePost(postId: number) {
  return http.post(`/favorites/${postId}`)
}

export function unfavoritePost(postId: number) {
  return http.delete(`/favorites/${postId}`)
}

export function reportTarget(payload: { target_type: 'post' | 'comment' | 'user'; target_id: number; reason: string }) {
  return http.post<unknown, { data: { code: number; msg: string; data: ReportResult } }>('/reports', payload)
}

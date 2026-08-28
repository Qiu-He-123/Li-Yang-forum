import { http, type LoadingAxiosRequestConfig } from './http'

/** 通用留言板（组局/活动/热门玩法） */
export type TargetType = 'gathering' | 'activity' | 'match'

export interface TargetCommentItem {
  id: number
  target_type: TargetType
  target_id: number
  parent_id: number | null
  content: string
  author: string
  author_avatar_url: string
  user_id: number | null
  created_at: string | null
}

export interface TargetCommentListResp {
  items: TargetCommentItem[]
  total: number
  page: number
  page_size: number
}

/** 留言列表（游客可看） */
export function listTargetComments(
  targetType: TargetType,
  targetId: number,
  page = 1,
  pageSize = 20,
  config: LoadingAxiosRequestConfig = {},
) {
  return http.get<unknown, { data: { code: number; msg: string; data: TargetCommentListResp } }>(
    `/comments/${targetType}/${targetId}`,
    { ...config, params: { page, page_size: pageSize } },
  )
}

/** 发表留言 / 回复留言（需登录） */
export function createTargetComment(
  targetType: TargetType,
  targetId: number,
  payload: { content: string; parent_id?: number | null },
) {
  return http.post<unknown, { data: { code: number; msg: string; data: TargetCommentItem } }>(
    `/comments/${targetType}/${targetId}`,
    payload,
  )
}

/** 删除留言（仅作者本人） */
export function deleteTargetComment(
  targetType: TargetType,
  targetId: number,
  commentId: number,
) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { deleted: boolean; remaining_count: number } } }>(
    `/comments/${targetType}/${targetId}/${commentId}`,
  )
}

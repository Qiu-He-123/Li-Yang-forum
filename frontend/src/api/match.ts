import { http, type LoadingAxiosRequestConfig } from './http'

/** 用户简要信息（匹配到的对方） */
export interface MatchPeer {
  id: number
  nickname: string
  avatar_url: string | null
  school_id: number
  /** @deprecated 已弃用，改用 age */
  grade: string | null
  /** 年龄（从生日动态计算，13-18；可能为 null） */
  age: number | null
  gender: 'male' | 'female' | 'unknown'
}

/** 匹配会话 */
export interface MatchSession {
  id: number
  user_a: number
  user_b: number
  status: 'active' | 'ended' | 'expired'
  expires_at: string | null
  ended_at: string | null
  mutual_follow: boolean
  created_at: string | null
  peer: MatchPeer | null
}

/** 入队响应 */
export interface EnqueueResult {
  status: 'waiting' | 'matched'
  queue_id?: number
  session?: MatchSession
}

/** 临时聊天消息 */
export interface MatchMessage {
  id: number
  session_id: number
  sender_id: number
  content: string
  created_at: string | null
}

/** 历史会话列表项 */
export interface MatchHistoryItem {
  id: number
  user_a: number
  user_b: number
  status: 'active' | 'ended' | 'expired'
  expires_at: string | null
  ended_at: string | null
  mutual_follow: boolean
  created_at: string | null
  peer: MatchPeer | null
}

export interface MatchHistory {
  items: MatchHistoryItem[]
  total: number
  page: number
  page_size: number
}

/** 入队 payload */
export interface MatchEnqueuePayload {
  /** @deprecated 已弃用，改用 age_min/age_max */
  grades?: string[]
  school_ids?: number[]
  tags?: string[]
  tag_required?: string[]
  target_gender?: 'male' | 'female' | 'any'
  /** 期望对方年龄下限（13-18，None 表示不限） */
  age_min?: number | null
  /** 期望对方年龄上限（13-18，None 表示不限） */
  age_max?: number | null
}

export function enqueueMatch(payload: MatchEnqueuePayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: EnqueueResult } }>('/match/queue', payload)
}

export function cancelMatch() {
  return http.post<unknown, { data: { code: number; msg: string; data: { ok: boolean } } }>('/match/cancel')
}

export function getActiveSession(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: MatchSession | null } }>('/match/active-session', config)
}

export function listSessionMessages(sessionId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: MatchMessage[] } }>(`/match/sessions/${sessionId}/messages`, config)
}

export function listMatchHistory(page = 1, pageSize = 20) {
  return http.get<unknown, { data: { code: number; msg: string; data: MatchHistory } }>('/match/history', {
    params: { page, page_size: pageSize },
  })
}

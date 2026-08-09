import { http, type LoadingAxiosRequestConfig } from './http'
import type { Badge } from '../types/api'

/** 漂流瓶作者信息（拾取到的瓶子暴露的作者基本信息） */
export interface BottleAuthor {
  author_id: number
  author_nickname: string | null
  author_avatar_url: string | null
  /** 作者佩戴的徽章 */
  author_badge?: Badge | null
  author_gender: 'male' | 'female' | 'unknown'
  /** @deprecated 已弃用，改用 author_age */
  author_grade: string | null
  /** 作者年龄（从生日动态计算，13-18；可能为 null） */
  author_age: number | null
}

/** 漂流瓶数据结构 */
export interface Bottle extends BottleAuthor {
  id: number
  school_id: number
  school_name: string | null
  content: string | null
  image_urls: string[]
  tags: string[]
  status: 'active' | 'picked' | 'recalled' | 'expired'
  /** 内容审核状态：pending(AI审核中) / approved / rejected / manual_review(人工审核中) */
  audit_status?: 'pending' | 'approved' | 'rejected' | 'manual_review'
  /** 未通过原因（rejected 时返回） */
  reject_reason?: string | null
  /** 联系方式（仅拾取者/作者可见，其他场景为 null） */
  contact: string | null
  created_at: string | null
  picked_at: string | null
  /** 拾取时返回的剩余次数 */
  remaining_picks_today?: number
  /** 我投放的瓶子：被拾取次数 */
  picked_count?: number
}

/** 我投放的瓶子列表响应 */
export interface MyBottlesResult {
  bottles: Bottle[]
  total: number
  picked_count: number
}

/** 拾取状态 */
export interface PickStatus {
  today_count: number
  daily_limit: number
  remaining: number
}

/** 投放瓶子 payload */
export interface BottleCreatePayload {
  content?: string | null
  image_urls?: string[]
  /** @deprecated 已弃用，后端会从用户 birthday 自动计算 author_age */
  grade?: string
  school_id: number
  tags?: string[]
  /** 联系方式（QQ/微信/手机等），拾取成功后对拾取者可见 */
  contact?: string | null
}

/** 拾取瓶子 payload */
export interface BottlePickPayload {
  /** @deprecated 已弃用，改用 age_min/age_max */
  grades?: string[]
  school_ids?: number[]
  /** 兼容字段：等同 tag_preferred（尽量有） */
  tags?: string[]
  /** 必须有的标签：瓶子必须包含这些标签才能被匹配到 */
  tag_required?: string[]
  /** 尽量有的标签：匹配候选中按重叠度排序优先 */
  tag_preferred?: string[]
  target_gender?: 'male' | 'female' | 'any'
  /** 期望作者年龄下限（13-18，None 表示不限） */
  age_min?: number | null
  /** 期望作者年龄上限（13-18，None 表示不限） */
  age_max?: number | null
}

/** 漂流瓶页统计 */
export interface BottleStats {
  online_count: number
  matching_count: number
  total_bottles: number
  today_picks: number
}

export function listBottleTags(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: string[] } }>('/bottles/tags', config)
}

export function createBottle(payload: BottleCreatePayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: Bottle } }>('/bottles', payload)
}

export function pickBottle(payload: BottlePickPayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: Bottle } }>('/bottles/pick', payload)
}

export function listMyBottles(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: MyBottlesResult } }>('/bottles/mine', config)
}

/** 作者收回瓶子（收回后不再可被拾取） */
export function recallBottle(bottleId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: Bottle } }>(`/bottles/${bottleId}/recall`)
}

export function listMyPicks(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Bottle[] } }>('/bottles/picks', config)
}

export function getPickStatus(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PickStatus } }>('/bottles/pick-status', config)
}

export function fetchBottleStats(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: BottleStats } }>('/stats/bottle', config)
}

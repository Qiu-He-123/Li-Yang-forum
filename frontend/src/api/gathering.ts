import { http, type LoadingAxiosRequestConfig } from './http'

/** 组局发起人/成员里的用户摘要 */
export interface GatheringHost {
  id: number
  nickname: string
  avatar: string | null
}

export interface GatheringMember {
  user_id: number
  nickname: string
  avatar: string | null
  is_host: boolean
  joined_at: string | null
}

/** 组局 */
export interface Gathering {
  id: number
  title: string
  /** online=线上 / offline=线下 */
  type: 'online' | 'offline'
  category: string
  start_time: string | null
  end_time: string | null
  location: string | null
  max_people: number
  joined_people: number
  description: string | null
  images: string[]
  /** recruiting=招募中 / cancelled=已取消 / ended=已结束 */
  status: 'recruiting' | 'cancelled' | 'ended'
  host: GatheringHost
  is_joined: boolean
  is_host: boolean
  created_at: string | null
  /** 详情接口附带 */
  members?: GatheringMember[]
}

export interface GatheringListResp {
  items: Gathering[]
  total: number
  page: number
  page_size: number
}

export interface GatheringCreatePayload {
  title: string
  type: 'online' | 'offline'
  category: string
  start_time: string
  end_time?: string | null
  location?: string | null
  max_people: number
  description?: string
  images?: string[]
}

/** 组局列表（默认仅招募中且未过截止时间，按开始时间升序；all_status=true 返回全部状态） */
export function listGatherings(
  params: {
    category?: string
    type?: 'online' | 'offline'
    all_status?: boolean
    page?: number
    page_size?: number
  } = {},
  config: LoadingAxiosRequestConfig = {},
) {
  return http.get<unknown, { data: { code: number; msg: string; data: GatheringListResp } }>(
    '/gatherings',
    { ...config, params },
  )
}

/** 组局分类列表 */
export function listGatheringCategories() {
  return http.get<unknown, { data: { code: number; msg: string; data: string[] } }>(
    '/gatherings/categories',
  )
}

/** 组局详情（含成员列表、报名状态） */
export function fetchGathering(id: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Gathering } }>(
    `/gatherings/${id}`,
    config,
  )
}

/** 我的组局（我发起的 + 我报名的） */
export function myGatherings() {
  return http.get<unknown, {
    data: { code: number; msg: string; data: { hosting: Gathering[]; joined: Gathering[] } }
  }>('/gatherings/mine')
}

/** 发布组局（发起人自动占用一个名额） */
export function createGathering(payload: GatheringCreatePayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: Gathering } }>(
    '/gatherings',
    payload,
  )
}

/** 报名组局 */
export function joinGathering(id: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: Gathering } }>(
    `/gatherings/${id}/join`,
  )
}

/** 退出组局 */
export function leaveGathering(id: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: Gathering } }>(
    `/gatherings/${id}/leave`,
  )
}

/** 取消组局（仅发起人） */
export function cancelGathering(id: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: Gathering } }>(
    `/gatherings/${id}/cancel`,
  )
}

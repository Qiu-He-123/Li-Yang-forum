import { http, type LoadingAxiosRequestConfig } from './http'
import type { Badge } from '../types/api'

/** 排行条目 */
export interface RankingItem {
  rank: number
  user_id: number
  nickname: string
  avatar_url: string
  badge: Badge | null
  school: string | null
  /** 排行分值（金币数 / 亲密度和 / 游戏分和 / 总分） */
  score: number
  /** 各排行附带的明细：pet_count / game_count / coins / affinity / game */
  extra?: {
    pet_count?: number
    game_count?: number
    coins?: number
    affinity?: number
    game?: number
  }
}

/** 排行接口响应：榜单 + 当前用户自己的名次（未登录为 null） */
export interface RankingResp {
  items: RankingItem[]
  total: number
  me: { rank: number; user_id: number; nickname: string; score: number } | null
}

interface RankingApiResp {
  code: number
  msg: string
  data: RankingResp
}

function fetchRanking(url: string, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: RankingApiResp }>(url, config)
}

/** 全部排行（金币 + 亲密度 + 游戏 总和） */
export function fetchAllRanking(config: LoadingAxiosRequestConfig = {}) {
  return fetchRanking('/rankings/all', config)
}

/** 金币排行 */
export function fetchCoinRanking(config: LoadingAxiosRequestConfig = {}) {
  return fetchRanking('/rankings/coins', config)
}

/** 宠物亲密度排行 */
export function fetchPetAffinityRanking(config: LoadingAxiosRequestConfig = {}) {
  return fetchRanking('/rankings/pet-affinity', config)
}

/** 游戏排行 */
export function fetchGameRanking(config: LoadingAxiosRequestConfig = {}) {
  return fetchRanking('/rankings/game', config)
}

/** 上报小游戏最佳战绩（Upsert，服务端取较大值） */
export function submitGameScore(
  gameKey: string,
  bestScore: number,
  config: LoadingAxiosRequestConfig = {},
) {
  return http.post<unknown, { data: { code: number; msg: string; data: { ok: boolean; best_score: number } } }>(
    '/rankings/game/score',
    { game_key: gameKey, best_score: bestScore },
    config,
  )
}

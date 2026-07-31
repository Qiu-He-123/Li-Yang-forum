import { http, type LoadingAxiosRequestConfig } from './http'
import type { FollowUser } from '../types/api'

/** 关注用户（幂等，触发通知） */
export function followUser(userId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { following: boolean } } }>(
    `/users/${userId}/follow`,
  )
}

/** 取关用户 */
export function unfollowUser(userId: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { following: boolean } } }>(
    `/users/${userId}/follow`,
  )
}

/** 是否已关注 */
export function checkFollowing(userId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { following: boolean } } }>(
    `/users/${userId}/is-following`,
    config,
  )
}

/** 关注列表 */
export function listFollowing(userId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: FollowUser[] } }>(
    `/users/${userId}/following`,
    config,
  )
}

/** 粉丝列表 */
export function listFollowers(userId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: FollowUser[] } }>(`/users/${userId}/followers`)
}

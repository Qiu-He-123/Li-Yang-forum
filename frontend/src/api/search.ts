import { http, type LoadingAxiosRequestConfig } from './http'
import type { HotSearch, SearchHistory } from '../types/api'

/** 当前用户搜索历史（最近 20 条，去重） */
export function listSearchHistory(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: SearchHistory[] } }>('/search/history', config)
}

/** 清空搜索历史 */
export function clearSearchHistory() {
  return http.delete<unknown, { data: { code: number; msg: string; data: {} } }>('/search/history')
}

/** 删除单条搜索历史 */
export function deleteSearchHistory(keyword: string) {
  return http.delete<unknown, { data: { code: number; msg: string; data: {} } }>(
    `/search/history/${encodeURIComponent(keyword)}`,
  )
}

/** 热搜榜（前 10） */
export function listHotSearch(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: HotSearch[] } }>('/search/hot', config)
}

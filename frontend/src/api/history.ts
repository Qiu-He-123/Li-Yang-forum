import { http } from './http'

export interface HistoryItem {
  history_id: number
  post_id: number
  title: string | null
  content: string
  image_urls: string[]
  category: string
  author_id: number
  author_nickname: string | null
  author_avatar_url: string | null
  like_count: number
  comment_count: number
  view_count: number
  viewed_at: string | null
}

export interface HistoryListResp {
  items: HistoryItem[]
  total: number
  page: number
  page_size: number
}

/** 浏览历史列表（分页） */
export function listHistory(page = 1, pageSize = 20) {
  return http.get<unknown, { data: { code: number; msg: string; data: HistoryListResp } }>('/history', {
    params: { page, page_size: pageSize },
  })
}

/** 删除单条浏览记录 */
export function deleteHistoryItem(historyId: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { deleted: boolean; id: number } } }>(
    `/history/${historyId}`,
  )
}

/** 清空浏览历史 */
export function clearHistory() {
  return http.delete<unknown, { data: { code: number; msg: string; data: { cleared: boolean; count: number } } }>(
    '/history',
  )
}

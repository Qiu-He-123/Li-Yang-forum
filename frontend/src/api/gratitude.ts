import { http } from './http'

export interface GratitudeItem {
  id: number
  name: string
  avatar_url: string | null
  bio: string | null
  detail: string | null
  sort_order: number
  is_active: boolean
}

/** 用户侧：上架名单列表 */
export function fetchGratitudeList() {
  return http.get<unknown, { data: { code: number; msg: string; data: GratitudeItem[] } }>('/gratitude-list')
}

/** 用户侧：单条详情 */
export function fetchGratitudeDetail(id: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: GratitudeItem } }>(`/gratitude-list/${id}`)
}

/** 管理侧：全部名单 */
export function adminFetchGratitudeList() {
  return http.get<unknown, { data: { code: number; msg: string; data: GratitudeItem[] } }>('/admin/gratitude-list')
}

/** 管理侧：新增 */
export function adminCreateGratitude(payload: Partial<GratitudeItem>) {
  return http.post<unknown, { data: { code: number; msg: string; data: GratitudeItem } }>(
    '/admin/gratitude-list',
    payload,
  )
}

/** 管理侧：编辑 */
export function adminUpdateGratitude(id: number, payload: Partial<GratitudeItem>) {
  return http.put<unknown, { data: { code: number; msg: string; data: GratitudeItem } }>(
    `/admin/gratitude-list/${id}`,
    payload,
  )
}

/** 管理侧：删除 */
export function adminDeleteGratitude(id: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: boolean } }>(
    `/admin/gratitude-list/${id}`,
  )
}

/** 管理侧：上传头像（jpg/png/webp/gif，≤5MB），返回 { url } */
export function adminUploadGratitudeAvatar(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return http.post<unknown, { data: { code: number; msg: string; data: { url: string } } }>(
    '/admin/gratitude-list/upload-avatar',
    formData,
    { timeout: 120_000 },
  )
}
import { http } from './http'
import type { ImageUploadResult } from '../types/api'

export function uploadImage(file: File, onProgress?: (percent: number) => void) {
  const formData = new FormData()
  formData.append('file', file)
  // 注意：不要手动设置 Content-Type，axios 会自动设置 multipart/form-data 并附带 boundary。
  // 手动设置会导致 boundary 丢失，后端无法解析，上传一直卡住。
  return http.post<unknown, { data: { code: number; msg: string; data: ImageUploadResult } }>(
    '/images',
    formData,
    {
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          onProgress(percent)
        }
      },
    },
  )
}

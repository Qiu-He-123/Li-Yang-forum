import { http, type LoadingAxiosRequestConfig } from './http'
import type { ImageUploadResult, MyImage } from '../types/api'

export function uploadImage(
  file: File,
  onProgress?: (percent: number) => void,
  purpose: 'post' | 'avatar' | 'background' = 'post',
) {
  const formData = new FormData()
  formData.append('file', file)
  // 注意：不要手动设置 Content-Type，axios 会自动设置 multipart/form-data 并附带 boundary。
  // 手动设置会导致 boundary 丢失，后端无法解析，上传一直卡住。
  const config: LoadingAxiosRequestConfig = {
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total && onProgress) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    },
    // Bug 修复：上传图片时不显示全屏遮罩，避免用户误以为"卡住不动"。
    // PostEditor 已有每张图片的局部进度条 + 百分比显示，足够反馈上传状态。
    showGlobalLoading: false,
    showGlobalError: true,
    // 单张图片上传允许更长超时（5MB × 慢网络），避免大图上传被 30s 默认超时打断
    timeout: 120_000,
  }
  const params: Record<string, string> = {}
  if (purpose === 'avatar' || purpose === 'background') {
    params.purpose = purpose
  }
  return http.post<unknown, { data: { code: number; msg: string; data: ImageUploadResult } }>(
    '/images',
    formData,
    { ...config, params: Object.keys(params).length ? params : undefined },
  )
}

/** 学生认证照片私密上传（P0-1：走隔离存储，只能本人/管理员读取） */
export function uploadVerificationImage(file: File, onProgress?: (percent: number) => void) {
  const formData = new FormData()
  formData.append('file', file)
  const config: LoadingAxiosRequestConfig = {
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total && onProgress) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    },
    showGlobalLoading: false,
    showGlobalError: true,
    timeout: 120_000,
  }
  return http.post<unknown, { data: { code: number; msg: string; data: ImageUploadResult } }>(
    '/images/verification',
    formData,
    config,
  )
}

/** 个人素材库：当前用户历史上传的图片（最新在前） */
export function listMyImages(page = 1, pageSize = 60) {
  const config: LoadingAxiosRequestConfig = {
    params: { page, page_size: pageSize },
    // 素材库由发帖页主动打开，不需要全屏 loading / 全局错误提示
    showGlobalLoading: false,
    showGlobalError: false,
  }
  return http.get<
    unknown,
    {
      data: {
        code: number
        msg: string
        data: { items: MyImage[]; total: number; page: number; page_size: number }
      }
    }
  >('/images', config)
}

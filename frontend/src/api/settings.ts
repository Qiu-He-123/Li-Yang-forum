import { http, type LoadingAxiosRequestConfig } from './http'

export interface PublicSettings {
  marquee_text: string
  marquee_items: string[]
}

/** 首页等公开页面读取的轻量配置（当前：首页滚动字幕内容）。 */
export function fetchPublicSettings() {
  const config: LoadingAxiosRequestConfig = {
    showGlobalLoading: false,
    showGlobalError: false,
  }
  return http.get<unknown, { data: { code: number; msg: string; data: PublicSettings } }>(
    '/settings/public',
    config,
  )
}

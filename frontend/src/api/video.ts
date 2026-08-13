import { http, type LoadingAxiosRequestConfig } from './http'

export interface VideoParseResult {
  platform: string
  title: string
  cover: string
  author: string
}

const silentConfig: LoadingAxiosRequestConfig = { showGlobalLoading: false }

/** 解析抖音/快手分享链接（预览，不发布）；静默请求，不弹全屏加载遮罩 */
export function parseVideoShare(text: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: VideoParseResult } }>(
    '/videos/parse',
    { text },
    silentConfig,
  )
}

/** 解析并发布视频帖（category=视频，直链播放模式）；静默请求，不弹全屏加载遮罩 */
export function publishVideoShare(text: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: { post: unknown; record: VideoParseResult } } }>(
    '/videos/publish',
    { text },
    silentConfig,
  )
}

/** 直链过期后重新解析换新直链 */
export function refreshVideoLink(postId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { video_url: string } } }>(
    '/videos/refresh-link',
    { post_id: postId },
    silentConfig,
  )
}

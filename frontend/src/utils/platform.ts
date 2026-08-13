import { openCaptchaGate } from '../composables/useCaptchaGate'
import { getDownloadToken } from '../api/appDownload'

/**
 * 平台 / 运行环境判断。
 *
 * 立洋社区安卓 App 是套壳 WebView，MainActivity 里自定义了 UA 后缀
 * "LYCommunityApp"，网页端可用它区分 App 与浏览器。
 */

/** 是否运行在立洋社区 App（套壳 WebView）内 */
export function isAppEnv(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    navigator.userAgent.includes('LYCommunityApp')
  )
}

/** 跳转下载手机端 App（防刷下载：先过验证码换一次性令牌再跳转） */
export async function downloadApp(): Promise<void> {
  if (typeof window === 'undefined') return
  const result = await openCaptchaGate('download')
  if (result.ok && result.downloadToken) {
    window.location.href = `/api/app-download?token=${result.downloadToken}`
  }
}

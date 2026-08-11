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

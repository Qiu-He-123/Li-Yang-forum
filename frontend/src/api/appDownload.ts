import { http } from './http'

export function getDownloadToken(payload: { captcha_id: string; captcha_text: string }) {
  return http.post<
    unknown,
    {
      data: {
        code: number
        msg: string
        data: { download_token: string; expires_in: number }
      }
    }
  >('/app-download/token', payload)
}

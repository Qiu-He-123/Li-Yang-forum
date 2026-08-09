import { http } from './http'

/** 学生认证申请详情 */
export interface VerificationApplication {
  id: number
  user_id: number
  user_nickname?: string | null
  user_username?: string | null
  image_url: string
  note: string | null
  status: 'pending' | 'approved' | 'rejected'
  reviewer_id: number | null
  reviewer_username?: string | null
  reviewed_at: string | null
  reject_reason: string | null
  granted_invite_code: string | null
  created_at: string | null
}

/** 当前用户的认证状态 */
export interface MyVerificationStatus {
  verification_status: 'unverified' | 'verified'
  latest_application: VerificationApplication | null
  pending_count: number
}

/** 管理员视角的申请列表分页 */
export interface VerificationListPage {
  items: VerificationApplication[]
  total: number
  page: number
  page_size: number
}

// ============ 用户端 ============

export function getMyVerificationStatus() {
  return http.get<unknown, { data: { code: number; msg: string; data: MyVerificationStatus } }>('/users/me/verification')
}

export function submitVerification(payload: { image_id: number; note?: string | null }) {
  return http.post<unknown, { data: { code: number; msg: string; data: VerificationApplication } }>('/users/me/verification', payload)
}

// ============ 管理员端 ============

/** 种子邀请码记录 */
export interface SeedCode {
  id: number
  code: string
  note: string | null
  batch_no: string | null
  /** unused(未使用) / reserved(待使用) / used(已使用) */
  status: 'unused' | 'reserved' | 'used'
  /** 待使用状态：由哪位管理员复制带走 */
  reserved_by: number | null
  reserved_by_username?: string | null
  reserved_at: string | null
  used_by: number | null
  used_by_username?: string | null
  used_at: string | null
  created_at: string | null
}

export interface SeedCodeListPage {
  items: SeedCode[]
  total: number
  counts: { unused: number; reserved: number; used: number }
  page: number
  page_size: number
}

export interface GenerateSeedCodesResult {
  batch_no: string
  count: number
  codes: string[]
}

export function adminListVerifications(params: { page?: number; page_size?: number; status?: 'pending' | 'approved' | 'rejected' } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: VerificationListPage } }>('/admin/verifications', { params })
}

export function adminReviewVerification(verificationId: number, payload: { action: 'approve' | 'reject'; reject_reason?: string }) {
  return http.post<unknown, { data: { code: number; msg: string; data: VerificationApplication } }>(`/admin/verifications/${verificationId}/review`, payload)
}

export function adminGenerateSeedCodes(payload: { count?: number; note?: string; batch_no?: string }) {
  return http.post<unknown, { data: { code: number; msg: string; data: GenerateSeedCodesResult } }>('/admin/seed-codes/generate', payload)
}

export function adminListSeedCodes(params: { page?: number; page_size?: number; batch_no?: string; status?: 'unused' | 'reserved' | 'used' } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: SeedCodeListPage } }>('/admin/seed-codes', { params })
}

export function adminReserveSeedCodes(payload: { count?: number; note?: string; batch_no?: string }) {
  return http.post<unknown, { data: { code: number; msg: string; data: GenerateSeedCodesResult } }>(
    '/admin/seed-codes/reserve',
    payload,
  )
}

export function adminReleaseSeedCode(codeId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { ok: boolean; code: string; status: string } } }>(
    `/admin/seed-codes/${codeId}/release`,
  )
}

export function adminDeleteSeedCode(codeId: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { ok: boolean } } }>(`/admin/seed-codes/${codeId}`)
}

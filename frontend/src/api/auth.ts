import { http } from './http'
import type { LoadingAxiosRequestConfig } from './http'
import type { AuthResult } from '../types/api'

export interface RegisterPayload {
  nickname: string
  username: string
  password: string
  confirm_password: string
  school_id: number
  agreed: boolean
  qq?: string | null
  invite_code?: string | null
}

export interface LoginPayload {
  username: string
  password: string
}

export function register(payload: RegisterPayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: AuthResult } }>('/auth/register', payload)
}

export function login(payload: LoginPayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: AuthResult } }>('/auth/login', payload)
}

export function logout() {
  return http.post('/auth/logout')
}

export function fetchMe(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: AuthResult } }>('/auth/me', config)
}

export interface ChangePasswordPayload {
  old_password: string
  new_password: string
  confirm_password: string
}

// T5-2：修改密码。后端校验旧密码 → 更新哈希 → 重发 token Cookie。
export function changePassword(payload: ChangePasswordPayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: AuthResult } }>(
    '/auth/change-password',
    payload,
  )
}

// ============ 邀请码系统 ============

export interface InviteCodeApplyPayload {
  code: string
}

export function applyInviteCode(payload: InviteCodeApplyPayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: {
    verification_status: string
    verified_at?: string
    inviter_id?: number | null
    message?: string
  } } }>('/auth/apply-invite-code', payload)
}

export interface MyInviteCodeInfo {
  code: string
  can_share: boolean
  cooldown_remaining: number
  is_frozen: boolean
  frozen_remaining: number
  verification_status: string
}

export function getMyInviteCode(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: MyInviteCodeInfo } }>('/auth/invite-code', config)
}

export interface VerificationStatusInfo {
  verification_status: string
  verified_at: string | null
  invited_by: number | null
  qq: string | null
}

export function getVerificationStatus(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: VerificationStatusInfo } }>('/auth/verification-status', config)
}

export function updateQQ(qq: string | null) {
  return http.patch<unknown, { data: { code: number; msg: string; data: { qq: string | null } } }>('/auth/qq', { qq })
}

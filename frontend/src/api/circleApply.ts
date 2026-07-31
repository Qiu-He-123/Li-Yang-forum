import { http } from './http'
import type { CircleApply, CircleAdmin } from '../types/api'

/** 阶段四：申请创建吧 */
export interface ApplyCreateCirclePayload {
  name: string
  slug: string
  description?: string
  icon?: string
  color?: string
}

/** 用户申请建吧（需登录） */
export function applyCreateCircle(data: ApplyCreateCirclePayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: CircleApply } }>(
    '/circles/apply',
    data,
  )
}

/** 我的申请列表（需登录） */
export function listMyApplies() {
  return http.get<unknown, { data: { code: number; msg: string; data: CircleApply[] } }>(
    '/circles/my-applies',
  )
}

/** 管理员：待审核吧列表（status 可选，返回所有用户申请的吧） */
export function listPendingCircles(status?: 'pending' | 'approved' | 'rejected') {
  return http.get<unknown, { data: { code: number; msg: string; data: CircleApply[] } }>(
    '/admin/circles/pending',
    { params: status ? { status } : {} },
  )
}

/** 管理员：审核吧申请 */
export function auditCircle(categoryId: number, approved: boolean, rejectReason?: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: CircleApply } }>(
    `/admin/circles/${categoryId}/audit`,
    { approved, reject_reason: rejectReason || null },
  )
}

/** 查看吧主列表 */
export function listCircleAdmins(slug: string) {
  return http.get<unknown, { data: { code: number; msg: string; data: CircleAdmin[] } }>(
    `/circles/${slug}/admins`,
  )
}

/** 任命管理员（仅吧主） */
export function addCircleAdmin(slug: string, userId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: CircleAdmin } }>(
    `/circles/${slug}/admins`,
    null,
    { params: { user_id: userId } },
  )
}

/** 移除管理员（仅吧主） */
export function removeCircleAdmin(slug: string, userId: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { id: number; user_id: number } } }>(
    `/circles/${slug}/admins/${userId}`,
  )
}

/** 吧主删帖 */
export function deletePostAsCircleAdmin(slug: string, postId: number) {
  return http.delete<unknown, { data: { code: number; msg: string; data: { post_id: number; circle_id: number } } }>(
    `/circles/${slug}/posts/${postId}`,
  )
}

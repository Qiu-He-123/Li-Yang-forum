import axios from 'axios'
import { http } from './http'
import type { Badge } from '../types/api'

// 管理员 API 独立实例：admin_token Cookie 由浏览器自动携带（withCredentials），
// 但 admin 接口不走用户 /api/http 拦截器中的 refresh 逻辑（admin_token 不通过 refresh 续期）。

export interface AdminLoginPayload {
  username: string
  password: string
}

export interface AdminInfo {
  id: number
  username: string
  role: string
}

export function adminLogin(payload: AdminLoginPayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: AdminInfo } }>(
    '/admin/login',
    payload,
  )
}

export function adminLogout() {
  return http.post('/admin/logout')
}

// ============ 统计 ============

export interface AdminStats {
  overview: { user_count: number; post_count: number; comment_count: number; report_count: number }
  pending: { posts: number; comments: number; reports: number }
  today: { new_users: number; new_posts: number; new_comments: number }
  trend_7d: Array<{ date: string; posts: number; users: number }>
  circle_distribution: Array<{ name: string; count: number }>
  report_status: Record<string, number>
}

export function adminStats() {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminStats } }>('/admin/stats')
}

// ============ 帖子 ============

export interface AdminPost {
  id: number
  title: string | null
  content: string
  category: string
  school: string | null
  author_id: number
  author: string | null
  author_avatar_url: string | null
  ai_status: string
  is_public: boolean
  is_anonymous: boolean
  image_urls: string[]
  tags: string[]
  like_count: number
  comment_count: number
  view_count: number
  share_count: number
  created_at: string | null
}

export interface PageResp<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export function adminListPosts(params: { page?: number; page_size?: number; keyword?: string; ai_status?: string } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminPost> } }>('/admin/posts', { params })
}

export function adminGetPost(postId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminPost } }>(`/admin/posts/${postId}`)
}

export function adminDeletePost(postId: number, reason: string) {
  return http.post(`/admin/posts/${postId}/delete`, { reason })
}

// ============ 系统设置 ============

export interface SystemSetting {
  key: string
  value: string
  description?: string | null
}

export function adminListSettings() {
  return http.get<unknown, { data: { code: number; msg: string; data: SystemSetting[] } }>('/admin/settings')
}

export function adminUpdateSettings(settings: Record<string, string>) {
  return http.put('/admin/settings', { settings })
}

// ============ 推荐探索 ============

export interface ExploreSummary {
  impressions: number
  click_count: number
  ctr: number
  like_count: number
  comment_count: number
  interaction_count: number
  interaction_rate: number
}

export interface ExploreTopPost {
  post_id: number
  title: string | null
  category: string
  impressions: number
  click_count: number
  like_count: number
  comment_count: number
  ctr: number
}

export interface ExploreImpressionLog {
  id: number
  post_id: number
  target_id: number | null
  title: string | null
  user_id: number | null
  nickname: string | null
  scene: string
  page: number
  created_at: string
}

export interface ExploreStats {
  summary: ExploreSummary
  top_posts: ExploreTopPost[]
  recent_logs: ExploreImpressionLog[]
}

export function adminExploreStats() {
  return http.get<unknown, { data: { code: number; msg: string; data: ExploreStats } }>('/admin/explore/stats')
}

export function adminAuditPost(postId: number, aiStatus: string, rejectReason?: string) {
  return http.patch(`/admin/posts/${postId}/audit`, { ai_status: aiStatus, reject_reason: rejectReason })
}

// ============ 评论 ============

export interface AdminComment {
  id: number
  post_id: number
  content: string
  user_id: number
  author: string | null
  ai_status: string
  like_count: number
  created_at: string | null
}

export function adminListComments(params: { page?: number; page_size?: number; keyword?: string; ai_status?: string } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminComment> } }>('/admin/comments', { params })
}

export function adminGetComment(commentId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminComment } }>(`/admin/comments/${commentId}`)
}

export function adminDeleteComment(commentId: number) {
  return http.delete(`/admin/comments/${commentId}`)
}

export function adminAuditComment(commentId: number, aiStatus: string, rejectReason?: string) {
  return http.patch(`/admin/comments/${commentId}/audit`, { ai_status: aiStatus, reject_reason: rejectReason })
}

// ============ 用户 ============

export interface AdminUser {
  id: number
  nickname: string
  phone: string
  school: string | null
  /** @deprecated 已弃用，改用 age */
  grade: string | null
  /** 年龄（从生日动态计算；可能为 null） */
  age: number | null
  avatar_url: string | null
  bio: string | null
  /** 当前佩戴的徽章 */
  wearing_badge?: Badge | null
  /** 已拥有徽章列表（"图标 名称" 文本） */
  badge_names?: string[]
  is_active: boolean
  post_count: number
  following_count: number
  followers_count: number
  created_at: string | null
}

export function adminListUsers(params: { page?: number; page_size?: number; keyword?: string } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminUser> } }>('/admin/users', { params })
}

export interface AdminUserBrief {
  id: number
  username: string
  nickname: string
  avatar_url: string | null
  school: string | null
}

export function adminGetUser(userId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminUserBrief } }>(`/admin/users/${userId}`)
}

export function adminUpdateUser(userId: number, payload: Partial<AdminUser>) {
  return http.patch(`/admin/users/${userId}`, payload)
}

// ============ 举报 ============

export interface AdminReport {
  id: number
  reporter_id: number
  reporter_nickname?: string | null
  target_type: string
  target_id: number
  reason: string
  ai_summary: string | null
  status: string
  created_at: string | null
  target?: AdminPost | AdminComment | AdminUser | null
}

export function adminListReports(params: { status?: string; page?: number; page_size?: number } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminReport> } }>('/admin/reports', { params })
}

export function adminGetReport(reportId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminReport } }>(`/admin/reports/${reportId}`)
}

export function adminHandleReport(reportId: number, status: string) {
  return http.patch(`/admin/reports/${reportId}`, { status })
}

// ============ 公告 ============

export interface AdminAnnouncement {
  id: number
  title: string
  content: string
  school_id: number | null
  is_active: boolean
  created_at: string | null
}

export interface AnnouncementCreatePayload {
  title: string
  content: string
  school_id?: number | null
}

export function adminListAnnouncements(params: { page?: number; page_size?: number } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminAnnouncement> } }>('/admin/announcements', { params })
}

export function adminCreateAnnouncement(payload: AnnouncementCreatePayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: { id: number } } }>(
    '/admin/announcements',
    payload,
  )
}

export function adminUpdateAnnouncement(annId: number, payload: Partial<AdminAnnouncement>) {
  return http.patch(`/admin/announcements/${annId}`, payload)
}

export function adminDeleteAnnouncement(annId: number) {
  return http.delete(`/admin/announcements/${annId}`)
}

// ============ 日志 ============

export interface AdminLog {
  id: number
  user_id?: number | null
  admin_id?: number | null
  action: string
  detail?: string | null
  ip?: string | null
  created_at: string | null
}

export interface AdminLoginLog {
  id: number
  user_id: number | null
  phone: string | null
  ip: string | null
  device: string | null
  success: boolean
  created_at: string | null
}

export function adminListLogs(params: { page?: number; page_size?: number; admin_id?: number; action?: string } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminLog> } }>('/admin/logs', { params })
}

export function adminListUserLogs(params: { user_id?: number; action?: string; page?: number; page_size?: number } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminLog> } }>('/admin/user-logs', {
    params,
  })
}

export function adminListLoginLogs(params: { page?: number; page_size?: number; user_id?: number; success?: boolean } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminLoginLog> } }>('/admin/login-logs', { params })
}

// 用于 admin_token 校验：裸 axios 调一次 /admin/posts，403 即未登录
export async function pingAdmin(): Promise<boolean> {
  try {
    const { data } = await axios.get('/api/admin/posts', { withCredentials: true })
    return data.code === 0
  } catch {
    return false
  }
}

// ============ 系统设置 / DeepSeek 配置 ============

export interface DeepSeekConfig {
  enabled: boolean
  api_key: string
  base_url: string
  model: string
  auto_delete_days: number
  /** 需要审核的内容范围：post 帖子 / comment 评论 / bottle 漂流瓶 / image 含图帖子转人工 */
  audit_scope: string[]
  /** 转人工复核的触发条件：ai_unavailable / violation / high_severity / sensitive_category */
  manual_review_triggers: string[]
}

export interface DeepSeekStatus {
  enabled: boolean
  api_key_configured: boolean
  api_key_masked: string
  base_url: string
  model: string
  auto_delete_days: number
  audit_scope: string[]
  manual_review_triggers: string[]
}

export interface DeepSeekTestResult {
  ok: boolean
  msg: string
  sample?: {
    pass: boolean
    reason: string
    category: string
    severity: string
  }
}

export interface DeepSeekAuditResult {
  pass: boolean
  reason: string
  category: string
  severity: string
  skipped?: boolean
  /** 使用的审核场景：post / comment / bottle / generic */
  content_type?: string
}

export function adminGetDeepSeekConfig() {
  return http.get<unknown, { data: { code: number; msg: string; data: DeepSeekConfig } }>('/admin/deepseek/config')
}

export function adminUpdateDeepSeekConfig(payload: Partial<DeepSeekConfig>) {
  return http.put<unknown, { data: { code: number; msg: string; data: DeepSeekConfig } }>(
    '/admin/deepseek/config',
    payload,
  )
}

export function adminDeepSeekTest() {
  return http.post<unknown, { data: { code: number; msg: string; data: DeepSeekTestResult } }>('/deepseek/test')
}

export function adminGetDeepSeekPrompts() {
  return http.get<unknown, { data: { code: number; msg: string; data: { prompts: Record<string, string>; labels: Record<string, string> } } }>(
    '/deepseek/prompts',
  )
}

export function adminDeepSeekAuditText(content: string, contentType = 'generic') {
  return http.post<unknown, { data: { code: number; msg: string; data: DeepSeekAuditResult } }>('/deepseek/audit', {
    content,
    content_type: contentType,
  })
}

export function adminDeepSeekAuditPost(postId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { post_id: number; ai_status: string; audit_result: DeepSeekAuditResult } } }>(
    `/deepseek/audit-post/${postId}`,
  )
}

export function adminDeepSeekAuditComment(commentId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { comment_id: number; ai_status: string; audit_result: DeepSeekAuditResult } } }>(
    `/deepseek/audit-comment/${commentId}`,
  )
}

export function adminCleanupAudit() {
  return http.post<unknown, { data: { code: number; msg: string; data: { enabled: boolean; days: number; deleted_posts: number; deleted_comments: number } } }>(
    '/admin/audit/cleanup',
  )
}

// ============ 封号管理 ============

export interface BanRecord {
  id: number
  user_id: number
  user_nickname: string | null
  user_phone: string | null
  admin_id: number | null
  admin_name: string | null
  reason: string
  duration_hours: number
  ban_until: string | null
  banned_at: string
  unbanned_at: string | null
  status: string
  appealable: boolean
}

export function adminListBanRecords(params: { page?: number; page_size?: number; user_id?: number; status?: string } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<BanRecord> } }>('/admin/ban-records', { params })
}

export function adminBanUser(userId: number, payload: { reason: string; duration_hours?: number; appealable?: boolean }) {
  return http.post(`/admin/users/${userId}/ban`, payload)
}

export function adminUnbanUser(userId: number) {
  return http.post(`/admin/users/${userId}/unban`)
}

// ============ 申诉管理 ============

export interface AdminAppeal {
  id: number
  user_id: number
  user_nickname: string | null
  ban_record_id: number | null
  reason: string
  status: string
  reviewed_by: number | null
  reviewer_name: string | null
  reviewed_at: string | null
  review_comment: string | null
  created_at: string
}

export function adminListAppeals(params: { page?: number; page_size?: number; status?: string } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AdminAppeal> } }>('/admin/appeals', { params })
}

export function adminReviewAppeal(appealId: number, payload: { status: string; review_comment?: string }) {
  return http.patch(`/admin/appeals/${appealId}/review`, payload)
}

// ============ AI 审核日志 ============

export interface AuditLog {
  id: number
  target_type: string
  target_id: number
  user_id: number | null
  ai_provider: string
  result: string
  reason: string
  category: string
  severity: string
  content_snapshot: string
  created_at: string
}

export function adminListAuditLogs(params: {
  page?: number
  page_size?: number
  target_type?: string
  result?: string
  user_id?: number
  category?: string
  severity?: string
} = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<AuditLog> } }>('/admin/audit-logs', { params })
}

// ============ 警告值系统管理 ============

export interface WarningConfig {
  warn_threshold: number
  temp_ban_threshold: number
  temp_ban_hours: number
  perm_ban_threshold: number
  violation_base_score: number
  checkin_reduce: number
  post_reduce: number
  comment_reduce: number
  updated_at: string | null
}

export interface WarningLog {
  id: number
  user_id: number
  delta: number
  score_after: number
  reason: string
  source: string
  related_type: string | null
  related_id: number | null
  operator_id: number | null
  created_at: string | null
}

export interface AdminAdjustWarningResult {
  user_id: number
  old_score: number
  new_score: number
  triggered_ban: boolean
}

export function adminGetWarningConfig() {
  return http.get<unknown, { data: { code: number; msg: string; data: WarningConfig } }>('/admin/warning-config')
}

export function adminUpdateWarningConfig(payload: Partial<WarningConfig>) {
  return http.put<unknown, { data: { code: number; msg: string; data: WarningConfig } }>(
    '/admin/warning-config',
    payload,
  )
}

export function adminAdjustUserWarning(userId: number, delta: number, reason: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: AdminAdjustWarningResult } }>(
    `/admin/users/${userId}/warning`,
    { delta, reason },
  )
}

export function adminListUserWarningLogs(userId: number, params: { page?: number; page_size?: number } = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PageResp<WarningLog> } }>(
    `/admin/users/${userId}/warning-logs`,
    { params },
  )
}

// ============ 图片人工审核（图片不走 AI 审核） ============

export interface AdminImage {
  id: number
  url: string
  mime_type: string
  size_bytes: number
  is_private: boolean
  audit_status: 'pending' | 'approved' | 'rejected'
  user_id: number | null
  user_nickname: string | null
  used_in_posts: number
  created_at: string | null
}

export interface AdminImageListPage {
  items: AdminImage[]
  total: number
  counts: { pending: number; approved: number; rejected: number }
  page: number
  page_size: number
}

export function adminListImages(params: {
  status?: 'pending' | 'approved' | 'rejected'
  keyword?: string
  page?: number
  page_size?: number
} = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminImageListPage } }>(
    '/admin/images',
    { params },
  )
}

export function adminReviewImage(
  imageId: number,
  payload: { action: 'approve' | 'reject'; reject_reason?: string },
) {
  return http.post<
    unknown,
    {
      data: {
        code: number
        msg: string
        data: { id: number; url: string; audit_status: string; related_posts: number[] }
      }
    }
  >(`/admin/images/${imageId}/review`, payload)
}

// ============ 漂流瓶审核（AI 审核 + 人工兜底） ============

export interface AdminBottle {
  id: number
  author_id: number
  author_nickname: string | null
  author_age: number | null
  author_gender: string
  school_id: number
  school_name: string | null
  content: string | null
  image_urls: string[]
  tags: string[]
  status: string
  audit_status: 'pending' | 'approved' | 'rejected' | 'manual_review'
  reject_reason: string | null
  created_at: string | null
}

export interface AdminBottleListPage {
  items: AdminBottle[]
  total: number
  counts: { pending: number; approved: number; rejected: number; manual_review: number }
  page: number
  page_size: number
}

export function adminListBottles(params: {
  status?: 'pending' | 'approved' | 'rejected' | 'manual_review'
  keyword?: string
  page?: number
  page_size?: number
} = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: AdminBottleListPage } }>(
    '/admin/bottles',
    { params },
  )
}

export function adminReviewBottle(
  bottleId: number,
  payload: { action: 'approve' | 'reject'; reject_reason?: string },
) {
  return http.post<
    unknown,
    { data: { code: number; msg: string; data: AdminBottle } }
  >(`/admin/bottles/${bottleId}/review`, payload)
}

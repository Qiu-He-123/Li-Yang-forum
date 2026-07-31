import { http, type LoadingAxiosRequestConfig } from './http'

export interface FriendUser {
  id: number
  nickname: string
  avatar_url: string | null
  bio: string | null
  school: string | null
  /** @deprecated 已弃用，改用 age */
  grade: string | null
  /** 年龄（从生日动态计算；可能为 null） */
  age: number | null
}

export interface FriendItem {
  user: FriendUser
  last_message: string | null
  last_time: string | null
  unread_count: number
}

export interface FriendRequestItem {
  id: number
  user: FriendUser
  message: string | null
  created_at: string | null
}

export interface SearchUserResult {
  user: FriendUser
  relation: 'friend' | 'pending_sent' | 'pending_received' | 'none'
  request_id?: number | null
}

/** 发送好友请求 */
export function sendFriendRequest(toId: number, message?: string) {
  return http.post('/friends/requests', { to_id: toId, message })
}

/** 接受好友请求 */
export function acceptFriendRequest(requestId: number) {
  return http.patch(`/friends/requests/${requestId}/accept`)
}

/** 拒绝好友请求 */
export function rejectFriendRequest(requestId: number) {
  return http.patch(`/friends/requests/${requestId}/reject`)
}

/** 好友请求列表 */
export function listFriendRequests(
  direction: 'incoming' | 'outgoing' = 'incoming',
  config: LoadingAxiosRequestConfig = {},
) {
  return http.get('/friends/requests', { ...config, params: { direction } })
}

/** 好友列表 */
export function listFriends(config: LoadingAxiosRequestConfig = {}) {
  return http.get('/friends', config)
}

/** 搜索用户 */
export function searchUsers(keyword: string, config: LoadingAxiosRequestConfig = {}) {
  return http.get('/friends/search', { ...config, params: { q: keyword } })
}

/** 发送消息 */
export function sendMessage(receiverId: number, content: string, msgType = 'text') {
  return http.post('/messages', { content, msg_type: msgType }, { params: { receiver_id: receiverId } })
}

/** 获取聊天记录（含关系状态：is_mutual, can_send, remaining_today） */
export function getMessages(
  friendId: number,
  page = 1,
  pageSize = 30,
  config: LoadingAxiosRequestConfig = {},
) {
  return http.get(`/messages/${friendId}`, {
    ...config,
    params: { page, page_size: pageSize },
  })
}

/** 获取会话列表（仅包含有消息记录的会话） */
export function listConversations(config: LoadingAxiosRequestConfig = {}) {
  return http.get('/messages', config)
}

// ============ 私信权限管理 ============

export type MessagePermission = 'everyone' | 'mutual_only' | 'stranger_once' | 'no_stranger'

/** 获取当前用户的私信权限设置 */
export function getMessagePermission(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { message_permission: MessagePermission } } }>('/messages/permission', config)
}

/** 更新当前用户的私信权限设置 */
export function updateMessagePermission(permission: MessagePermission) {
  return http.patch<unknown, { data: { code: number; msg: string; data: { message_permission: MessagePermission } } }>(
    '/messages/permission',
    { message_permission: permission },
  )
}

/** 预检：能否给指定用户发消息 */
export function checkCanSend(userId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: { can_send: boolean; reason: string; is_mutual: boolean; remaining_today: number } } }>(
    `/messages/check/${userId}`,
  )
}

import { http } from './http'
import type { ApiResponse } from '../types/api'

export interface OrderTask {
  id: number
  user_id: number
  poster_name: string
  poster_avatar: string | null
  title: string
  content: string
  category: string
  reward: number
  escrow: number
  status: string // open/in_progress/done/completed/cancelled
  assignee_id: number | null
  assignee_name: string
  boost: number
  deliver_note: string | null
  is_mine: boolean
  is_assigned_to_me: boolean
  platform_cut?: number
  created_at: string
  completed_at: string | null
}

export interface OrderListResp {
  categories: string[]
  total: number
  items: OrderTask[]
}

export interface WalletInfo {
  balance: number
  frozen: number
  rate: number
  commission_rate: number
  withdraw_min_cents: number
  boost_price: number
  transactions: {
    id: number
    amount: number
    balance_after: number
    type: string
    status: string
    description: string | null
    created_at: string
  }[]
}

export const ORDER_STATUS_META: Record<string, { text: string; cls: string }> = {
  open: { text: '待接单', cls: 'st-open' },
  in_progress: { text: '进行中', cls: 'st-going' },
  done: { text: '已交付', cls: 'st-done' },
  completed: { text: '已完成', cls: 'st-completed' },
  cancelled: { text: '已取消', cls: 'st-cancel' },
}

export function listOrders(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<OrderListResp> }>('/orders', { params })
}

// ==================== 订单 AI 对话助手 ====================
export interface AiCard {
  type?: string
  tasks?: OrderTask[]
  empty?: boolean
  balance?: number
  frozen?: number
  action?: string
  data?: Record<string, unknown>
  task?: OrderTask
}

export interface AiChatMsg {
  id?: number
  role: string // user / assistant / tool
  content: string
  meta?: AiCard | null
  created_at?: string
}

export interface OrderAiState {
  enabled: boolean
  daily_token: number
  daily_token_limit: number
  remaining_token: number | null
}

export interface ChatResp {
  new_messages: AiChatMsg[]
  state: OrderAiState
  spent_tokens: number
}

export function orderAiChat(text: string) {
  return http.post<unknown, { data: ApiResponse<ChatResp> }>('/orders/ai/chat', { text })
}

export function orderAiHistory() {
  return http.get<unknown, { data: ApiResponse<{ history: AiChatMsg[]; state: OrderAiState }> }>('/orders/ai/history')
}

export function orderAiState() {
  return http.get<unknown, { data: ApiResponse<OrderAiState> }>('/orders/ai/state')
}

export function myOrders(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<OrderListResp> }>('/orders/my', { params })
}

export function getOrder(id: number) {
  return http.get<unknown, { data: ApiResponse<OrderTask> }>(`/orders/${id}`)
}

export function createOrder(payload: { title: string; content: string; category: string; reward: number }) {
  return http.post<unknown, { data: ApiResponse<OrderTask> }>('/orders', payload)
}

export function acceptOrder(id: number) {
  return http.post<unknown, { data: ApiResponse<OrderTask> }>(`/orders/${id}/accept`)
}

export function deliverOrder(id: number, note: string) {
  return http.post<unknown, { data: ApiResponse<OrderTask> }>(`/orders/${id}/deliver`, { note })
}

export function confirmOrder(id: number) {
  return http.post<unknown, { data: ApiResponse<OrderTask> }>(`/orders/${id}/confirm`)
}

export function cancelOrder(id: number) {
  return http.post<unknown, { data: ApiResponse<OrderTask> }>(`/orders/${id}/cancel`)
}

export function boostOrder(id: number) {
  return http.post<unknown, { data: ApiResponse<OrderTask> }>(`/orders/${id}/boost`)
}

export function getWallet() {
  return http.get<unknown, { data: ApiResponse<WalletInfo> }>('/orders/wallet/me')
}

export function recharge(fuel_amount: number) {
  return http.post<unknown, { data: ApiResponse<{ cents: number; bin: number; rate: number; status: string }> }>(
    '/orders/wallet/recharge',
    { fuel_amount },
  )
}

export function withdraw(fuel_amount: number, payee: string) {
  return http.post<unknown, { data: ApiResponse<{ id: number; amount_bin: number; amount_cents: number; status: string }> }>(
    '/orders/wallet/withdraw',
    { fuel_amount, payee },
  )
}

// ==================== 后台 ====================
export function adminListOrders(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<OrderListResp> }>('/admin/orders', { params })
}

export function adminCancelOrder(id: number) {
  return http.post<unknown, { data: ApiResponse<OrderTask> }>(`/admin/orders/${id}/cancel`)
}

export function adminSettings() {
  return http.get<unknown, { data: ApiResponse<Record<string, number>> }>('/admin/orders/settings')
}

export function adminUpdateSettings(payload: Record<string, number>) {
  return http.post<unknown, { data: ApiResponse<Record<string, number>> }>('/admin/orders/settings', payload)
}

export function adminListRecharges(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<{ items: { id: number; user_name: string; amount: number; status: string; created_at: string }[]; total: number }> }>(
    '/admin/orders/recharges',
    { params },
  )
}
export function adminApproveRecharge(id: number) {
  return http.post<unknown, { data: ApiResponse<Record<string, unknown>> }>(`/admin/orders/recharge/${id}/approve`)
}
export function adminRejectRecharge(id: number) {
  return http.post<unknown, { data: ApiResponse<Record<string, unknown>> }>(`/admin/orders/recharge/${id}/reject`)
}

export function adminListWithdraws(params?: Record<string, unknown>) {
  return http.get<unknown, {
    data: ApiResponse<{ items: { id: number; user_name: string; amount_bin: number; amount_cents: number; payee: string; status: string; created_at: string }[]; total: number }>
  }>('/admin/orders/withdraws', { params })
}
export function adminApproveWithdraw(id: number) {
  return http.post<unknown, { data: ApiResponse<Record<string, unknown>> }>(`/admin/orders/withdraw/${id}/approve`)
}
export function adminRejectWithdraw(id: number, reason: string) {
  return http.post<unknown, { data: ApiResponse<Record<string, unknown>> }>(`/admin/orders/withdraw/${id}/reject`, { reason })
}

// ==================== 后台：订单 AI 管理 ====================
export interface OrderAiSessionRow {
  user_id: number
  user_name: string
  daily_token: number
  daily_token_limit: number
  message_count: number
  daily_date: string
  created_at: string
  updated_at: string
}
export interface OrderAiSettings {
  enabled: boolean
  daily_token_limit: number
  context_messages: number
}
export function adminOrderAiSessions(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<{ items: OrderAiSessionRow[]; total: number }> }>('/admin/orders/ai/sessions', { params })
}
export function adminOrderAiMessages(userId: number, limit = 100) {
  return http.get<unknown, { data: ApiResponse<{ role: string; messages: AiChatMsg[] }> }>(
    `/admin/orders/ai/sessions/${userId}/messages`,
    { params: { limit } },
  )
}
export function adminOrderAiSettings() {
  return http.get<unknown, { data: ApiResponse<OrderAiSettings> }>('/admin/orders/ai/settings')
}
export function adminUpdateOrderAiSettings(payload: Partial<OrderAiSettings>) {
  return http.post<unknown, { data: ApiResponse<OrderAiSettings> }>('/admin/orders/ai/settings', payload)
}

// ==================== 抽奖（提现改抽奖）====================
export interface LotteryPrize {
  id: number
  name: string
  image_url: string | null
  weight: number
  min_qty: number
  max_qty: number
  hot_qty: number
  ad_qty: number
  max_ad_times: number
  enabled: boolean
}
export interface LotteryMyInfo {
  prize: LotteryPrize
  base_qty: number
  ticket_qty: number
  ad_times_left: number
  draw_id: number
}
// 用户端
export function lotteryPool() {
  return http.get<unknown, { data: ApiResponse<{ prizes: LotteryPrize[]; ticket_rate: number; enabled: boolean; admin_wechat: string; draw_cost: number; my: { ticket_qty: number; total_draws: number } }> }>(
    '/orders/lottery/pool',
  )
}
export interface LotteryInventoryItem {
  id: number
  prize_name: string
  image_url: string | null
  qty: number
  status: string
  created_at: string
}
export function lotteryMy() {
  return http.get<unknown, { data: ApiResponse<{ ticket_qty: number; total_draws: number; inventory: LotteryInventoryItem[] }> }>('/orders/lottery/my')
}
export function lotteryExchange(count: number) {
  return http.post<unknown, { data: ApiResponse<{ ticket_qty: number; spent: number; count: number }> }>('/orders/lottery/exchange', { count })
}
export function lotteryDraw() {
  return http.post<unknown, { data: ApiResponse<LotteryMyInfo> }>('/orders/lottery/draw')
}
export function lotteryAdGrant(drawId: number) {
  return http.post<unknown, { data: ApiResponse<{ draw_id: number; ad_times_left: number; ad_qty_granted: number; total_qty: number }> }>('/orders/lottery/ad-grant', { draw_id: drawId })
}
export function lotteryClaim(drawId: number) {
  return http.post<unknown, { data: ApiResponse<{ claimed: boolean; admin_wechat: string; qty: number }> }>('/orders/lottery/claim', { draw_id: drawId })
}

// 后台
export interface LotterySettings {
  ticket_rate: number
  enabled: boolean
  admin_wechat: string
}
export interface LotteryDrawRow {
  id: number
  user_id: number
  user_name: string
  prize_name: string
  base_qty: number
  ad_times_used: number
  ad_qty_granted: number
  total_qty: number
  status: string
  created_at: string
}
export interface LotteryInventoryRow {
  id: number
  user_id: number
  user_name: string
  prize_name: string
  image_url: string | null
  qty: number
  status: string
  claimed_at: string
  created_at: string
}
export function adminLotterySettings() {
  return http.get<unknown, { data: ApiResponse<LotterySettings> }>('/admin/orders/lottery/settings')
}
export function adminUpdateLotterySettings(payload: Partial<LotterySettings>) {
  return http.post<unknown, { data: ApiResponse<LotterySettings> }>('/admin/orders/lottery/settings', payload)
}
export function adminLotteryPrizes() {
  return http.get<unknown, { data: ApiResponse<{ items: LotteryPrize[] }> }>('/admin/orders/lottery/prizes')
}
export function adminCreateLotteryPrize(payload: Partial<LotteryPrize>) {
  return http.post<unknown, { data: ApiResponse<LotteryPrize> }>('/admin/orders/lottery/prizes', payload)
}
export function adminUpdateLotteryPrize(id: number, payload: Partial<LotteryPrize>) {
  return http.put<unknown, { data: ApiResponse<LotteryPrize> }>(`/admin/orders/lottery/prizes/${id}`, payload)
}
export function adminDeleteLotteryPrize(id: number) {
  return http.delete<unknown, { data: ApiResponse<Record<string, unknown>> }>(`/admin/orders/lottery/prizes/${id}`)
}
export function adminLotteryDraws(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<{ items: LotteryDrawRow[]; total: number }> }>('/admin/orders/lottery/draws', { params })
}
export function adminLotteryInventory(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<{ items: LotteryInventoryRow[]; total: number }> }>('/admin/orders/lottery/inventory', { params })
}
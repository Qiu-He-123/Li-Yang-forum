import { http, type LoadingAxiosRequestConfig } from './http'

export interface GuessOption {
  id: number
  label: string
  sort_order: number
  /** 该选项累计押注积分 */
  total_points: number
  /** 该选项累计押注人数 */
  total_users: number
}

export interface GuessItem {
  id: number
  title: string
  description: string | null
  deadline: string | null
  is_active: boolean
  date_key: string
  winning_option_id: number | null
  settled_at: string | null
  total_users: number
  total_points: number
  options: GuessOption[]
}

export interface MyBet {
  id: number
  option_id: number
  amount: number
  skipped: boolean
  result: 'pending' | 'win' | 'lose' | 'refund' | 'cancel'
  reward: number
}

export interface TodayGuessResp {
  guess: GuessItem | null
  my_bet: MyBet | null
  now: string
}

export function getTodayGuess(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: TodayGuessResp } }>(
    '/guesses/today',
    config,
  )
}

export function placeGuessBet(guessId: number, optionId: number, amount: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { bet: MyBet; guess: GuessItem } } }>(
    `/guesses/${guessId}/bet`,
    { option_id: optionId, amount },
  )
}

export function skipGuessBet(guessId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { bet: MyBet } } }>(
    `/guesses/${guessId}/skip`,
    {},
  )
}

// ===== admin 侧 =====

export interface AdminGuessCreatePayload {
  title: string
  description?: string
  deadline: string
  date_key?: string
  options: string[]
}

export function adminGuessList(params: { page?: number; page_size?: number; date_key?: string }) {
  return http.get<unknown, { data: { code: number; msg: string; data: { total: number; items: Array<GuessItem & { bets?: any[] }> } } }>(
    '/admin/guesses',
    { params },
  )
}

export function adminGuessDetail(guessId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: GuessItem & { bets?: any[] } } }>(`/admin/guesses/${guessId}`)
}

export function adminGuessCreate(payload: AdminGuessCreatePayload) {
  return http.post<unknown, { data: { code: number; msg: string; data: GuessItem } }>('/admin/guesses', payload)
}

export function adminGuessToggle(guessId: number, is_active: boolean) {
  return http.patch<unknown, { data: { code: number; msg: string; data: GuessItem } }>(
    `/admin/guesses/${guessId}/toggle`,
    { is_active },
  )
}

export function adminGuessDelete(guessId: number) {
  return http.delete<unknown, { data: { code: number; msg: string } }>(`/admin/guesses/${guessId}`)
}

export function adminGuessSettle(guessId: number, winning_option_id: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: GuessItem } }>(
    `/admin/guesses/${guessId}/settle`,
    { winning_option_id },
  )
}

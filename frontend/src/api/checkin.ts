import { http } from './http'

export interface CheckInResult {
  id: number
  check_in_date: string
  consecutive_days: number
  reward_points: number
  already_checked_in: boolean
  message: string
}

export interface CheckInStatus {
  checked_in_today: boolean
  today_consecutive_days: number
  today_reward_points: number
  month_days: Array<{
    date: string
    consecutive_days: number
    reward_points: number
  }>
  month_checked_days: number[]
  total_month_count: number
}

export interface MonthlyHistory {
  year: number
  month: number
  days: Array<{
    date: string
    day: number
    consecutive_days: number
    reward_points: number
  }>
  total_count: number
}

/** 今日签到 */
export function checkInToday() {
  return http.post<unknown, { data: { code: number; msg: string; data: CheckInResult } }>('/checkin/today')
}

/** 获取签到状态 */
export function getCheckInStatus() {
  return http.get<unknown, { data: { code: number; msg: string; data: CheckInStatus } }>('/checkin/status')
}

/** 获取指定月份签到记录 */
export function getMonthlyHistory(year: number, month: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: MonthlyHistory } }>('/checkin/history', {
    params: { year, month },
  })
}

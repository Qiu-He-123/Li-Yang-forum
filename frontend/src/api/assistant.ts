import { http } from './http'
import type { ApiResponse } from '../types/api'

export interface AssistantLogRow {
  id: number
  user_id: number
  user_name: string
  input: string
  intent: string
  reply: string
  action: string
  hit: boolean
  created_at: string
}
export interface AssistantStats {
  total: number
  hits: number
  hit_rate: number
  per_day: { date: string; count: number }[]
}

export function assistantLog(payload: { input: string; intent: string; reply: string; action: string; hit: boolean }) {
  return http.post<unknown, { data: ApiResponse<unknown> }>('/assistant/log', payload)
}

export function adminAssistantLogs(params?: Record<string, unknown>) {
  return http.get<unknown, { data: ApiResponse<{ items: AssistantLogRow[]; total: number }> }>('/admin/assistant/logs', { params })
}

export function adminAssistantStats() {
  return http.get<unknown, { data: ApiResponse<AssistantStats> }>('/admin/assistant/stats')
}
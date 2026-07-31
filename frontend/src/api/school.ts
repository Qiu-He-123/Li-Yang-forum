import { http, type LoadingAxiosRequestConfig } from './http'
import type { School } from '../types/api'

export function listSchools(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: School[] } }>('/schools', config)
}

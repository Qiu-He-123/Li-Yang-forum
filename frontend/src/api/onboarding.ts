import { http } from './http'

export function getOnboardingStatus() {
  return http.get<unknown, { data: { code: number; msg: string; data: { onboarding_done: boolean } } }>(
    '/onboarding/status',
  )
}

export function completeOnboarding() {
  return http.post<unknown, { data: { code: number; msg: string; data: { onboarding_done: boolean } } }>(
    '/onboarding/complete',
  )
}

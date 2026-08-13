import { http } from './http'

export interface CoinTransactionItem {
  id: number
  amount: number
  balance_after: number
  type: string
  ref_id: string | null
  description: string | null
  created_at: string
}

export interface BadgeShopItem {
  id: number
  name: string
  code: string
  icon: string
  description: string | null
  price: number
  owned: boolean
}

export function getCoinsMe() {
  return http.get<unknown, { data: { code: number; msg: string; data: { coins: number; onboarding_done: boolean } } }>(
    '/coins/me',
  )
}

export function getCoinTransactions(page = 1, pageSize = 50) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: CoinTransactionItem[]; total: number } } }>(
    '/coins/transactions',
    { params: { page, page_size: pageSize } },
  )
}

export function getBadgeShop() {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: BadgeShopItem[]; coins: number } } }>(
    '/coins/badges',
  )
}

export function purchaseBadge(badgeId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { badge: BadgeShopItem; coins: number } } }>(
    `/coins/badges/${badgeId}/purchase`,
  )
}

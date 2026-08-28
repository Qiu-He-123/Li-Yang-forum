import type { Post } from '../types/api'
import { useCircleStore } from '../stores/circle'

/**
 * 圈子图标与色调映射（严格对齐设计稿：发现页.html）
 * 首页瀑布流与沉浸刷流共用同一份映射，避免两处维护。
 * - 图片卡（card--image）：白色背景，无染色
 * - 文本卡（card--text）：按圈子染色，仅 4 种染色：study/lost/game/confess
 */
export const circleMeta: Record<
  string,
  { icon: string; pillBg: string; pillColor: string; cardBg: string; iconColor: string }
> = {
  confess: { icon: 'heart', pillBg: '#f7eaff', pillColor: '#af52de', cardBg: '#faf5ff', iconColor: '#af52de' },
  lost: { icon: 'circle-question', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#ffecea', iconColor: '#ff3b30' },
  market: { icon: 'tag', pillBg: '#fff3e6', pillColor: '#d26510', cardBg: '#ffffff', iconColor: '#d26510' },
  study: { icon: 'file', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#e8f2ff', iconColor: '#007aff' },
  food: { icon: 'map-pin', pillBg: '#fff3e6', pillColor: '#d26510', cardBg: '#ffffff', iconColor: '#d26510' },
  game: { icon: 'star', pillBg: '#eeeaff', pillColor: '#5856d6', cardBg: '#f3f0ff', iconColor: '#5856d6' },
  photo: { icon: 'camera', pillBg: '#e9f9ee', pillColor: '#34c759', cardBg: '#ffffff', iconColor: '#34c759' },
  club: { icon: 'star', pillBg: '#f7eaff', pillColor: '#af52de', cardBg: '#ffffff', iconColor: '#af52de' },
  sport: { icon: 'flame', pillBg: '#e8f2ff', pillColor: '#007aff', cardBg: '#ffffff', iconColor: '#007aff' },
  match: { icon: 'shuffle', pillBg: '#fff3e6', pillColor: '#d26510', cardBg: '#ffffff', iconColor: '#ff9500' },
  treehole: { icon: 'lock', pillBg: '#f2f2f7', pillColor: '#48484a', cardBg: '#ffffff', iconColor: '#8e8e93' },
  qa: { icon: 'circle-question', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#e8f2ff', iconColor: '#007aff' },
  flea: { icon: 'tag', pillBg: '#e9f9ee', pillColor: '#34c759', cardBg: '#ffffff', iconColor: '#34c759' },
  default: { icon: 'sparkles', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#ffffff', iconColor: '#007aff' },
}

export function getCircleMeta(slug: string) {
  return circleMeta[slug] || circleMeta.default
}

/** 后端 post.category 存的是圈子 name（如「校园美食」），需映射回 slug（如「food」） */
export function resolveCircleSlug(post: Post): string {
  const circleStore = useCircleStore()
  const bySlug = circleStore.circles.find((c) => c.slug === post.category)
  if (bySlug) return bySlug.slug
  const byName = circleStore.circles.find((c) => c.name === post.category)
  if (byName) return byName.slug
  return post.category || 'default'
}

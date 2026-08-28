import { http, type LoadingAxiosRequestConfig } from './http'

/** 帧动画单个动作配置（DyberPet 像素宠物） */
export interface PetAnimAction {
  key: string
  label: string
  frames: string[]
  /** 帧间隔（毫秒） */
  interval: number
}

/** 帧动画配置 */
export interface PetAnim {
  slug: string
  actions: PetAnimAction[]
}

/** 宠物商城商品 */
export interface PetProduct {
  id: number
  name: string
  category_id: number
  category: string
  price: number
  original_price: number | null
  stock: number
  image_url: string | null
  image: string | null
  model_3d_url: string | null
  anim: PetAnim | null
  description: string | null
  sales: number
  status: number
  created_at: string | null
  owned?: boolean
  /** 1=活体宠物 2=道具(食物/玩具/日用/医疗) 3=进化道具 */
  kind: number
  /** 道具好感加成（仅 kind=2） */
  affinity_gain: number
  /** 宠物 AI 人设（游戏触发话术同块编辑） */
  ai_persona?: string | null
  /** 宠物是否启用 AI 对话 */
  ai_enabled?: boolean
  /** 宠物 AI 主动找人开关 */
  ai_wake_enabled?: boolean
  /** 宠物是否能飞行（kind=1 活体宠物自动触发"上抛悬空再落回"） */
  can_fly?: boolean
  /** 道具按类型定制的数值字段 JSON */
  attrs?: Record<string, number> | null
  /** 陪我玩「动作→宠物说话」JSON 常量 */
  game_speech?: string | null
  bag_qty?: number
}

export interface PetCategory {
  id: number
  name: string
  icon: string | null
  sort_order: number
}

export interface PetProductListResp {
  items: PetProduct[]
  total: number
  page: number
  page_size: number
}

/** 冷却时间（秒） */
export interface PetCooldowns {
  pet: number
  feed: number
  play: number
}

/** 每日好感数据 */
export interface PetDailyAffinity {
  date: string | null
  gained: number
  cap: number
  remaining: number
}

/** 下一级信息 */
export interface PetNextLevel {
  level: number
  name: string
  affinity_needed: number
  desc: string
  unlocks: string[]
}

/** 假随机掉落物 */
export interface PetDrop {
  item_id: number
  name: string
  image_url: string | null
  emoji: string
  /** 是否保底（pity）掉落 */
  pity: boolean
  bag_qty: number
}

/** 点击宠物返回 */
export interface TapPetResp {
  satiety: number
  is_hungry: boolean
  drop: PetDrop | null
  interact_count: number
}

/** 我的宠物（含等级/进化/冷却等完整状态） */
export interface MyPetItem extends PetProduct {
  adopted_at: string | null
  affinity: number
  level: number
  level_name: string
  level_desc: string
  evolved: boolean
  evolved_at: string | null
  nickname: string | null
  /** 饱食度 0-100 */
  satiety: number
  /** 是否饿虚（饱食度 < 30） */
  is_hungry: boolean
  /** 小情绪（由饱食度 + 好感生成） */
  mood?: string
  cooldowns: PetCooldowns
  daily_affinity: PetDailyAffinity
  next_level: PetNextLevel | null
}

export interface MyPetsResp {
  items: MyPetItem[]
  total: number
  /** 当前已养宠物数 */
  owned: number
  /** 宠物上限（基础上限 MAX_OWNED_PETS=2 + 已购领养位） */
  limit: number
  /** 已购额外领养位数量 */
  extra_slots: number
  coins: number
}

/** 背包道具 */
export interface BagItem extends PetProduct {
  qty: number
}

export interface MyBagResp {
  items: BagItem[]
  total: number
  total_qty: number
}

/** 升级方案步骤 */
export interface UpgradePlanStep {
  level: number
  name: string
  affinity_required: number
  desc: string
  unlocks: string[]
  is_current: boolean
  is_reached: boolean
  evolution_item_required?: boolean
  has_evolution_item?: boolean
}

export interface UpgradePlanResp {
  pet: MyPetItem
  plan: UpgradePlanStep[]
  evolved: boolean
}

/** 宠物状态/需求 */
export interface PetStatusResp {
  pet: MyPetItem
  need: 'none' | 'feed' | 'play' | 'pet'
  cooldowns: PetCooldowns
}

/** 互动返回 */
export interface InteractResp {
  affinity: number
  gained: number
  raw_gain: number
  decay: number
  level: number
  leveled_up: boolean
  daily_gained: number
  daily_cap: number
  daily_remaining: number
  can_evolve: boolean
  satiety?: number
  is_hungry?: boolean
}

/** 商品分类列表 */
export function listPetCategories(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PetCategory[] } }>(
    '/pet-shop/categories',
    config,
  )
}

/** 商品列表（仅上架，分类/关键词/类型/分页） */
export function listPetProducts(
  params: { category?: string; keyword?: string; kind?: number; page?: number; page_size?: number } = {},
  config: LoadingAxiosRequestConfig = {},
) {
  return http.get<unknown, { data: { code: number; msg: string; data: PetProductListResp } }>(
    '/pet-shop/products',
    { ...config, params },
  )
}

/** 商品详情 */
export function fetchPetProduct(id: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PetProduct } }>(
    `/pet-shop/products/${id}`,
    config,
  )
}

/** 金币领养宠物 */
export function adoptPet(productId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: { pet: PetProduct; coins: number } } }>(
    `/pet-shop/products/${productId}/adopt`,
    {},
    config,
  )
}

/** 我的宠物列表 */
export function listMyPets(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: MyPetsResp } }>(
    '/pet-shop/my-pets',
    config,
  )
}

/** 某人已领养的宠物（公开轻量信息，用于帖子卡片等展示他人的宠物） */
export interface UserPetLight {
  id: number
  name: string
  nickname: string | null
  anim: PetAnim | null
  image_url: string | null
  level: number
  level_name: string
  evolved: boolean
  /** 宠物是否能飞行 */
  can_fly?: boolean
}

export function listUserPets(userId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: UserPetLight[]; total: number } } }>(
    `/pet-shop/user/${userId}/pets`,
    config,
  )
}

/** 购买道具进背包 */
export function purchaseItem(productId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: { item: PetProduct & { bag_qty: number }; coins: number } } }>(
    `/pet-shop/products/${productId}/buy`,
    {},
    config,
  )
}

/** 购买"宠物领养位"：永久 +1 宠物名额，突破基础上限(MAX_OWNED_PETS=2) */
export function adoptSlot(productId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, {
    data: { code: number; msg: string; data: { product: PetProduct; pet_extra_slots: number; max_owned: number; coins: number } }
  }>(
    `/pet-shop/products/${productId}/adopt-slot`,
    {},
    config,
  )
}

/** 喂食/赠送：消耗背包食物 1 份，好感度提升。可选指定 foodId 喂某种食物。 */
export function feedPet(
  petProductId: number,
  foodId?: number,
  config: LoadingAxiosRequestConfig = {},
) {
  return http.post<unknown, { data: { code: number; msg: string; data: InteractResp & { food: PetProduct; bag: BagItem[] } } }>(
    `/pet-shop/pets/${petProductId}/feed`,
    { food_id: foodId ?? null },
    config,
  )
}

/** 用背包玩具陪玩：消耗玩具 1 份，好感度提升（与玩耍共用冷却） */
export function playPetToy(
  petProductId: number,
  toyId: number,
  config: LoadingAxiosRequestConfig = {},
) {
  return http.post<unknown, { data: { code: number; msg: string; data: InteractResp & { toy: PetProduct; bag: BagItem[] } } }>(
    `/pet-shop/pets/${petProductId}/play`,
    { toy_id: toyId },
    config,
  )
}

/** 互动（摸摸头/玩耍） */
export function interactPet(
  petProductId: number,
  action: 'pet' | 'play' = 'pet',
  config: LoadingAxiosRequestConfig = {},
) {
  return http.post<unknown, { data: { code: number; msg: string; data: InteractResp } }>(
    `/pet-shop/pets/${petProductId}/interact?action=${action}`,
    {},
    config,
  )
}

/** 遗弃宠物 */
export function abandonPet(petProductId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: { abandoned: number; name: string; pets_left: number } } }>(
    `/pet-shop/pets/${petProductId}/abandon`,
    {},
    config,
  )
}

/** 道具背包 */
export function listMyBag(config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: MyBagResp } }>(
    '/pet-shop/my-bag',
    config,
  )
}

/** 使用背包道具（食物喂食/玩具陪玩/日用医疗使用/进化水晶进化） */
export interface UseItemResp {
  message: string
  bag: BagItem[]
  pet?: MyPetItem | null
  result?: { gained: number } | null
  can_evolve: boolean
  satiety?: number | null
  evolved?: boolean
}

export function useBagItem(petProductId: number, itemId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: UseItemResp } }>(
    `/pet-shop/pets/${petProductId}/use-item`,
    { item_id: itemId },
    config,
  )
}

/** 升级方案 */
export function getUpgradePlan(petProductId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: UpgradePlanResp } }>(
    `/pet-shop/pets/${petProductId}/plan`,
    config,
  )
}

/** 超级进化 */
export function evolvePet(petProductId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: { pet: MyPetItem; evolved: boolean; msg: string } } }>(
    `/pet-shop/pets/${petProductId}/evolve`,
    {},
    config,
  )
}

/** 设置昵称 */
export function setPetNickname(petProductId: number, nickname: string, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: { nickname: string } } }>(
    `/pet-shop/pets/${petProductId}/nickname`,
    { nickname },
    config,
  )
}

/** 宠物状态/需求（用于桌宠气泡） */
export function getPetStatus(petProductId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: PetStatusResp } }>(
    `/pet-shop/pets/${petProductId}/status`,
    config,
  )
}

/** 点击宠物：爱心反馈 + 饱食度结算 + 假随机掉落（pity 保底） */
export function tapPet(petProductId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.post<unknown, { data: { code: number; msg: string; data: TapPetResp } }>(
    `/pet-shop/pets/${petProductId}/tap`,
    {},
    config,
  )
}

/** 好感度等级（旧版5心，保留兼容） */
export const AFFINITY_LEVELS = [
  { min: 0, label: '陌生', hearts: 1 },
  { min: 20, label: '熟悉', hearts: 2 },
  { min: 40, label: '伙伴', hearts: 3 },
  { min: 60, label: '挚友', hearts: 4 },
  { min: 80, label: '灵魂伴侣', hearts: 5 },
]

export function affinityLevel(affinity: number) {
  let lv = AFFINITY_LEVELS[0]
  for (const l of AFFINITY_LEVELS) if (affinity >= l.min) lv = l
  return lv
}

/** 等级配置名称 */
export const PET_LEVEL_NAMES: Record<number, string> = {
  1: '幼崽', 2: '幼年', 3: '少年', 4: '青年', 5: '成年', 6: '灵魂伴侣',
}

/** 冷却时间（秒） */
export const COOLDOWNS = { pet: 300, feed: 1800, play: 600 }

/** 格式化冷却时间 */
export function formatCooldown(seconds: number): string {
  if (seconds <= 0) return '可互动'
  if (seconds >= 60) return `${Math.ceil(seconds / 60)}分钟后`
  return `${seconds}秒后`
}

// ====================== 管理后台：上传 ZIP 制作宠物 ======================
// 后端路由 /admin/pet-shop/upload-zip（multipart file + 可选表单字段 name/price/category_id），
// 返回 { product }；压缩后 >20MB 会被拒绝。

export interface PetZipUploadOpts {
  name?: string
  price?: number
  category_id?: number
  description?: string
}

export interface PetZipUploadResp {
  product: PetProduct
}

/** 上传 ZIP 制作宠物（占位封装；后端未实现时由调用方 try/catch 静默兜底） */
export function adminUploadPetZip(file: File, opts: PetZipUploadOpts = {}, config: LoadingAxiosRequestConfig = {}) {
  const formData = new FormData()
  formData.append('file', file)
  if (opts.name != null && opts.name !== '') formData.append('name', opts.name)
  if (opts.price != null) formData.append('price', String(opts.price))
  if (opts.category_id != null) formData.append('category_id', String(opts.category_id))
  if (opts.description != null && opts.description !== '') formData.append('description', opts.description)
  return http.post<unknown, { data: { code: number; msg: string; data: PetZipUploadResp } }>(
    '/admin/pet-shop/upload-zip',
    formData,
    { timeout: 300_000, showGlobalLoading: false, ...config },
  )
}

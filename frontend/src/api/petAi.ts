import { http } from './http'

/**
 * 宠物 AI（DeepSeek 引擎）前端 API。
 *
 * 覆盖：用户聊天 / 历史记录 / AI 状态 / 动作上报 / 事件触发，
 * 以及后台配置读写 / 模型列表 / 连接测试 / 统计。
 */

// ==================== 消息类型 ====================

export interface PetAiChatMessage {
  id?: number
  /** user=用户 / assistant=AI 分段 / tool=工具调用卡片 */
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  /** 工具卡片附加信息：{ tool, args, result } */
  meta?: {
    tool?: string
    args?: Record<string, unknown>
    result?: string
    forced_sleep?: boolean
  } | null
  created_at?: string | null
}

export interface PetAiState {
  sleeping: boolean
  wake_at: string | null
  sleeping_until: string | null
  daily_token: number
  daily_token_limit: number
  remaining_token: number | null
  warn_mode: boolean
  daily_proactive_count: number
  daily_proactive_max: number
}

export interface PetAiChatResp {
  messages: PetAiChatMessage[]
  sleeping: boolean
  skipped: boolean
  state: PetAiState
}

// ==================== 用户侧 ====================

/** 宠物会话列表项（消息中心展示） */
export interface PetAiConversationItem {
  pet_id: number
  name: string
  nickname: string | null
  anim: unknown
  image_url: string | null
  ai_wake_enabled: boolean
  last_message: string
  last_time: string | null
  sleeping: boolean
  /** 未读 AI 消息数（红点） */
  unread_count: number
}

/** 宠物会话列表（所有开启 AI 的宠物，按最后活跃排序） */
export function petAiConversations() {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: PetAiConversationItem[]; total: number } } }>(
    '/pet-ai/conversations',
  )
}

/** 将该宠物所有未读 AI 消息标记为已读（清除红点） */
export function petAiMarkRead(petId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: Record<string, never> } }>(
    `/pet-ai/${petId}/read`,
    {},
  )
}

/** 用户发消息 → AI 分段回复 */
export function petAiChat(petId: number, text: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: PetAiChatResp } }>(
    `/pet-ai/${petId}/chat`,
    { text },
  )
}

/** 聊天记录（前端回显） */
export function petAiMessages(petId: number, limit = 50) {
  return http.get<unknown, { data: { code: number; msg: string; data: { messages: PetAiChatMessage[] } } }>(
    `/pet-ai/${petId}/messages`,
    { params: { limit } },
  )
}

/** AI 状态（是否睡觉/今日 token/主动次数） */
export function petAiState(petId: number) {
  return http.get<unknown, { data: { code: number; msg: string; data: PetAiState } }>(
    `/pet-ai/${petId}/state`,
  )
}

/** 上报用户动作（注入 AI 上下文） */
export function petAiRecordActivity(action: string, detail = '') {
  return http.post<unknown, { data: { code: number; msg: string; data: Record<string, never> } }>(
    '/pet-ai/activity',
    { action, detail },
  )
}

/** 事件触发：浏览超阈值时让 AI 说一句话 */
export function petAiTriggerEvent(petId: number, eventType: string, detail = '', seconds = 0) {
  return http.post<unknown, { data: { code: number; msg: string; data: PetAiChatResp } }>(
    '/pet-ai/event',
    { pet_id: petId, event_type: eventType, detail, seconds },
  )
}

/** 事件触发阈值（用户侧）：前端据此决定何时上报浏览时长 */
export interface PetAiEventConfig {
  enabled: boolean
  /** [最小秒, 最大秒] */
  post_detail: [number, number]
  post_list: [number, number]
  pet_shop: [number, number]
}

export function petAiEventConfig() {
  return http.get<unknown, { data: { code: number; msg: string; data: PetAiEventConfig } }>(
    '/pet-ai/event-config',
  )
}

// ==================== 管理侧 ====================

export interface PetAiConfig {
  pet_ai_enabled: boolean
  pet_ai_api_key: string
  pet_ai_api_key_configured?: boolean
  pet_ai_base_url: string
  pet_ai_model: string
  pet_ai_proactive_interval_min: number
  pet_ai_daily_token_limit: number
  pet_ai_token_warn_threshold: number
  pet_ai_gift_coins_single: number
  pet_ai_gift_coins_daily: number
  pet_ai_affinity_add_single: number
  pet_ai_affinity_add_daily: number
  pet_ai_affinity_sub_single: number
  pet_ai_affinity_sub_daily: number
  pet_ai_sleep_min: number
  pet_ai_sleep_max: number
  pet_ai_event_post_detail_min: number
  pet_ai_event_post_detail_max: number
  pet_ai_event_post_list_min: number
  pet_ai_event_post_list_max: number
  pet_ai_event_pet_shop_min: number
  pet_ai_event_pet_shop_max: number
  pet_ai_event_cooldown_min: number
  pet_ai_daily_proactive_max: number
  pet_ai_user_actions_count: number
  /** 默认提示词（宠物未单独设置人设时使用；{pet_name}/{owner} 占位会被替换） */
  pet_ai_default_persona: string
}

export interface PetAiModelsResp {
  success: boolean
  models: string[]
  error?: string | null
}

export interface PetAiStats {
  ai_pet_count: number
  message_count: number
  today_token: number
  today_proactive_count: number
}

/** 读取宠物 AI 完整配置 */
export function adminPetAiConfig() {
  return http.get<unknown, { data: { code: number; msg: string; data: PetAiConfig } }>('/admin/pet-ai/config')
}

/** 更新宠物 AI 配置（只传需要修改的键） */
export function adminPetAiUpdateConfig(payload: Partial<PetAiConfig>) {
  return http.put<unknown, { data: { code: number; msg: string; data: PetAiConfig } }>('/admin/pet-ai/config', payload)
}

/** 从 DeepSeek 官方 API 拉取模型列表 */
export function adminPetAiModels() {
  return http.get<unknown, { data: { code: number; msg: string; data: PetAiModelsResp } }>('/admin/pet-ai/models')
}

/** 测试 DeepSeek 连接 */
export function adminPetAiTest() {
  return http.post<unknown, { data: { code: number; msg: string; data: { ok: boolean; msg: string; models?: string[] } } }>(
    '/admin/pet-ai/test',
  )
}

/** 宠物 AI 统计 */
export function adminPetAiStats() {
  return http.get<unknown, { data: { code: number; msg: string; data: PetAiStats } }>('/admin/pet-ai/stats')
}

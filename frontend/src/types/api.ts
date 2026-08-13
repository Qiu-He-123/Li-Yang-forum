// 前后端共享类型定义集中管理

export interface School {
  id: number
  name: string
  code: string
}

export type AiStatus = 'pending' | 'approved' | 'rejected' | 'manual_review'

/** @用户简要信息（Post.mention_users 元素） */
export interface MentionUser {
  id: number
  nickname: string
  avatar_url?: string | null
  badge?: Badge | null
}

/** 徽章（勋章） */
export interface Badge {
  id: number
  name: string
  code: string
  /** 图标：emoji（如 🏅）或图片 URL */
  icon: string
  description?: string | null
  is_active?: boolean
  is_system?: boolean
  sort_order?: number
  /** 当前用户是否已拥有 */
  is_owned?: boolean
  /** 当前用户是否正在佩戴 */
  is_wearing?: boolean
  created_at?: string | null
  /** 获取时间（公开主页勋章展示用） */
  acquired_at?: string | null
}

export interface Post {
  id: number
  content: string
  title?: string | null
  is_original?: boolean
  has_ai_content?: boolean
  is_public?: boolean
  image_urls: string[]
  /** 视频 URL 列表（微信朋友圈视频等，HTML5 video 渲染） */
  video_urls?: string[]
  /** 来源：normal / wechat_auto / wechat_manual / video_share（抖音/B站/快手分享） */
  source?: string
  is_anonymous: boolean
  category: string
  school: string
  school_id?: number
  author: string
  author_id?: number
  author_avatar_url?: string | null
  /** 作者佩戴的徽章（匿名帖不返回） */
  author_badge?: Badge | null
  like_count: number
  comment_count: number
  view_count?: number
  share_count?: number
  last_reply_at?: string | null
  /** 推荐探索：该条是否为「探索位」随机曝光（冷启动内容） */
  explored?: boolean
  tags: string[]
  ai_status?: AiStatus
  reject_reason?: string | null
  created_at?: string | null
  /** 阶段二：话题 id */
  topic_id?: number | null
  /** 阶段二：话题名 */
  topic_name?: string | null
  /** 阶段二：位置文本 */
  location?: string | null
  /** 阶段二：被 @ 的用户列表（后端可选返回） */
  mention_users?: MentionUser[]
  /** 阶段二：是否包含投票（用于详情页判断是否拉取投票详情） */
  has_poll?: boolean
  /** 审核可见性：false 表示因审核状态不可查看原文 */
  is_viewable?: boolean
  /** 审核不可查看原因：pending/rejected/manual_review */
  view_block_reason?: string | null
}

export interface CommentItem {
  id: number
  post_id?: number
  parent_id: number | null
  content: string
  author: string
  author_avatar_url?: string | null
  /** 评论者佩戴的徽章 */
  author_badge?: Badge | null
  user_id?: number
  like_count: number
  ai_status?: AiStatus
  reject_reason?: string | null
  /** 推荐探索：该条是否为「探索位」随机曝光 */
  explored?: boolean
  created_at?: string | null
}

export interface Profile {
  id: number
  uid: string
  nickname: string
  phone?: string
  school: string
  school_id?: number
  avatar_url: string | null
  background_url: string | null
  bio: string | null
  grade?: string | null
  /** 生日（ISO 字符串，设置后动态计算年龄，替代 grade） */
  birthday?: string | null
  /** 年龄（从 birthday 动态计算；后端返回） */
  age?: number | null
  gender?: 'male' | 'female' | 'unknown'
  post_count: number
  like_count: number
  following_count?: number
  followers_count?: number
  /** 当前佩戴的徽章 */
  wearing_badge?: Badge | null
  /** 已拥有的徽章数量 */
  badge_count?: number
  /** 该用户是否关注了当前登录用户（用于判断互关） */
  is_following_me?: boolean
}

export interface Announcement {
  id: number
  title: string
  content: string
  school_id?: number | null
  is_active?: boolean
  is_read?: boolean
  created_at?: string | null
}

export interface ApiResponse<T> {
  code: number
  msg: string
  data: T
}

export interface BanInfo {
  is_banned: boolean
  ban_until: string | null
  ban_reason: string | null
  violation_count: number
}

export interface AuthResult {
  user_id: number
  nickname?: string
  username?: string
  access_token?: string
  refresh_token?: string
  ban_info?: BanInfo | null
  verification_status?: string  // unverified / verified
}

export interface LikeResult {
  like_count: number
}

export interface ReportResult {
  id: number
  status: string
  ai_summary: string | null
}

export interface ImageUploadResult {
  id: number
  url: string
  thumb_url?: string
  /** 图片审核状态：pending(待人工审核) / approved / rejected */
  audit_status?: string
  /** 图片审核提示（如"图片内容需人工审核"） */
  audit_note?: string
}

/** 个人素材库图片（发帖时可复用历史上传） */
export interface MyImage {
  id: number
  url: string
  mime_type?: string
  created_at?: string | null
}

// ============ 新增类型（圈子/搜索/关注/通知分类） ============

/** 圈子（分类） */
export interface Circle {
  id: number
  name: string
  slug: string
  icon: string
  description: string | null
  color: string
  post_count: number
  member_count: number
  sort_order: number
  is_active: boolean
  is_joined?: boolean
  created_at?: string | null
  /** 阶段四：创建者 id（系统初始化圈子为 null） */
  creator_id?: number | null
  /** 阶段四：审核状态 pending/approved/rejected */
  status?: 'pending' | 'approved' | 'rejected'
  /** 阶段四：当前用户是否是吧主/管理员 */
  is_admin?: boolean
}

/** 圈子详情 */
export type CircleDetail = Circle

/** 阶段四：吧申请记录（我创建的吧） */
export interface CircleApply {
  id: number
  name: string
  slug: string
  icon: string | null
  description: string | null
  color: string
  post_count: number
  member_count: number
  sort_order: number
  creator_id: number | null
  status: 'pending' | 'approved' | 'rejected'
  reject_reason: string | null
  audit_at: string | null
  created_at: string | null
  /** 管理员视角下返回的申请人昵称/头像 */
  creator_nickname?: string | null
  creator_avatar_url?: string | null
}

/** 阶段四：吧主（圈子管理员） */
export interface CircleAdmin {
  id: number
  category_id: number
  user_id: number
  role: 'owner' | 'admin'
  nickname: string | null
  avatar_url: string | null
  created_at: string | null
}

/** 搜索历史 */
export interface SearchHistory {
  id: number
  keyword: string
  created_at: string
}

/** 热搜项 */
export interface HotSearch {
  keyword: string
  count: number
  /** 标签：沸/热/新，后端可返回 */
  tag?: 'hot' | 'boil' | 'new' | null
}

/** 关注用户 */
export interface FollowUser {
  id: number
  nickname: string
  avatar_url: string | null
  badge?: Badge | null
  bio: string | null
  school: string
  /** 当前用户是否已关注此人 */
  is_following?: boolean
}

/** 通知（带类型/引用） */
export interface NotificationItem {
  id: number
  type: 'interaction' | 'comment' | 'like' | 'follow' | 'system' | 'announcement' | 'mention' | 'topic' | 'vote_end'
  title: string
  content: string
  is_read: boolean
  sender_id?: number | null
  sender_nickname?: string | null
  sender_avatar_url?: string | null
  reference_type?: string | null
  reference_id?: number | null
  /** 帖子/评论类通知的原帖 id（评论通知的 reference_id 是 comment_id，需用 post_id 跳转） */
  post_id?: number | null
  read_at?: string | null
  created_at?: string | null
}

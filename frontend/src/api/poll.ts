import { http, type LoadingAxiosRequestConfig } from './http'

/** 投票选项 */
export interface PollOption {
  id: number
  content: string
  vote_count: number
  /** 当前用户是否投了该选项 */
  voted?: boolean
}

/** 投票详情 */
export interface Poll {
  id: number
  post_id: number
  title: string
  multi_vote: boolean
  deadline: string | null
  options: PollOption[]
  total_votes: number
  /** 当前用户是否已投票 */
  user_voted: boolean
  /** 是否已截止 */
  is_expired: boolean
}

/** 创建帖子里携带的投票载荷（提交给 /posts） */
export interface PollCreate {
  title: string
  multi_vote: boolean
  deadline: string | null
  options: string[]
}

/** 获取帖子关联的投票详情 */
export function getPoll(postId: number, config: LoadingAxiosRequestConfig = {}) {
  return http.get<unknown, { data: { code: number; msg: string; data: Poll } }>(`/polls/${postId}`, config)
}

/** 投票（可多选） */
export function votePoll(postId: number, optionIds: number[]) {
  return http.post<unknown, { data: { code: number; msg: string; data: { poll: Poll } } }>(
    `/polls/${postId}/vote`,
    { option_ids: optionIds },
  )
}

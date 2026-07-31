import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as authApi from '../api/auth'
import { useInteractionStore } from './interaction'
import { useUserStore } from './user'

export const useSessionStore = defineStore('session', () => {
  const userId = ref<number | null>(Number(localStorage.getItem('userId')) || null)
  const nickname = ref<string>(localStorage.getItem('nickname') || '')
  const isBanned = ref<boolean>(localStorage.getItem('banned') === '1')
  // 邀请码系统三状态：guest（未登录）/ unverified（已注册未填邀请码）/ verified（已填邀请码）
  const verificationStatus = ref<string>(localStorage.getItem('verificationStatus') || 'guest')
  let validationPromise: Promise<boolean> | null = null

  function setBanned(value: boolean, banUntil?: string, banReason?: string) {
    isBanned.value = value
    if (value) {
      localStorage.setItem('banned', '1')
      localStorage.setItem('ban_until', banUntil || '')
      localStorage.setItem('ban_reason', banReason || '')
    } else {
      localStorage.removeItem('banned')
      localStorage.removeItem('ban_until')
      localStorage.removeItem('ban_reason')
    }
  }

  function setVerificationStatus(status: string) {
    verificationStatus.value = status
    localStorage.setItem('verificationStatus', status)
  }

  /** 判断是否已认证（已填邀请码） */
  function isVerified() {
    return verificationStatus.value === 'verified'
  }

  /** 判断是否已登录（包括未填邀请码的注册用户） */
  function isLoggedIn() {
    return userId.value !== null
  }

  async function register(payload: authApi.RegisterPayload) {
    const { data } = await authApi.register(payload)
    userId.value = data.data.user_id
    localStorage.setItem('userId', String(userId.value))
    if (data.data.nickname) {
      nickname.value = data.data.nickname
      localStorage.setItem('nickname', data.data.nickname)
    }
    if (data.data.verification_status) {
      setVerificationStatus(data.data.verification_status)
    }
  }

  async function login(payload: authApi.LoginPayload) {
    const { data } = await authApi.login(payload)
    userId.value = data.data.user_id
    localStorage.setItem('userId', String(userId.value))
    if (data.data.nickname) {
      nickname.value = data.data.nickname
      localStorage.setItem('nickname', data.data.nickname)
    }
    if (data.data.verification_status) {
      setVerificationStatus(data.data.verification_status)
    }
    // 检测封号状态：后端允许封号用户登录，但前端需跳转到封号提示页
    if (data.data.ban_info?.is_banned) {
      const banInfo = data.data.ban_info
      setBanned(true, banInfo.ban_until || '', banInfo.ban_reason || '')
      // 通过抛出错误让登录页跳转
      const err = new Error('BANNED') as Error & { isBanned?: true }
      err.isBanned = true
      throw err
    }
  }

  /** 调用 /auth/me 校验当前 Cookie 是否仍然有效，用于刷新页面后恢复登录态。
   *
   * 稳定性修复：
   * - 不再在 catch 中清 session。http 拦截器已在 refresh_token 真正无效时
   *   调用 clearSessionAndRedirect()，这里重复清 session 会导致：
   *   1) 服务器临时故障（非 auth 错误）时误清 session → 用户被强制登出
   *   2) 多个并发请求同时触发 validateSession 时重复清 session
   * - 网络错误/服务器临时故障：保留 session，下次请求自动重试 refresh
   * - 仅当 http 拦截器已判定 refresh_token 无效并清了 session时，
   *   userId.value 才会变 null，此时直接返回 false 即可
   */
  async function validateSession(): Promise<boolean> {
    if (!userId.value) return false
    if (validationPromise) return validationPromise

    const expectedUserId = userId.value
    validationPromise = (async () => {
      try {
        const { data } = await authApi.fetchMe({
          showGlobalLoading: false,
          showGlobalError: false,
        })
        if (userId.value !== expectedUserId) return false
        userId.value = data.data.user_id
        if (data.data.nickname) {
          nickname.value = data.data.nickname
          localStorage.setItem('nickname', data.data.nickname)
        }
        if (data.data.verification_status) {
          setVerificationStatus(data.data.verification_status)
        }
        const banInfo = data.data.ban_info
        if (banInfo?.is_banned) {
          setBanned(true, banInfo.ban_until || '', banInfo.ban_reason || '')
          const { default: router } = await import('../router')
          if (router.currentRoute.value.name !== 'banned') {
            await router.replace({ name: 'banned' })
          }
          return false
        }
        if (isBanned.value) {
          setBanned(false)
          const { default: router } = await import('../router')
          if (router.currentRoute.value.name === 'banned') {
            await router.replace({ name: 'home' })
          }
        }
        return true
      } catch (error) {
        const authError = error as Error & { isSessionInvalid?: boolean }
        if (authError.isSessionInvalid || !userId.value) return false
        return true
      }
    })().finally(() => {
      validationPromise = null
    })

    return validationPromise
  }

  function clearSession() {
    userId.value = null
    nickname.value = ''
    localStorage.removeItem('userId')
    localStorage.removeItem('nickname')
    setBanned(false)
    setVerificationStatus('guest')
    // 同步清空点赞 / 收藏缓存
    useInteractionStore().clear()
    useUserStore().clearProfile()
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // 忽略登出请求错误，仍然清理本地状态
    }
    clearSession()
  }

  return {
    userId,
    nickname,
    isBanned,
    verificationStatus,
    setBanned,
    setVerificationStatus,
    isVerified,
    isLoggedIn,
    register,
    login,
    validateSession,
    clearSession,
    logout,
  }
})

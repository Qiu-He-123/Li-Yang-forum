import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as adminApi from '../api/admin'

export const useAdminStore = defineStore('admin', () => {
  const adminInfo = ref<adminApi.AdminInfo | null>(
    (() => {
      const raw = sessionStorage.getItem('adminInfo')
      return raw ? (JSON.parse(raw) as adminApi.AdminInfo) : null
    })(),
  )
  const checking = ref(false)

  function isLogged() {
    return !!adminInfo.value
  }

  async function login(payload: adminApi.AdminLoginPayload) {
    const { data } = await adminApi.adminLogin(payload)
    adminInfo.value = data.data
    sessionStorage.setItem('adminInfo', JSON.stringify(data.data))
  }

  async function logout() {
    try {
      await adminApi.adminLogout()
    } catch {
      // 忽略网络错误，仍然清本地态
    }
    clear()
  }

  function clear() {
    adminInfo.value = null
    sessionStorage.removeItem('adminInfo')
  }

  /** 路由守卫调用：通过 ping /admin/posts 校验 admin_token Cookie 是否仍有效。 */
  async function validate(): Promise<boolean> {
    if (!adminInfo.value) return false
    checking.value = true
    try {
      const ok = await adminApi.pingAdmin()
      if (!ok) clear()
      return ok
    } catch {
      clear()
      return false
    } finally {
      checking.value = false
    }
  }

  return { adminInfo, checking, isLogged, login, logout, clear, validate }
})

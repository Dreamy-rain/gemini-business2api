import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const isLoggedIn = ref(false)
  const isLoading = ref(false)
  const lastCheckedAt = ref(0)
  const AUTH_CACHE_MS = 10000
  let checkPromise: Promise<boolean> | null = null

  // 登录
  async function login(password: string) {
    isLoading.value = true
    try {
      await authApi.login({ password })
      await authApi.checkAuth()
      isLoggedIn.value = true
      lastCheckedAt.value = Date.now()
      return true
    } catch (error) {
      isLoggedIn.value = false
      throw error
    } finally {
      isLoading.value = false
    }
  }

  // 登出
  async function logout() {
    try {
      await authApi.logout()
    } finally {
      isLoggedIn.value = false
      lastCheckedAt.value = 0
    }
  }

  // 检查登录状态
  async function checkAuth() {
    const now = Date.now()
    if (isLoggedIn.value && now - lastCheckedAt.value < AUTH_CACHE_MS) {
      return true
    }
    if (checkPromise) {
      return checkPromise
    }
    try {
      checkPromise = (async () => {
        await authApi.checkAuth()
        isLoggedIn.value = true
        return true
      })()
      return await checkPromise
    } catch (error) {
      isLoggedIn.value = false
      return false
    } finally {
      lastCheckedAt.value = Date.now()
      checkPromise = null
    }
  }

  return {
    isLoggedIn,
    isLoading,
    login,
    logout,
    checkAuth,
  }
})

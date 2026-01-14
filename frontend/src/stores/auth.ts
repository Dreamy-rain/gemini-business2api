import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const isLoggedIn = ref(false)
  const isLoading = ref(false)

  // 登录
  async function login(password: string) {
    isLoading.value = true
    try {
      await authApi.login({ password })
      await authApi.checkAuth()
      isLoggedIn.value = true
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
    }
  }

  // 检查登录状态
  async function checkAuth() {
    try {
      await authApi.checkAuth()
      isLoggedIn.value = true
      return true
    } catch (error) {
      isLoggedIn.value = false
      return false
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

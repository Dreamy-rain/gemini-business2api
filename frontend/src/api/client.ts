import axios, { type AxiosInstance, type AxiosError } from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// 创建 axios 实例
export const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 30000,
  withCredentials: true, // 支持 cookie 认证
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    // 可以在这里添加 token 等认证信息
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error: AxiosError) => {
    // 统一错误处理
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.isLoggedIn = false
      router.push('/login')
    }

    const errorMessage = error.response?.data
      ? (error.response.data as any).detail || (error.response.data as any).message
      : error.message

    // 保留 HTTP 状态码，便于调用方做精细化处理（例如任务不存在时的 404）
    const wrapped = new Error(errorMessage || '请求失败') as Error & {
      status?: number
      data?: unknown
    }
    wrapped.status = error.response?.status
    wrapped.data = error.response?.data

    return Promise.reject(wrapped)
  }
)

export default apiClient

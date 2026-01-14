import axios, { type AxiosInstance, type AxiosError } from 'axios'

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
  (error: AxiosError) => {
    // 统一错误处理
    if (error.response?.status === 401) {
      window.location.hash = '#/login'
    }

    const errorMessage = error.response?.data
      ? (error.response.data as any).detail || (error.response.data as any).message
      : error.message

    return Promise.reject(new Error(errorMessage || '请求失败'))
  }
)

export default apiClient

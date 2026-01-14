import apiClient from './client'
import type { LoginRequest, LoginResponse } from '@/types/api'

export const authApi = {
  login: (data: LoginRequest) => {
    const payload = new URLSearchParams()
    payload.append('admin_key', data.password)
    return apiClient.post<URLSearchParams, LoginResponse>('/login', payload, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    })
  },

  logout: () =>
    apiClient.post('/logout'),

  checkAuth: () =>
    apiClient.get('/admin/health'),
}

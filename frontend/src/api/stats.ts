import apiClient from './client'
import type { AdminStats } from '@/types/api'

export const statsApi = {
  overview() {
    return apiClient.get<AdminStats>('/admin/stats')
  },
}

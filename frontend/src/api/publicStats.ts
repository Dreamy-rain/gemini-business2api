import apiClient from './client'
import type { PublicStats } from '@/types/api'

export const publicStatsApi = {
  overview() {
    return apiClient.get<PublicStats>('/public/stats')
  },
}

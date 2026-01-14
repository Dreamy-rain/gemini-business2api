import apiClient from './client'
import type { UptimeResponse } from '@/types/api'

export const monitorApi = {
  uptime(days = 90) {
    return apiClient.get<never, UptimeResponse>('/public/uptime', { params: { days } })
  },
}

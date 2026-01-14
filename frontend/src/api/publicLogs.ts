import apiClient from './client'
import type { PublicLogsResponse } from '@/types/api'

export const publicLogsApi = {
  list: (params?: { limit?: number }) =>
    apiClient.get<never, PublicLogsResponse>('/public/log', { params }),
}

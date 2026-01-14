import apiClient from './client'
import type { PublicDisplay } from '@/types/api'

export const publicDisplayApi = {
  overview() {
    return apiClient.get<PublicDisplay>('/public/display')
  },
}

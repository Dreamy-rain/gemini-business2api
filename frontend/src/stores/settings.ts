import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsApi } from '@/api'
import type { Settings } from '@/types/api'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings | null>(null)
  const isLoading = ref(false)

  // 加载设置
  async function loadSettings() {
    isLoading.value = true
    try {
      settings.value = await settingsApi.get()
    } finally {
      isLoading.value = false
    }
  }

  // 更新设置
  async function updateSettings(newSettings: Settings) {
    await settingsApi.update(newSettings)
    settings.value = newSettings
  }

  return {
    settings,
    isLoading,
    loadSettings,
    updateSettings,
  }
})

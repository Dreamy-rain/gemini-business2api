import { defineStore } from 'pinia'
import { ref } from 'vue'
import { accountsApi } from '@/api'
import type { AdminAccount, AccountConfigItem } from '@/types/api'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<AdminAccount[]>([])
  const isLoading = ref(false)

  async function loadAccounts() {
    isLoading.value = true
    try {
      const response = await accountsApi.list()
      accounts.value = Array.isArray(response)
        ? response
        : response.accounts || []
    } finally {
      isLoading.value = false
    }
  }

  async function deleteAccount(accountId: string) {
    await accountsApi.delete(accountId)
    await loadAccounts()
  }

  async function disableAccount(accountId: string) {
    await accountsApi.disable(accountId)
    await loadAccounts()
  }

  async function enableAccount(accountId: string) {
    await accountsApi.enable(accountId)
    await loadAccounts()
  }

  async function bulkEnable(accountIds: string[]) {
    await Promise.all(accountIds.map(accountId => accountsApi.enable(accountId)))
    await loadAccounts()
  }

  async function bulkDisable(accountIds: string[]) {
    await Promise.all(accountIds.map(accountId => accountsApi.disable(accountId)))
    await loadAccounts()
  }

  async function bulkDelete(accountIds: string[]) {
    await Promise.all(accountIds.map(accountId => accountsApi.delete(accountId)))
    await loadAccounts()
  }

  async function updateConfig(newAccounts: AccountConfigItem[]) {
    await accountsApi.updateConfig(newAccounts)
    await loadAccounts()
  }

  return {
    accounts,
    isLoading,
    loadAccounts,
    deleteAccount,
    disableAccount,
    enableAccount,
    bulkEnable,
    bulkDisable,
    bulkDelete,
    updateConfig,
  }
})

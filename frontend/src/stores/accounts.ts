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
    accounts.value = accounts.value.filter(acc => acc.id !== accountId)
    await accountsApi.delete(accountId)
  }

  async function disableAccount(accountId: string) {
    await accountsApi.disable(accountId)
    const account = accounts.value.find(acc => acc.id === accountId)
    if (account) account.disabled = true
  }

  async function enableAccount(accountId: string) {
    await accountsApi.enable(accountId)
    const account = accounts.value.find(acc => acc.id === accountId)
    if (account) {
      account.disabled = false
      // 清除冷却状态，因为启用操作也会重置这些
      account.cooldown_seconds = 0
      account.cooldown_reason = ''
    }
  }

  async function bulkEnable(accountIds: string[]) {
    await accountsApi.bulkEnable(accountIds)
    accountIds.forEach(id => {
      const account = accounts.value.find(acc => acc.id === id)
      if (account) {
        account.disabled = false
        account.cooldown_seconds = 0
        account.cooldown_reason = ''
      }
    })
  }

  async function bulkDisable(accountIds: string[]) {
    await accountsApi.bulkDisable(accountIds)
    accountIds.forEach(id => {
      const account = accounts.value.find(acc => acc.id === id)
      if (account) account.disabled = true
    })
  }

  async function bulkDelete(accountIds: string[]) {
    await accountsApi.bulkDelete(accountIds)
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

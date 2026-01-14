<template>
  <div class="space-y-8">
    <section class="rounded-3xl border border-border bg-card p-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="grid w-full grid-cols-2 gap-3 sm:flex sm:w-auto sm:items-center">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索账号 ID"
            class="w-full rounded-full border border-input bg-background px-4 py-2 text-sm sm:w-48"
          />
          <SelectMenu
            v-model="statusFilter"
            :options="statusOptions"
          />
        </div>
        <div class="flex w-full flex-wrap items-center gap-3 text-xs text-muted-foreground sm:w-auto sm:flex-nowrap">
          <Checkbox :modelValue="allSelected" @update:modelValue="toggleSelectAll">
            全选
          </Checkbox>
          <span>共 {{ filteredAccounts.length }} 个账号</span>
          <span v-if="selectedCount">已选 {{ selectedCount }} 个</span>
          <div class="ml-auto flex items-center gap-2 sm:ml-0">
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary"
              :class="viewMode === 'table' ? 'bg-accent text-accent-foreground' : ''"
              @click="viewMode = 'table'"
              aria-label="列表视图"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor">
                <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h16v2H4v-2z" />
              </svg>
            </button>
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary"
              :class="viewMode === 'card' ? 'bg-accent text-accent-foreground' : ''"
              @click="viewMode = 'card'"
              aria-label="卡片视图"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor">
                <path d="M4 6h7v6H4V6zm9 0h7v6h-7V6zM4 14h7v4H4v-4zm9 0h7v4h-7v-4z" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                 hover:border-primary hover:text-primary"
          @click="openConfigPanel"
        >
          账户配置
        </button>
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                 hover:border-primary hover:text-primary"
          :disabled="isLoading"
          @click="refreshAccounts"
        >
          刷新列表
        </button>
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                 hover:border-primary hover:text-primary"
          :disabled="!selectedCount"
          @click="handleBulkEnable"
        >
          批量启用
        </button>
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                 hover:border-primary hover:text-primary"
          :disabled="!selectedCount"
          @click="handleBulkDisable"
        >
          批量禁用
        </button>
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-destructive transition-colors
                 hover:border-destructive hover:text-destructive"
          :disabled="!selectedCount"
          @click="handleBulkDelete"
        >
          批量删除
        </button>
      </div>

      <div v-if="viewMode === 'card'" class="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="account in filteredAccounts"
          :key="account.id"
          class="rounded-2xl border border-border bg-card p-4"
          :class="rowClass(account)"
          @click="toggleSelect(account.id)"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-xs text-muted-foreground">账号 ID</p>
              <p class="mt-1 font-mono text-xs text-foreground">{{ account.id }}</p>
            </div>
            <div class="flex items-center gap-2">
              <Checkbox
                :modelValue="selectedIds.has(account.id)"
                @update:modelValue="toggleSelect(account.id)"
                @click.stop
              />
              <span
                class="inline-flex items-center rounded-full border border-border px-3 py-1 text-xs"
                :class="statusClass(account)"
              >
                {{ statusLabel(account) }}
              </span>
            </div>
          </div>

          <div class="mt-4 grid grid-cols-2 gap-3 text-xs text-muted-foreground">
            <div>
              <p>剩余时间</p>
              <p class="mt-1 text-sm font-semibold" :class="remainingClass(account)">
                {{ displayRemaining(account.remaining_display) }}
              </p>
              <p v-if="account.expires_at" class="mt-1 text-[11px]">
                {{ account.expires_at }}
              </p>
            </div>
            <div>
              <p>冷却</p>
              <p class="mt-1" :class="cooldownClass(account)">
                <span v-if="account.cooldown_seconds > 0">
                  {{ formatCooldown(account.cooldown_seconds) }} · {{ account.cooldown_reason }}
                </span>
                <span v-else>
                  {{ account.cooldown_reason || '无冷却' }}
                </span>
              </p>
            </div>
            <div>
              <p>失败数</p>
              <p class="mt-1 text-sm font-semibold text-foreground">{{ account.error_count }}</p>
            </div>
            <div>
              <p>会话数</p>
              <p class="mt-1 text-sm font-semibold text-foreground">{{ account.conversation_count }}</p>
            </div>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2">
            <button
              class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click.stop="openEdit(account.id)"
            >
              编辑
            </button>
            <button
              v-if="shouldShowEnable(account)"
              class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click.stop
              @click="handleEnable(account.id)"
            >
              启用
            </button>
            <button
              v-else
              class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click.stop
              @click="handleDisable(account.id)"
            >
              禁用
            </button>
            <button
              class="rounded-full border border-border px-3 py-1 text-xs text-destructive transition-colors
                     hover:border-destructive hover:text-destructive"
              @click.stop
              @click="handleDelete(account.id)"
            >
              删除
            </button>
          </div>
        </div>
        <div v-if="!filteredAccounts.length && !isLoading" class="rounded-2xl border border-border bg-background p-4 text-center text-xs text-muted-foreground">
          暂无账号数据，请检查后台配置。
        </div>
      </div>

      <div v-else class="relative mt-6 overflow-x-auto overflow-y-visible">
        <table class="min-w-full text-left text-sm">
          <thead class="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            <tr>
              <th class="py-3 pr-4">
                <Checkbox :modelValue="allSelected" @update:modelValue="toggleSelectAll" />
              </th>
              <th class="py-3 pr-6">账号 ID</th>
              <th class="py-3 pr-6">状态</th>
              <th class="py-3 pr-6">
                <span class="inline-flex items-center gap-2">
                  剩余/过期
                  <HelpTip text="过期时间为 12 小时，账户过期以北京时间为准。" />
                </span>
              </th>
              <th class="py-3 pr-6">冷却</th>
              <th class="py-3 pr-6">失败数</th>
              <th class="py-3 pr-6">会话数</th>
              <th class="py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="text-sm text-foreground">
            <tr v-if="!filteredAccounts.length && !isLoading">
              <td colspan="8" class="py-8 text-center text-muted-foreground">
                暂无账号数据，请检查后台配置。
              </td>
            </tr>
            <tr
              v-for="account in filteredAccounts"
              :key="account.id"
              class="border-t border-border"
              :class="rowClass(account)"
              @click="toggleSelect(account.id)"
            >
              <td class="py-4 pr-4" @click.stop>
                <Checkbox
                  :modelValue="selectedIds.has(account.id)"
                  @update:modelValue="toggleSelect(account.id)"
                />
              </td>
              <td class="py-4 pr-6 font-mono text-xs text-foreground">
                {{ account.id }}
              </td>
              <td class="py-4 pr-6">
                <span
                  class="inline-flex items-center rounded-full border border-border px-3 py-1 text-xs"
                  :class="statusClass(account)"
                >
                  {{ statusLabel(account) }}
                </span>
              </td>
              <td class="py-4 pr-6">
                <div class="text-sm font-semibold" :class="remainingClass(account)">
                  {{ displayRemaining(account.remaining_display) }}
                </div>
                <span v-if="account.expires_at" class="block text-[11px] text-muted-foreground">
                  {{ account.expires_at }}
                </span>
              </td>
              <td class="py-4 pr-6 text-xs">
                <span v-if="account.cooldown_seconds > 0" :class="cooldownClass(account)">
                  {{ formatCooldown(account.cooldown_seconds) }} · {{ account.cooldown_reason }}
                </span>
                <span v-else :class="cooldownClass(account)">
                  {{ account.cooldown_reason || '无冷却' }}
                </span>
              </td>
              <td class="py-4 pr-6 text-xs text-muted-foreground">
                {{ account.error_count }}
              </td>
              <td class="py-4 pr-6 text-xs text-muted-foreground">
                {{ account.conversation_count }}
              </td>
              <td class="py-4 text-right">
                <div class="flex flex-wrap justify-end gap-2">
                  <button
                    class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                           hover:border-primary hover:text-primary"
                    @click.stop="openEdit(account.id)"
                  >
                    编辑
                  </button>
                  <button
                    v-if="shouldShowEnable(account)"
                    class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                           hover:border-primary hover:text-primary"
                    @click.stop="handleEnable(account.id)"
                  >
                    启用
                  </button>
                  <button
                    v-else
                    class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                           hover:border-primary hover:text-primary"
                    @click.stop="handleDisable(account.id)"
                  >
                    禁用
                  </button>
                  <button
                    class="rounded-full border border-border px-3 py-1 text-xs text-destructive transition-colors
                           hover:border-destructive hover:text-destructive"
                    @click.stop="handleDelete(account.id)"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
  <ConfirmDialog
    :open="confirmDialog.open.value"
    :title="confirmDialog.title.value"
    :message="confirmDialog.message.value"
    :confirm-text="confirmDialog.confirmText.value"
    :cancel-text="confirmDialog.cancelText.value"
    @confirm="confirmDialog.confirm"
    @cancel="confirmDialog.cancel"
  />
  <Teleport to="body">
    <div v-if="isEditOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="w-full max-w-lg rounded-3xl border border-border bg-card p-6 shadow-xl">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium text-foreground">编辑账号</p>
          <button
            class="text-xs text-muted-foreground transition-colors hover:text-foreground"
            @click="closeEdit"
          >
            关闭
          </button>
        </div>

        <div v-if="editError" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {{ editError }}
        </div>

        <div class="mt-4 space-y-3 text-sm">
          <label class="block text-xs text-muted-foreground">账号 ID</label>
          <input
            v-model="editForm.id"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            disabled
          />

          <label class="block text-xs text-muted-foreground">secure_c_ses</label>
          <textarea
            v-model="editForm.secure_c_ses"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            rows="3"
          ></textarea>

          <label class="block text-xs text-muted-foreground">csesidx</label>
          <input
            v-model="editForm.csesidx"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
          />

          <label class="block text-xs text-muted-foreground">config_id</label>
          <input
            v-model="editForm.config_id"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
          />

          <label class="block text-xs text-muted-foreground">host_c_oses</label>
          <input
            v-model="editForm.host_c_oses"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
          />

          <label class="block text-xs text-muted-foreground">expires_at</label>
          <input
            v-model="editForm.expires_at"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            placeholder="2025-12-23 10:59:21"
          />
        </div>

        <div class="mt-6 flex items-center justify-end gap-2">
          <button
            class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                   hover:border-primary hover:text-primary"
            @click="closeEdit"
          >
            取消
          </button>
          <button
            class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                   hover:opacity-90"
            @click="saveEdit"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="isConfigOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="w-full max-w-3xl rounded-3xl border border-border bg-card p-6 shadow-xl">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium text-foreground">账户配置（JSON）</p>
          <div class="flex items-center gap-2">
            <button
              class="rounded-full bg-foreground px-3 py-1 text-xs text-background transition-opacity
                     hover:opacity-90"
              @click="toggleConfigMask"
            >
              {{ configMasked ? '显示原文' : '脱敏显示' }}
            </button>
            <button
              class="text-xs text-muted-foreground transition-colors hover:text-foreground"
              @click="closeConfigPanel"
            >
              关闭
            </button>
          </div>
        </div>

        <div v-if="configError" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {{ configError }}
        </div>

        <div class="mt-4">
          <textarea
            v-model="configJson"
            class="h-96 w-full rounded-2xl border border-input bg-background px-4 py-3 font-mono text-xs text-foreground"
            spellcheck="false"
            :readonly="configMasked"
          ></textarea>
        </div>

        <div class="mt-6 flex items-center justify-end gap-2">
          <button
            class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                   hover:border-primary hover:text-primary"
            @click="closeConfigPanel"
          >
            取消
          </button>
          <button
            class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                   hover:opacity-90"
            @click="saveConfigPanel"
            :disabled="configMasked"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useAccountsStore } from '@/stores'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import HelpTip from '@/components/ui/HelpTip.vue'
import { accountsApi } from '@/api'
import type { AdminAccount, AccountConfigItem } from '@/types/api'

const accountsStore = useAccountsStore()
const { accounts, isLoading } = storeToRefs(accountsStore)
const confirmDialog = useConfirmDialog()

const searchQuery = ref('')
const statusFilter = ref('all')
const selectedIds = ref<Set<string>>(new Set())
const viewMode = ref<'table' | 'card'>('table')
const isEditOpen = ref(false)
const editError = ref('')
const isConfigOpen = ref(false)
const configError = ref('')
const configJson = ref('')
const configMasked = ref(false)
const configData = ref<AccountConfigItem[]>([])
const editForm = ref<AccountConfigItem>({
  id: '',
  secure_c_ses: '',
  csesidx: '',
  config_id: '',
  host_c_oses: '',
  expires_at: '',
})
const editIndex = ref<number | null>(null)
const configAccounts = ref<AccountConfigItem[]>([])
const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '正常', value: '正常' },
  { label: '即将过期', value: '即将过期' },
  { label: '已过期', value: '已过期' },
  { label: '手动禁用', value: '手动禁用' },
  { label: '错误禁用', value: '错误禁用' },
  { label: '429限流', value: '429限流' },
]

const filteredAccounts = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return accounts.value.filter(account => {
    const matchesQuery = !query || account.id.toLowerCase().includes(query)
    const matchesStatus = statusFilter.value === 'all' || statusLabel(account) === statusFilter.value
    return matchesQuery && matchesStatus
  })
})

const selectedCount = computed(() => selectedIds.value.size)
const allSelected = computed(() =>
  filteredAccounts.value.length > 0 && filteredAccounts.value.every(account => selectedIds.value.has(account.id))
)

const refreshAccounts = async () => {
  await accountsStore.loadAccounts()
  selectedIds.value = new Set()
}

onMounted(async () => {
  await refreshAccounts()
})

const statusLabel = (account: AdminAccount) => {
  if (account.cooldown_reason?.includes('429') && account.cooldown_seconds > 0) {
    return '429限流'
  }
  if (account.cooldown_reason === '错误禁用') {
    return '错误禁用'
  }
  if (account.disabled) {
    return '手动禁用'
  }
  if (account.status === '已过期') {
    return '已过期'
  }
  if (account.status === '即将过期') {
    return '即将过期'
  }
  return '正常'
}

const statusClass = (account: AdminAccount) => {
  const status = statusLabel(account)
  if (status === '429限流' || status === '即将过期') {
    return 'bg-amber-200 text-amber-900'
  }
  if (status === '错误禁用' || status === '已过期') {
    return 'bg-destructive/10 text-destructive'
  }
  if (status === '手动禁用') {
    return 'bg-muted text-muted-foreground'
  }
  return 'bg-emerald-500 text-white'
}

const shouldShowEnable = (account: AdminAccount) => {
  if (account.cooldown_reason?.includes('429') && account.cooldown_seconds > 0) {
    return true
  }
  return account.disabled || account.cooldown_reason === '错误禁用'
}

const displayRemaining = (value: string) => {
  if (value === '已过期') return '过期'
  if (value === '未设置') return '未设置'
  return value
}

const remainingClass = (account: AdminAccount) => {
  if (account.status === '已过期') return 'text-rose-600'
  if (account.status === '即将过期') return 'text-amber-700'
  if (account.status === '未设置') return 'text-muted-foreground'
  return 'text-emerald-600'
}

const formatCooldown = (seconds: number) => {
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} 分钟`
  return `${(seconds / 3600).toFixed(1)} 小时`
}

const cooldownClass = (account: AdminAccount) => {
  if (account.cooldown_seconds > 0) return 'text-amber-700'
  if (account.cooldown_reason === '错误禁用') return 'text-rose-600'
  return 'text-muted-foreground'
}

const rowClass = (account: AdminAccount) => {
  const status = statusLabel(account)
  if (status === '手动禁用' || status === '已过期') {
    return 'bg-muted/70'
  }
  return ''
}

const toggleSelect = (accountId: string) => {
  const next = new Set(selectedIds.value)
  if (next.has(accountId)) {
    next.delete(accountId)
  } else {
    next.add(accountId)
  }
  selectedIds.value = next
}

const toggleSelectAll = () => {
  if (allSelected.value) {
    selectedIds.value = new Set()
    return
  }
  selectedIds.value = new Set(filteredAccounts.value.map(account => account.id))
}

const getConfigId = (acc: AccountConfigItem, index: number) =>
  acc.id || `account_${index + 1}`

const loadConfigList = async () => {
  const response = await accountsApi.getConfig()
  return response.accounts.map((acc, index) => ({
    ...acc,
    id: getConfigId(acc, index),
  }))
}

const applyEditTarget = (list: AccountConfigItem[], accountId: string) => {
  let targetIndex = -1
  for (let i = 0; i < list.length; i += 1) {
    if (list[i].id === accountId) {
      targetIndex = i
      break
    }
  }
  if (targetIndex === -1) {
    editError.value = '未找到对应账号配置。'
    return false
  }

  const target = list[targetIndex]
  editForm.value = {
    id: target.id,
    secure_c_ses: target.secure_c_ses,
    csesidx: target.csesidx,
    config_id: target.config_id,
    host_c_oses: target.host_c_oses,
    expires_at: target.expires_at,
  }
  configAccounts.value = list
  editIndex.value = targetIndex
  isEditOpen.value = true
  return true
}

const openEdit = async (accountId: string) => {
  editError.value = ''
  try {
    const list = await loadConfigList()
    applyEditTarget(list, accountId)
  } catch (error: any) {
    editError.value = error.message || '加载账号配置失败'
  }
}

const openConfigPanel = async () => {
  configError.value = ''
  try {
    const response = await accountsApi.getConfig()
    configData.value = Array.isArray(response.accounts) ? response.accounts : []
    configJson.value = JSON.stringify(maskConfig(configData.value), null, 2)
    configMasked.value = true
    isConfigOpen.value = true
  } catch (error: any) {
    configError.value = error.message || '加载账号配置失败'
  }
}

const closeConfigPanel = () => {
  isConfigOpen.value = false
  configError.value = ''
  configMasked.value = false
}

const getConfigFromEditor = () => {
  const parsed = JSON.parse(configJson.value)
  if (!Array.isArray(parsed)) {
    throw new Error('配置格式必须是数组。')
  }
  return parsed as AccountConfigItem[]
}

const maskValue = (value: unknown) => {
  if (typeof value !== 'string') return value
  if (!value) return value
  if (value.length <= 6) return `${value.slice(0, 2)}****`
  return `${value.slice(0, 3)}****`
}

const maskConfig = (list: AccountConfigItem[]) => {
  const fields = new Set(['secure_c_ses', 'csesidx', 'config_id', 'host_c_oses'])
  return list.map((item) => {
    const next = { ...item }
    fields.forEach((field) => {
      const value = (next as Record<string, unknown>)[field]
      if (value) {
        ;(next as Record<string, unknown>)[field] = maskValue(value)
      }
    })
    return next
  })
}

const toggleConfigMask = () => {
  configError.value = ''
  if (!configMasked.value) {
    try {
      configData.value = getConfigFromEditor()
    } catch (error: any) {
      configError.value = error.message || 'JSON 格式错误'
      return
    }
    configJson.value = JSON.stringify(maskConfig(configData.value), null, 2)
    configMasked.value = true
    return
  }

  configJson.value = JSON.stringify(configData.value, null, 2)
  configMasked.value = false
}

const saveConfigPanel = async () => {
  configError.value = ''
  try {
    const parsed = getConfigFromEditor()
    await accountsStore.updateConfig(parsed)
    closeConfigPanel()
  } catch (error: any) {
    configError.value = error.message || '保存失败'
  }
}

const closeEdit = () => {
  isEditOpen.value = false
  editError.value = ''
}

const saveEdit = async () => {
  if (editIndex.value === null) return
  const next = [...configAccounts.value]
  next[editIndex.value] = {
    ...next[editIndex.value],
    id: editForm.value.id,
    secure_c_ses: editForm.value.secure_c_ses,
    csesidx: editForm.value.csesidx,
    config_id: editForm.value.config_id,
    host_c_oses: editForm.value.host_c_oses || undefined,
    expires_at: editForm.value.expires_at || undefined,
  }

  try {
    await accountsStore.updateConfig(next)
    closeEdit()
  } catch (error: any) {
    editError.value = error.message || '保存失败'
  }
}

const handleBulkEnable = async () => {
  await accountsStore.bulkEnable(Array.from(selectedIds.value))
  selectedIds.value = new Set()
}

const handleBulkDisable = async () => {
  const confirmed = await confirmDialog.ask({
    title: '批量禁用',
    message: '确定要批量禁用选中的账号吗？',
  })
  if (!confirmed) return
  await accountsStore.bulkDisable(Array.from(selectedIds.value))
  selectedIds.value = new Set()
}

const handleBulkDelete = async () => {
  const confirmed = await confirmDialog.ask({
    title: '批量删除',
    message: '确定要批量删除选中的账号吗？',
    confirmText: '删除',
  })
  if (!confirmed) return
  await accountsStore.bulkDelete(Array.from(selectedIds.value))
  selectedIds.value = new Set()
}

const handleEnable = async (accountId: string) => {
  await accountsStore.enableAccount(accountId)
}

const handleDisable = async (accountId: string) => {
  const confirmed = await confirmDialog.ask({
    title: '禁用账号',
    message: '确定要禁用该账号吗？',
  })
  if (!confirmed) return
  await accountsStore.disableAccount(accountId)
}

const handleDelete = async (accountId: string) => {
  const confirmed = await confirmDialog.ask({
    title: '删除账号',
    message: '确定要删除该账号吗？',
    confirmText: '删除',
  })
  if (!confirmed) return
  await accountsStore.deleteAccount(accountId)
}
</script>

<template>
  <div class="rounded-3xl border border-border bg-card p-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-base font-semibold text-foreground">管理日志</p>
      <div class="text-xs text-muted-foreground">
        自动刷新：{{ autoRefreshEnabled ? '开启' : '关闭' }}
      </div>
    </div>

    <div class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <div class="rounded-2xl border border-border bg-card px-4 py-3 text-center">
        <div class="text-[11px] text-muted-foreground">总数</div>
        <div class="mt-1 text-lg font-semibold text-foreground">{{ stats?.memory.total ?? 0 }}</div>
      </div>
      <div class="rounded-2xl border border-border bg-card px-4 py-3 text-center">
        <div class="text-[11px] text-muted-foreground">对话</div>
        <div class="mt-1 text-lg font-semibold text-foreground">{{ stats?.chat_count ?? 0 }}</div>
      </div>
      <div class="rounded-2xl border border-border bg-card px-4 py-3 text-center">
        <div class="text-[11px] text-muted-foreground">INFO</div>
        <div class="mt-1 text-lg font-semibold text-foreground">{{ stats?.memory.by_level.INFO ?? 0 }}</div>
      </div>
      <div class="rounded-2xl border border-border bg-card px-4 py-3 text-center">
        <div class="text-[11px] text-muted-foreground">WARNING</div>
        <div class="mt-1 text-lg font-semibold text-foreground">{{ stats?.memory.by_level.WARNING ?? 0 }}</div>
      </div>
      <div class="rounded-2xl border border-border bg-card px-4 py-3 text-center">
        <div class="text-[11px] text-muted-foreground">ERROR</div>
        <div class="mt-1 text-lg font-semibold" :class="stats?.memory.by_level.ERROR ? 'text-rose-600' : 'text-foreground'">
          {{ stats?.memory.by_level.ERROR ?? 0 }}
        </div>
      </div>
      <div class="rounded-2xl border border-border bg-card px-4 py-3 text-center">
        <div class="text-[11px] text-muted-foreground">缓存上限</div>
        <div class="mt-1 text-lg font-semibold text-foreground">{{ stats?.memory.capacity ?? 0 }}</div>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-2 sm:flex-nowrap">
      <div class="w-44 shrink-0">
        <SelectMenu v-model="filters.level" :options="levelOptions" />
      </div>
      <input
        v-model.trim="filters.search"
        type="text"
        placeholder="搜索..."
        class="min-w-[200px] flex-1 rounded-2xl border border-border bg-background px-3 py-2 text-xs text-foreground sm:min-w-0"
      />
      <input
        v-model.number="filters.limit"
        type="number"
        min="10"
        max="1000"
        step="100"
        class="w-24 rounded-2xl border border-border bg-background px-3 py-2 text-xs text-foreground"
      />
      <button
        class="rounded-full border border-border px-4 py-2 text-xs font-medium text-foreground transition-colors
               hover:border-primary hover:text-primary"
        @click="fetchLogs"
      >
        查询
      </button>
      <button
        class="rounded-full border border-border px-4 py-2 text-xs font-medium text-foreground transition-colors
               hover:border-primary hover:text-primary"
        @click="exportLogs"
      >
        导出
      </button>
      <button
        class="rounded-full border border-border px-4 py-2 text-xs font-medium text-foreground transition-colors
               hover:border-primary hover:text-primary"
        @click="toggleView"
      >
        {{ rawView ? '结构化视图' : '原始视图' }}
      </button>
      <button
        class="rounded-full px-4 py-2 text-xs font-medium transition-colors"
        :class="autoRefreshEnabled ? 'bg-primary text-primary-foreground' : 'border border-border text-muted-foreground hover:text-foreground'"
        @click="toggleAutoRefresh"
      >
        自动刷新
      </button>
      <button
        class="rounded-full border border-border px-4 py-2 text-xs font-medium text-destructive transition-colors
               hover:border-destructive/60"
        @click="confirmOpen = true"
      >
        清空
      </button>
    </div>

    <div v-if="statusMessage" class="mt-3 text-xs" :class="statusToneClass">
      {{ statusMessage }}
    </div>

    <div v-if="errorMessage" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
      {{ errorMessage }}
    </div>

    <div
      v-if="rawView"
      ref="rawLogContainer"
      class="scrollbar-slim mt-4 max-h-[60vh] overflow-x-auto overflow-y-auto rounded-2xl border border-border bg-black px-4 py-3 text-xs text-green-200"
    >
      <pre class="whitespace-pre font-mono leading-relaxed">{{ rawLogView.text }}</pre>
    </div>
    <div
      v-else
      ref="structuredLogContainer"
      class="scrollbar-slim mt-4 max-h-[60vh] space-y-3 overflow-y-auto rounded-2xl border border-border bg-card px-4 py-3"
    >
      <div v-if="structuredView.ungrouped.length === 0 && structuredView.groups.length === 0" class="text-xs text-muted-foreground">
        暂无日志
      </div>

      <div v-for="(log, index) in structuredView.ungrouped" :key="`u-${index}`">
        <div class="cv-auto flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-muted-foreground">{{ log.time }}</span>
            <span :class="levelBadgeClass(log.level)">{{ log.level }}</span>
            <span
              v-for="tag in log.tags"
              :key="tag"
              class="rounded px-2 py-0.5 text-[10px] font-semibold text-white"
              :style="{ backgroundColor: getCategoryColor(tag) }"
            >
              {{ tag }}
            </span>
            <span
              v-if="log.accountId"
              class="text-[11px] font-semibold"
              :style="{ color: getAccountColor(log.accountId) }"
            >
              {{ log.accountId }}
            </span>
          </div>
          <div class="w-full text-foreground md:w-auto md:flex-1">
            {{ log.text }}
          </div>
        </div>
      </div>

      <div v-for="group in structuredView.groups" :key="group.id" class="rounded-2xl border border-border bg-card">
        <button
          type="button"
          class="flex w-full flex-wrap items-center gap-2 rounded-2xl bg-secondary/40 px-4 py-3 text-left text-xs transition hover:bg-secondary/60"
          @click="toggleGroup(group.id)"
        >
          <span :class="statusBadgeClass(group.status)">{{ statusLabel(group.status) }}</span>
          <span class="text-muted-foreground">req_{{ group.id }}</span>
          <span v-if="group.accountId" class="text-xs font-semibold" :style="{ color: getAccountColor(group.accountId) }">
            {{ group.accountId }}
          </span>
          <span v-if="group.model" class="text-muted-foreground">{{ group.model }}</span>
          <span v-if="isGroupLimited(group)" class="text-[10px] text-muted-foreground">
            仅显示最近 {{ groupLogLimit }} 条
          </span>
          <span class="text-muted-foreground">{{ group.logs.length }} 条日志</span>
          <span
            class="ml-auto text-muted-foreground transition-transform"
            :class="{ 'rotate-90': !isCollapsed(group.id) }"
          >
            ▸
          </span>
        </button>
        <div v-if="!isCollapsed(group.id)" class="space-y-2 px-4 py-3">
          <div
            v-for="(log, logIndex) in visibleGroupLogs(group)"
            :key="`${group.id}-${logIndex}`"
            class="cv-auto flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs"
          >
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-muted-foreground">{{ log.time }}</span>
              <span :class="levelBadgeClass(log.level)">{{ log.level }}</span>
              <span
                v-for="tag in log.tags"
                :key="tag"
                class="rounded px-2 py-0.5 text-[10px] font-semibold text-white"
                :style="{ backgroundColor: getCategoryColor(tag) }"
              >
                {{ tag }}
              </span>
              <span
                v-if="log.accountId"
                class="text-[11px] font-semibold"
                :style="{ color: getAccountColor(log.accountId) }"
              >
                {{ log.accountId }}
              </span>
            </div>
            <div class="w-full text-foreground md:w-auto md:flex-1">
              {{ log.text }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <ConfirmDialog
    :open="confirmOpen"
    title="确认操作"
    message="确定要清空所有运行日志吗？"
    confirm-text="确认"
    cancel-text="取消"
    @confirm="clearLogs"
    @cancel="confirmOpen = false"
  />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { logsApi } from '@/api'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import type { AdminLogStats, LogEntry } from '@/types/api'

type ParsedLogEntry = LogEntry & {
  tags: string[]
  accountId: string
  text: string
  reqId: string
}

type GroupedLog = {
  id: string
  logs: ParsedLogEntry[]
  status: string
  accountId: string
  model: string
}

type GroupedLogState = {
  ungrouped: ParsedLogEntry[]
  groups: GroupedLog[]
}

const logs = ref<LogEntry[]>([])
const parsedLogs = ref<ParsedLogEntry[]>([])
const groupedLogs = ref<GroupedLogState>({ ungrouped: [], groups: [] })
const stats = ref<AdminLogStats | null>(null)
const errorMessage = ref('')
const statusMessage = ref('')
const statusTone = ref<'success' | 'error'>('success')
const confirmOpen = ref(false)
const autoRefreshEnabled = ref(true)
const collapsedState = ref<Record<string, boolean>>({})
const rawView = ref(true)
const rawLogContainer = ref<HTMLDivElement | null>(null)
const structuredLogContainer = ref<HTMLDivElement | null>(null)
const structuredRenderLimit = 1000
const rawRenderLimit = 1000
const groupLogLimit = 200
const refreshIntervalMs = 3000
let timer: number | undefined
let isFetching = false

const filters = reactive({
  level: '',
  search: '',
  limit: 300,
})

const levelOptions = [
  { label: '全部', value: '' },
  { label: 'INFO', value: 'INFO' },
  { label: 'WARNING', value: 'WARNING' },
  { label: 'ERROR', value: 'ERROR' },
]

const CATEGORY_COLORS: Record<string, string> = {
  SYSTEM: '#9e9e9e',
  CONFIG: '#607d8b',
  LOG: '#9e9e9e',
  AUTH: '#4caf50',
  SESSION: '#00bcd4',
  FILE: '#ff9800',
  CHAT: '#2196f3',
  API: '#8bc34a',
  CACHE: '#9c27b0',
  ACCOUNT: '#f44336',
  MULTI: '#673ab7',
}

const ACCOUNT_COLORS: Record<string, string> = {
  account_1: '#9c27b0',
  account_2: '#e91e63',
  account_3: '#00bcd4',
  account_4: '#4caf50',
  account_5: '#ff9800',
}

const statusToneClass = computed(() =>
  statusTone.value === 'error' ? 'text-destructive' : 'text-muted-foreground'
)

const getCategoryColor = (category: string) => CATEGORY_COLORS[category] || '#757575'
const getAccountColor = (accountId: string) => ACCOUNT_COLORS[accountId] || '#757575'

const levelBadgeClass = (level: LogEntry['level']) => {
  const base = 'rounded px-2 py-0.5 text-[10px] font-semibold'
  if (level === 'INFO') return `${base} bg-blue-100 text-blue-700`
  if (level === 'WARNING') return `${base} bg-amber-100 text-amber-700`
  if (level === 'ERROR' || level === 'CRITICAL') return `${base} bg-rose-100 text-rose-700`
  return `${base} bg-violet-100 text-violet-700`
}

const statusBadgeClass = (status: string) => {
  const base = 'rounded-md px-2 py-0.5 text-[11px] font-semibold'
  if (status === 'success') return `${base} bg-emerald-100 text-emerald-700`
  if (status === 'error') return `${base} bg-rose-100 text-rose-700`
  if (status === 'timeout') return `${base} bg-amber-100 text-amber-700`
  return `${base} bg-amber-100 text-amber-700`
}

const statusLabel = (status: string) => {
  if (status === 'success') return '成功'
  if (status === 'error') return '失败'
  if (status === 'timeout') return '超时'
  return '进行中'
}

const parseLogMessage = (message: string) => {
  let remaining = message
  const tags: string[] = []
  let accountId = ''
  const tagRegex = /^\[([A-Za-z0-9_]+)\]/

  while (true) {
    const match = remaining.match(tagRegex)
    if (!match) break
    const tag = match[1]
    remaining = remaining.slice(match[0].length).trim()

    if (tag.startsWith('req_')) {
      continue
    }
    if (tag.startsWith('account_')) {
      accountId = tag
      continue
    }
    tags.push(tag)
  }

  return { tags, accountId, text: remaining }
}

const parseLogEntry = (log: LogEntry): ParsedLogEntry => {
  const parsed = parseLogMessage(log.message)
  const reqMatch = log.message.match(/\[req_([a-z0-9]+)\]/i)
  return {
    ...log,
    ...parsed,
    reqId: reqMatch ? reqMatch[1] : '',
  }
}

const parseLogTime = (value: string) => {
  if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return new Date(value)
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
    return new Date(value.replace(' ', 'T'))
  }
  if (/^\d{2}:\d{2}:\d{2}$/.test(value)) {
    const now = new Date()
    const [hours, minutes, seconds] = value.split(':').map(Number)
    const parsed = new Date(now)
    parsed.setHours(hours, minutes, seconds, 0)
    return parsed
  }
  return null
}

const getGroupStatus = (groupLogs: LogEntry[]) => {
  const lastLog = groupLogs[groupLogs.length - 1]
  const lastMessage = lastLog.message

  if (lastMessage.includes('响应完成') || lastMessage.includes('非流式响应完成')) {
    return 'success'
  }
  if (lastLog.level === 'ERROR' || lastMessage.includes('失败')) {
    return 'error'
  }

  const parsedTime = parseLogTime(lastLog.time)
  if (parsedTime) {
    const diffMinutes = (Date.now() - parsedTime.getTime()) / 1000 / 60
    if (diffMinutes > 5) {
      return 'timeout'
    }
  }

  return 'in_progress'
}

const buildGroupedLogs = (items: ParsedLogEntry[]): GroupedLogState => {
  const groups = new Map<string, ParsedLogEntry[]>()
  const groupOrder: string[] = []
  const ungrouped: ParsedLogEntry[] = []

  items.forEach((log) => {
    if (log.reqId) {
      if (!groups.has(log.reqId)) {
        groups.set(log.reqId, [])
        groupOrder.push(log.reqId)
      }
      groups.get(log.reqId)?.push(log)
    } else {
      ungrouped.push(log)
    }
  })

  const groupList = groupOrder.map((id) => {
    const groupLogs = groups.get(id) || []
    const firstLog = groupLogs[0]
    const accountMatch = firstLog?.message.match(/\[(account_[^\]]+)\]/i)
    const modelMatch = firstLog?.message.match(/收到请求: ([^ |]+)/) || firstLog?.message.match(/Received request: ([^ |]+)/)

    return {
      id,
      logs: groupLogs,
      status: getGroupStatus(groupLogs),
      accountId: firstLog?.accountId || (accountMatch ? accountMatch[1] : ''),
      model: modelMatch ? modelMatch[1] : '',
    }
  })

  return { ungrouped, groups: groupList }
}

const structuredView = computed(() => {
  const ungrouped = groupedLogs.value.ungrouped
  const groups = groupedLogs.value.groups
  const limitedUngrouped = ungrouped.length > structuredRenderLimit
    ? ungrouped.slice(-structuredRenderLimit)
    : ungrouped
  const limitedGroups = groups.length > structuredRenderLimit
    ? groups.slice(-structuredRenderLimit)
    : groups

  return {
    ungrouped: limitedUngrouped,
    groups: limitedGroups,
    limited: ungrouped.length > limitedUngrouped.length || groups.length > limitedGroups.length,
    ungroupedTotal: ungrouped.length,
    groupsTotal: groups.length,
    ungroupedShowing: limitedUngrouped.length,
    groupsShowing: limitedGroups.length,
  }
})

const rawLogView = computed(() => {
  const total = parsedLogs.value.length
  const startIndex = total > rawRenderLimit ? total - rawRenderLimit : 0
  const slice = parsedLogs.value.slice(startIndex)
  const text = slice.map(log => `${log.time} | ${log.level} | ${log.message}`).join('\n')
  const showing = slice.length
  return {
    text,
    total,
    showing,
    limited: total > showing,
  }
})

const isCollapsed = (requestId: string) => collapsedState.value[requestId] === true

const toggleGroup = (requestId: string) => {
  collapsedState.value[requestId] = !isCollapsed(requestId)
  localStorage.setItem('log-fold-state', JSON.stringify(collapsedState.value))
}

const isGroupLimited = (group: GroupedLog) => group.logs.length > groupLogLimit

const visibleGroupLogs = (group: GroupedLog) => {
  if (group.logs.length <= groupLogLimit) return group.logs
  return group.logs.slice(-groupLogLimit)
}

const normalizeLimit = () => {
  if (!filters.limit || Number.isNaN(filters.limit)) {
    filters.limit = 300
  }
  filters.limit = Math.min(Math.max(filters.limit, 10), 1000)
}

const fetchLogs = async () => {
  if (isFetching) return
  isFetching = true
  errorMessage.value = ''
  statusMessage.value = ''
  normalizeLimit()
  try {
    const response = await logsApi.list({
      limit: filters.limit,
      level: filters.level || undefined,
      search: filters.search || undefined,
    })
    logs.value = response.logs
    parsedLogs.value = response.logs.map(parseLogEntry)
    groupedLogs.value = buildGroupedLogs(parsedLogs.value)
    stats.value = response.stats
  } catch (error: any) {
    errorMessage.value = error.message || '日志加载失败'
  } finally {
    isFetching = false
    requestAnimationFrame(scrollToBottom)
  }
}

const exportLogs = async () => {
  statusMessage.value = ''
  statusTone.value = 'success'
  try {
    const response = await logsApi.list({
      limit: 1000,
      level: filters.level || undefined,
      search: filters.search || undefined,
    })
    const blob = new Blob(
      [JSON.stringify({ exported_at: new Date().toISOString(), logs: response.logs }, null, 2)],
      { type: 'application/json' }
    )
    const blobUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = blobUrl
    anchor.download = `logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`
    anchor.click()
    URL.revokeObjectURL(blobUrl)
    statusMessage.value = '导出成功'
  } catch (error: any) {
    statusTone.value = 'error'
    statusMessage.value = error.message || '导出失败'
  }
}

const clearLogs = async () => {
  confirmOpen.value = false
  try {
    await logsApi.clear()
    statusTone.value = 'success'
    statusMessage.value = '已清空日志'
    await fetchLogs()
  } catch (error: any) {
    statusTone.value = 'error'
    statusMessage.value = error.message || '清空失败'
  }
}

const stopAutoRefresh = () => {
  if (timer) {
    window.clearTimeout(timer)
    timer = undefined
  }
}

const scheduleAutoRefresh = () => {
  if (!autoRefreshEnabled.value || document.hidden) return
  timer = window.setTimeout(async () => {
    await fetchLogs()
    scheduleAutoRefresh()
  }, refreshIntervalMs)
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  scheduleAutoRefresh()
}

const toggleAutoRefresh = () => {
  autoRefreshEnabled.value = !autoRefreshEnabled.value
  if (autoRefreshEnabled.value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
}

const toggleView = () => {
  rawView.value = !rawView.value
  requestAnimationFrame(scrollToBottom)
}

const scrollToBottom = () => {
  if (rawView.value && rawLogContainer.value) {
    rawLogContainer.value.scrollTop = rawLogContainer.value.scrollHeight
  }
  if (!rawView.value && structuredLogContainer.value) {
    structuredLogContainer.value.scrollTop = structuredLogContainer.value.scrollHeight
  }
}

const handleVisibilityChange = () => {
  if (document.hidden) {
    stopAutoRefresh()
  } else if (autoRefreshEnabled.value) {
    startAutoRefresh()
  }
}

onMounted(() => {
  const saved = localStorage.getItem('log-fold-state')
  if (saved) {
    try {
      collapsedState.value = JSON.parse(saved)
    } catch {
      collapsedState.value = {}
    }
  }
  fetchLogs()
  startAutoRefresh()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  stopAutoRefresh()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

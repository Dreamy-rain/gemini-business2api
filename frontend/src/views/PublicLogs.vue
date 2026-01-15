<template>
  <div class="min-h-screen overflow-x-hidden bg-card/70 text-foreground backdrop-blur">
    <div class="mx-auto w-full max-w-6xl min-w-0 px-4 py-8">
      <section class="rounded-3xl border border-border bg-card p-6">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="flex items-center gap-3">
            <img :src="logoUrl" alt="Gemini Business2API" class="h-8 w-8 object-contain" />
            <div>
              <p class="text-base font-semibold text-foreground">公开日志</p>
            </div>
          </div>
          <div class="flex items-center gap-2 text-xs text-muted-foreground">
            <span>自动刷新：3s</span>
          </div>
        </div>

        <div
          class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-secondary/40 px-4 py-3"
        >
          <div class="text-xs text-muted-foreground">
            展示最近 <span class="font-semibold text-foreground">{{ limit }}</span> 条会话日志
          </div>
          <a
            v-if="chatUrl"
            :href="chatUrl"
            target="_blank"
            class="text-xs font-medium text-emerald-600 transition hover:text-emerald-500"
          >
            开始对话
          </a>
          <span v-else class="text-xs text-muted-foreground">开始对话</span>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div
            v-for="card in statCards"
            :key="card.label"
            class="rounded-2xl border border-border bg-card px-4 py-3 text-center"
          >
            <div class="text-[11px] text-muted-foreground">{{ card.label }}</div>
            <div class="mt-1 text-lg font-semibold" :style="{ color: card.color || undefined }">
              {{ card.value }}
            </div>
          </div>
        </div>

        <div
          v-if="errorMessage"
          class="mt-4 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
        >
          {{ errorMessage }}
        </div>

        <div
          v-if="logs.length === 0 && !errorMessage"
          class="mt-4 rounded-2xl border border-border bg-secondary/30 px-4 py-6 text-center text-sm text-muted-foreground"
        >
          暂无日志
        </div>

        <div v-else-if="logs.length > 0" class="mt-4 max-h-[60vh] space-y-3 overflow-y-auto pr-1 scrollbar-slim">
          <div v-for="log in visibleLogs" :key="log.request_id" class="rounded-2xl border border-border bg-card">
            <button
              type="button"
              class="flex w-full flex-wrap items-center gap-2 rounded-2xl bg-secondary/40 px-4 py-3 text-left text-xs transition hover:bg-secondary/60"
              @click="toggleGroup(log.request_id)"
            >
              <span :class="statusBadgeClass(log.status)">{{ statusLabel(log.status) }}</span>
              <span class="text-muted-foreground">req_{{ log.request_id }}</span>
              <span class="text-muted-foreground">{{ log.events.length }} 条事件</span>
              <span
                class="ml-auto text-muted-foreground transition-transform"
                :class="{ 'rotate-90': !isCollapsed(log.request_id) }"
              >
                ▸
              </span>
            </button>

            <div v-if="!isCollapsed(log.request_id)" class="space-y-2 px-4 py-3">
              <div
                v-for="event in log.events"
                :key="`${log.request_id}-${event.time}-${event.type}`"
                class="cv-auto flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-3 py-2 text-xs"
              >
                <div class="text-muted-foreground">{{ event.time }}</div>
                <span :class="eventBadgeClass(event)">{{ eventLabel(event) }}</span>
                <div class="flex-1 text-foreground">{{ event.content }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { publicDisplayApi, publicLogsApi, publicStatsApi } from '@/api'
import type {
  PublicDisplay,
  PublicLogEvent,
  PublicLogGroup,
  PublicLogStatus,
  PublicStats,
} from '@/types/api'

const logs = ref<PublicLogGroup[]>([])
const stats = ref<PublicStats | null>(null)
const display = ref<PublicDisplay | null>(null)
const errorMessage = ref('')
const lastUpdated = ref('--:--')
const collapsedState = ref<Record<string, boolean>>({})
const limit = 1000
const renderLimit = 1000
const refreshIntervalMs = 3000
let timer: number | undefined
let isFetching = false

const logoUrl = computed(() => {
  const url = display.value?.logo_url?.trim()
  return url || '/logo.svg'
})
const chatUrl = computed(() => display.value?.chat_url?.trim() || '')

const totalLogs = computed(() => logs.value.length)
const successLogs = computed(() => logs.value.filter(log => log.status === 'success').length)
const errorLogs = computed(() => logs.value.filter(log => log.status === 'error').length)

const visibleLogs = computed(() => {
  if (logs.value.length > renderLimit) {
    return logs.value.slice(-renderLimit)
  }
  return logs.value
})

const avgResponseTime = computed(() => {
  let total = 0
  let count = 0

  logs.value.forEach(log => {
    if (log.status !== 'success') return
    log.events.forEach(event => {
      if (event.type !== 'complete') return
      const match = event.content.match(/([0-9]+(?:\.[0-9]+)?)\s*s/)
      if (match) {
        total += Number(match[1])
        count += 1
      }
    })
  })

  if (count === 0) return '-'
  return `${(total / count).toFixed(1)}s`
})

const successRate = computed(() => {
  const completed = successLogs.value + errorLogs.value
  if (completed === 0) return '-'
  return `${((successLogs.value / completed) * 100).toFixed(1)}%`
})

const statCards = computed(() => [
  { label: '总访客', value: stats.value?.total_visitors ?? 0 },
  {
    label: '每分钟请求',
    value: stats.value?.requests_per_minute ?? 0,
    color: stats.value?.load_color,
  },
  { label: '平均响应', value: avgResponseTime.value },
  { label: '成功率', value: successRate.value, color: '#10b981' },
  { label: '对话次数', value: totalLogs.value },
  { label: '成功', value: successLogs.value, color: '#10b981' },
  { label: '失败', value: errorLogs.value, color: '#ef4444' },
  { label: '更新时间', value: lastUpdated.value, color: '#6b7280' },
])

const statusLabel = (status: PublicLogStatus) => {
  if (status === 'success') return '成功'
  if (status === 'error') return '失败'
  if (status === 'timeout') return '超时'
  return '进行中'
}

const statusBadgeClass = (status: PublicLogStatus) => {
  const base = 'rounded-md px-2 py-0.5 text-[11px] font-semibold'
  if (status === 'success') return `${base} bg-emerald-100 text-emerald-700`
  if (status === 'error') return `${base} bg-rose-100 text-rose-700`
  if (status === 'timeout') return `${base} bg-amber-100 text-amber-700`
  return `${base} bg-amber-100 text-amber-700`
}

const eventLabel = (event: PublicLogEvent) => {
  if (event.type === 'start') return '开始对话'
  if (event.type === 'select') return '选择'
  if (event.type === 'retry') return '重试'
  if (event.type === 'switch') return '切换'
  if (event.type === 'complete') {
    if (event.status === 'success') return '完成'
    if (event.status === 'error') return '失败'
    if (event.status === 'timeout') return '超时'
    return '完成'
  }
  return '事件'
}

const eventBadgeClass = (event: PublicLogEvent) => {
  const base = 'rounded-md px-2 py-0.5 text-[11px] font-semibold'
  if (event.type === 'start') return `${base} bg-blue-100 text-blue-700`
  if (event.type === 'select') return `${base} bg-violet-100 text-violet-700`
  if (event.type === 'retry') return `${base} bg-amber-100 text-amber-700`
  if (event.type === 'switch') return `${base} bg-cyan-100 text-cyan-700`
  if (event.type === 'complete') {
    if (event.status === 'success') return `${base} bg-emerald-100 text-emerald-700`
    if (event.status === 'error') return `${base} bg-rose-100 text-rose-700`
    if (event.status === 'timeout') return `${base} bg-amber-100 text-amber-700`
  }
  return `${base} bg-slate-100 text-slate-600`
}

const loadCollapseState = () => {
  try {
    const saved = localStorage.getItem('public-log-fold-state')
    if (saved) collapsedState.value = JSON.parse(saved)
  } catch {
    collapsedState.value = {}
  }
}

const saveCollapseState = () => {
  localStorage.setItem('public-log-fold-state', JSON.stringify(collapsedState.value))
}

const isCollapsed = (requestId: string) => collapsedState.value[requestId] === true

const toggleGroup = (requestId: string) => {
  collapsedState.value[requestId] = !isCollapsed(requestId)
  saveCollapseState()
}

const fetchData = async () => {
  if (isFetching) return
  isFetching = true
  errorMessage.value = ''
  try {
    const [logsResponse, statsResponse] = await Promise.all([
      publicLogsApi.list({ limit }),
      publicStatsApi.overview(),
    ])
    logs.value = logsResponse.logs
    stats.value = statsResponse
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch (error: any) {
    errorMessage.value = error.message || '日志加载失败'
  } finally {
    isFetching = false
  }
}

const fetchDisplay = async () => {
  try {
    display.value = await publicDisplayApi.overview()
  } catch {
    display.value = null
  }
}

const stopAutoRefresh = () => {
  if (timer) {
    window.clearTimeout(timer)
    timer = undefined
  }
}

const scheduleAutoRefresh = () => {
  if (document.hidden) return
  timer = window.setTimeout(async () => {
    await fetchData()
    scheduleAutoRefresh()
  }, refreshIntervalMs)
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  scheduleAutoRefresh()
}

const handleVisibilityChange = () => {
  if (document.hidden) {
    stopAutoRefresh()
  } else {
    startAutoRefresh()
  }
}

onMounted(() => {
  loadCollapseState()
  fetchDisplay()
  fetchData()
  startAutoRefresh()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  stopAutoRefresh()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

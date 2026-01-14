import { computed, ref } from 'vue'
import { monitorApi } from '@/api'
import type { UptimeHeartbeat, UptimeResponse, UptimeService } from '@/types/api'

type ServiceView = {
  key: string
  name: string
  statusLabel: string
  statusClass: string
  uptime: number
  total: number
  success: number
  beats: Array<{ className: string; tooltip: string | null }>
}

const slowThresholdMs = 40000
const maxBeats = 60

const mapStatusLabel = (statusValue: UptimeService['status']) => {
  if (statusValue === 'up') return '正常'
  if (statusValue === 'warn') return '注意'
  if (statusValue === 'down') return '异常'
  return '未知'
}

const mapStatusClass = (statusValue: UptimeService['status']) => {
  if (statusValue === 'up') return 'monitor-badge--up'
  if (statusValue === 'warn') return 'monitor-badge--warn'
  if (statusValue === 'down') return 'monitor-badge--down'
  return 'monitor-badge--unknown'
}

const buildBeats = (heartbeats: UptimeHeartbeat[] = []) => {
  const beats: Array<{ className: string; tooltip: string | null }> = []
  for (let i = 0; i < maxBeats; i += 1) {
    if (i < heartbeats.length) {
      const beat = heartbeats[i]
      const latencyMs = beat.latency_ms ?? null
      const isSlow = beat.success && latencyMs !== null && latencyMs > slowThresholdMs
      const level = beat.level ?? (isSlow ? 'warn' : (beat.success ? 'up' : 'down'))
      const className = level === 'warn'
        ? 'monitor-beat--warn'
        : (level === 'up' ? 'monitor-beat--up' : 'monitor-beat--down')
      const latencyText = latencyMs !== null
        ? ` · 首响 ${(Math.max(latencyMs, 0) / 1000).toFixed(1)}s`
        : ''
      const statusCodeText = beat.status_code ? ` · HTTP ${beat.status_code}` : ''
      const statusText = level === 'warn' ? '警告' : (beat.success ? '成功' : '失败')

      beats.push({
        className,
        tooltip: `${beat.time} · ${statusText}${statusCodeText}${latencyText}`,
      })
    } else {
      beats.push({ className: 'monitor-beat--empty', tooltip: null })
    }
  }
  return beats
}

export function useUptimeStatus() {
  const status = ref<UptimeResponse | null>(null)
  const errorMessage = ref('')
  const isLoading = ref(false)

  const updatedAt = computed(() => status.value?.updated_at ?? '')

  const services = computed<ServiceView[]>(() => {
    if (!status.value) return []

    return Object.entries(status.value.services).map(([key, service]) => ({
      key,
      name: service.name,
      statusLabel: mapStatusLabel(service.status),
      statusClass: mapStatusClass(service.status),
      uptime: service.uptime,
      total: service.total,
      success: service.success,
      beats: buildBeats(service.heartbeats),
    }))
  })

  const refreshStatus = async () => {
    if (isLoading.value) return
    isLoading.value = true
    errorMessage.value = ''

    try {
      status.value = await monitorApi.uptime()
    } catch (error) {
      errorMessage.value = (error as Error).message || '监控数据获取失败'
    } finally {
      isLoading.value = false
    }
  }

  return {
    services,
    updatedAt,
    errorMessage,
    isLoading,
    refreshStatus,
  }
}

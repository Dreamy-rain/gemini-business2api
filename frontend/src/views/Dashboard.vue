<template>
  <div class="space-y-8">
    <section class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      <div
        v-for="stat in stats"
        :key="stat.label"
        class="rounded-3xl border border-border bg-card p-6"
      >
        <p class="text-xs uppercase tracking-[0.3em] text-muted-foreground">{{ stat.label }}</p>
        <p class="mt-4 text-3xl font-semibold text-foreground">{{ stat.value }}</p>
        <p class="mt-2 text-xs text-muted-foreground">{{ stat.caption }}</p>
      </div>
    </section>

    <section class="dashboard-split flex w-full flex-col gap-6">
      <div class="dashboard-main w-full min-w-0 rounded-3xl border border-border bg-card p-6 overflow-hidden">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium text-foreground">调用趋势（近12小时）</p>
        </div>
        <div ref="trendChartRef" class="mt-6 h-56 w-full max-w-full lg:h-64"></div>
        <div class="mt-6 border-t border-border pt-6">
          <p class="text-sm font-medium text-foreground">模型调用分布（近12小时）</p>
          <div ref="modelChartRef" class="mt-4 h-56 w-full max-w-full lg:h-64"></div>
        </div>
      </div>

      <div class="dashboard-side w-full min-w-0 rounded-3xl border border-border bg-card p-6">
        <p class="text-sm font-medium text-foreground">账号健康</p>
        <div class="mt-6 space-y-4">
          <div v-for="item in accountBreakdown" :key="item.label" class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span class="flex items-center gap-2 text-muted-foreground">
                {{ item.label }}
                <HelpTip v-if="item.tooltip" :text="item.tooltip" />
              </span>
              <span class="font-medium text-foreground">{{ item.value }}</span>
            </div>
            <div class="h-2 w-full rounded-full bg-secondary">
              <div class="h-2 rounded-full" :class="item.barClass" :style="{ width: item.percent + '%' }"></div>
            </div>
          </div>
        </div>
        <div class="mt-6 rounded-2xl border border-border bg-secondary/50 p-4 text-xs text-muted-foreground">
          建议及时处理失败或过期账号，避免影响轮询效率。
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { statsApi } from '@/api'
import HelpTip from '@/components/ui/HelpTip.vue'

type ChartInstance = {
  setOption: (option: unknown) => void
  resize: () => void
  dispose: () => void
}

const stats = ref([
  { label: '账号总数', value: '0', caption: '账号池中已加载的总数量。' },
  { label: '活跃账号', value: '0', caption: '未过期、未禁用、未限流且可用。' },
  { label: '失败账号', value: '0', caption: '自动禁用或已过期，需要处理。' },
  { label: '限流账号', value: '0', caption: '触发 429 限流，冷却中。' },
])

const trendData = ref<number[]>([])
const trendFailureData = ref<number[]>([])
const trendLabels = ref<string[]>([])
const trendModelRequests = ref<Record<string, number[]>>({})

const trendChartRef = ref<HTMLDivElement | null>(null)
const modelChartRef = ref<HTMLDivElement | null>(null)
let trendChart: ChartInstance | null = null
let modelChart: ChartInstance | null = null

const accountBreakdown = computed(() => {
  const total = Math.max(Number(stats.value[0].value), 1)
  const active = Number(stats.value[1].value)
  const failed = Number(stats.value[2].value)
  const rateLimited = Number(stats.value[3].value)
  const available = Math.max(total - active - failed - rateLimited, 0)

  return [
    {
      label: '活跃',
      value: active,
      percent: Math.round((active / total) * 100),
      barClass: 'bg-emerald-500',
    },
    {
      label: '失败',
      value: failed,
      percent: Math.round((failed / total) * 100),
      barClass: 'bg-destructive',
    },
    {
      label: '限流',
      value: rateLimited,
      percent: Math.round((rateLimited / total) * 100),
      barClass: 'bg-amber-300',
    },
    {
      label: '空闲',
      tooltip: '未限流、未失败、未激活使用中的账号（主要是手动禁用）。',
      value: available,
      percent: Math.round((available / total) * 100),
      barClass: 'bg-slate-300',
    },
  ]
})

onMounted(async () => {
  await loadOverview()
  initTrendChart()
  initModelChart()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
  if (modelChart) {
    modelChart.dispose()
    modelChart = null
  }
})

function initTrendChart() {
  const echarts = (window as any).echarts as { init: (el: HTMLElement) => ChartInstance } | undefined
  if (!echarts || !trendChartRef.value) return

  trendChart = echarts.init(trendChartRef.value)
  updateTrendChart()
  scheduleTrendResize()
}

function initModelChart() {
  const echarts = (window as any).echarts as { init: (el: HTMLElement) => ChartInstance } | undefined
  if (!echarts || !modelChartRef.value) return

  modelChart = echarts.init(modelChartRef.value)
  updateModelChart()
  scheduleModelResize()
}

function updateTrendChart() {
  if (!trendChart) return

  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['总请求', '失败/限流'],
      right: 0,
      top: 0,
      textStyle: { color: '#6b6b6b', fontSize: 11 },
    },
    grid: { left: 24, right: 16, top: 44, bottom: 24, containLabel: true },
    xAxis: {
      type: 'category',
      data: trendLabels.value,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#d4d4d4' } },
      axisTick: { show: false },
      axisLabel: { color: '#6b6b6b', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#6b6b6b', fontSize: 10 },
      splitLine: { lineStyle: { color: '#e5e5e5' } },
    },
    series: [
      {
        name: '总请求',
        type: 'line',
        data: trendData.value,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 3 },
        itemStyle: { color: '#0ea5e9' },
      },
      {
        name: '失败/限流',
        type: 'line',
        data: trendFailureData.value,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#f59e0b' },
      },
    ],
  })
  scheduleTrendResize()
}

function updateModelChart() {
  if (!modelChart) return

  const modelSeries = Object.entries(trendModelRequests.value).map(([model, data]) => ({
    name: model,
    type: 'line',
    stack: 'models',
    data,
    smooth: true,
    showSymbol: false,
    areaStyle: { opacity: 0.2 },
    lineStyle: { width: 1.5 },
    itemStyle: { color: getModelColor(model) },
  }))

  modelChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: {
      data: modelSeries.map(series => series.name),
      right: 0,
      top: 0,
      textStyle: { color: '#6b6b6b', fontSize: 11 },
    },
    grid: { left: 24, right: 16, top: 44, bottom: 24, containLabel: true },
    xAxis: {
      type: 'category',
      data: trendLabels.value,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#d4d4d4' } },
      axisTick: { show: false },
      axisLabel: { color: '#6b6b6b', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#6b6b6b', fontSize: 10 },
      splitLine: { lineStyle: { color: '#e5e5e5' } },
    },
    series: modelSeries,
  })
  scheduleModelResize()
}

function handleResize() {
  if (trendChart) {
    trendChart.resize()
  }
  if (modelChart) {
    modelChart.resize()
  }
}

async function loadOverview() {
  try {
    const overview = await statsApi.overview()
    stats.value[0].value = (overview.total_accounts ?? 0).toString()
    stats.value[1].value = (overview.active_accounts ?? 0).toString()
    stats.value[2].value = (overview.failed_accounts ?? 0).toString()
    stats.value[3].value = (overview.rate_limited_accounts ?? 0).toString()

    const trend = overview.trend || { labels: [], total_requests: [], failed_requests: [], rate_limited_requests: [] }
    trendLabels.value = trend.labels || []
    trendData.value = trend.total_requests || []
    const failed = trend.failed_requests || []
    const limited = trend.rate_limited_requests || []
    trendFailureData.value = trendData.value.map((_, idx) => (failed[idx] || 0) + (limited[idx] || 0))
    trendModelRequests.value = trend.model_requests || {}

    updateTrendChart()
    updateModelChart()
  } catch (error) {
    console.error('Failed to load overview:', error)
  }
}

function scheduleTrendResize() {
  if (!trendChart) return
  requestAnimationFrame(() => {
    trendChart?.resize()
  })
}

function scheduleModelResize() {
  if (!modelChart) return
  requestAnimationFrame(() => {
    modelChart?.resize()
  })
}

function getModelColor(model: string) {
  const modelColors: Record<string, string> = {
    'gemini-3-pro-preview': '#2563eb',
    'gemini-2.5-pro': '#10b981',
    'gemini-2.5-flash': '#f97316',
    'gemini-3-flash-preview': '#8b5cf6',
    'gemini-auto': '#64748b',
  }
  return modelColors[model] || '#94a3b8'
}
</script>

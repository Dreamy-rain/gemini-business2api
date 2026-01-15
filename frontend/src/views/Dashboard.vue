<template>
  <div class="space-y-8">
    <section class="grid grid-cols-2 gap-4 md:grid-cols-2 xl:grid-cols-4">
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
        <div ref="trendChartRef" class="mt-6 h-64 w-full max-w-full lg:h-72"></div>
        <div class="mt-4 border-t border-border pt-4">
          <p class="text-sm font-medium text-foreground">模型调用分布（近12小时）</p>
          <div ref="modelChartRef" class="mt-4 h-80 w-full max-w-full lg:h-64"></div>
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
const trendSuccessData = ref<number[]>([])
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

  const successColor = '#0ea5e9'
  const failureColor = '#f59e0b'
  const failureLineColor = '#ef4444'

  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['成功(总请求)', '失败/限流'],
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
        name: '成功(总请求)',
        type: 'line',
        data: trendSuccessData.value,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.25 },
        itemStyle: { color: successColor },
        emphasis: { disabled: true },
        z: 1,
      },
      {
        name: '失败/限流',
        type: 'line',
        data: trendFailureData.value,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.4 },
        itemStyle: { color: failureLineColor },
        emphasis: { disabled: true },
        z: 2,
      },
    ],
  })
  scheduleTrendResize()
}

function updateModelChart() {
  if (!modelChart) return

  const modelTotals = Object.entries(trendModelRequests.value)
    .map(([model, data]) => ({
      name: model,
      value: data.reduce((sum, item) => sum + item, 0),
      itemStyle: { color: getModelColor(model), borderRadius: 8 },
    }))
    .filter(item => item.value > 0)

  // 响应式布局：手机端标签在底部，桌面端标签在左侧
  const isMobile = window.innerWidth < 768
  const legendConfig = isMobile
    ? {
        data: modelTotals.map(item => item.name),
        left: 'center',
        bottom: 0,
        orient: 'horizontal' as const,
        textStyle: { color: '#6b6b6b', fontSize: 11 },
      }
    : {
        data: modelTotals.map(item => item.name),
        left: 0,
        top: 'center',
        orient: 'vertical' as const,
        textStyle: { color: '#6b6b6b', fontSize: 11 },
      }

  const pieCenter = isMobile ? ['50%', '38%'] : ['66%', '50%']
  const pieRadius = isMobile ? ['40%', '62%'] : ['52%', '78%']

  modelChart.setOption({
    animation: true,
    animationDuration: 600,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 300,
    animationEasingUpdate: 'cubicOut',
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string; value: number; percent: number }) =>
        `${params.name}: ${params.value} 次 (${params.percent}%)`,
    },
    legend: legendConfig,
    series: [
      {
        type: 'pie',
        radius: pieRadius,
        center: pieCenter,
        startAngle: 90,
        animationType: 'scale',
        animationEasing: 'cubicOut',
        avoidLabelOverlap: true,
        label: { show: true, formatter: '{b}', fontSize: 11, color: '#6b6b6b' },
        labelLine: { length: 12, length2: 10 },
        itemStyle: { borderWidth: 2, borderColor: '#fff', borderRadius: 10 },
        data: modelTotals,
      },
    ],
  })
  scheduleModelResize()
}

function handleResize() {
  if (trendChart) {
    trendChart.resize()
  }
  if (modelChart) {
    // 重新渲染图表以应用响应式布局
    updateModelChart()
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
    const failureSeries = trendData.value.map((_, idx) => (failed[idx] || 0) + (limited[idx] || 0))
    trendFailureData.value = failureSeries
    trendSuccessData.value = trendData.value.map(item => Math.max(item, 0))
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
    'gemini-3-pro-preview': '#0ea5e9',
    'gemini-2.5-pro': '#22c55e',
    'gemini-2.5-flash': '#f59e0b',
    'gemini-3-flash-preview': '#ec4899',
    'gemini-auto': '#64748b',
  }
  return modelColors[model] || '#94a3b8'
}
</script>

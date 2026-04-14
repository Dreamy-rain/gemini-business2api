<template>
  <div class="space-y-5">
    <section class="grid grid-cols-2 gap-3 md:grid-cols-2 xl:grid-cols-4">
      <StatCard
        v-for="stat in stats"
        :key="stat.label"
        size="sm"
        :label="stat.label"
        :value="stat.value"
        :caption="stat.caption"
        :icon="stat.icon"
        :icon-bg="stat.iconBg"
        :icon-color="stat.iconColor"
        root-class="dashboard-stat-card !rounded-3xl !p-4"
      />
    </section>

    <section class="grid grid-cols-1 gap-4">
      <ChartCard title="模型请求分布" size="sm" root-class="dashboard-chart-card !rounded-3xl !p-5">
        <template #actions>
          <SegmentedTabs v-model="timeRangeHourlyRequests" :options="timeRanges" aria-label="模型请求分布时间范围" />
        </template>
        <div ref="hourlyRequestsChartRef" class="h-72 w-full px-2"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4">
      <ChartCard title="调用趋势" size="sm" root-class="dashboard-chart-card !rounded-3xl !p-5">
        <template #actions>
          <SegmentedTabs v-model="timeRangeTrend" :options="timeRanges" aria-label="调用趋势时间范围" />
        </template>
        <div ref="trendChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="成功率趋势" size="sm" root-class="dashboard-chart-card !rounded-3xl !p-5">
        <template #actions>
          <SegmentedTabs v-model="timeRangeSuccessRate" :options="timeRanges" aria-label="成功率趋势时间范围" />
        </template>
        <div ref="successRateChartRef" class="h-56 w-full"></div>
      </ChartCard>

      <ChartCard title="平均响应时间" size="sm" root-class="dashboard-chart-card !rounded-3xl !p-5">
        <template #actions>
          <SegmentedTabs v-model="timeRangeResponseTime" :options="timeRanges" aria-label="平均响应时间范围" />
        </template>
        <div ref="responseTimeChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="模型调用占比" size="sm" root-class="dashboard-chart-card !rounded-3xl !p-5">
        <template #actions>
          <SegmentedTabs v-model="timeRangeModel" :options="timeRanges" aria-label="模型调用占比时间范围" />
        </template>
        <div ref="modelChartRef" class="h-56 w-full"></div>
      </ChartCard>

      <ChartCard title="模型使用排行" size="sm" root-class="dashboard-chart-card !rounded-3xl !p-5">
        <template #actions>
          <SegmentedTabs v-model="timeRangeModelRank" :options="timeRanges" aria-label="模型使用排行时间范围" />
        </template>
        <div ref="modelRankChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ChartCard, SegmentedTabs, StatCard } from 'nanocat-ui'
import { useDashboardPage } from './dashboard/useDashboardPage'

const {
  stats,
  timeRanges,
  timeRangeHourlyRequests,
  timeRangeTrend,
  timeRangeSuccessRate,
  timeRangeModel,
  timeRangeModelRank,
  timeRangeResponseTime,
  hourlyRequestsChartRef,
  trendChartRef,
  successRateChartRef,
  responseTimeChartRef,
  modelChartRef,
  modelRankChartRef,
} = useDashboardPage()
</script>

<style scoped>
:deep(.dashboard-chart-card > div:first-child) {
  margin-bottom: 1rem;
  padding-bottom: 0;
  border-bottom-width: 0;
}

:deep(.dashboard-chart-card .ui-card-title) {
  font-size: 0.875rem;
  font-weight: 500;
}

:deep(.dashboard-chart-card .ui-card-description) {
  margin-top: 0.25rem;
  font-size: 0.75rem;
  line-height: 1rem;
}
</style>

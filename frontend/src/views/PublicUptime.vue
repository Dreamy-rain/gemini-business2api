<template>
  <div class="min-h-screen overflow-x-hidden bg-card/70 text-foreground backdrop-blur">
    <div class="mx-auto flex min-h-screen w-full max-w-5xl min-w-0 items-center justify-center px-4 py-8">
      <section class="w-full rounded-3xl border border-border bg-card p-6">
        <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-sm font-medium text-foreground">服务状态</p>
          </div>
          <p class="text-xs text-muted-foreground">最近更新：{{ updatedAt || '未获取' }}</p>
        </div>

        <div
          v-if="errorMessage"
          class="mb-4 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
        >
          {{ errorMessage }}
        </div>

        <div class="grid gap-8 md:grid-cols-2">
          <div v-for="service in services" :key="service.key" class="monitor-card">
            <div class="monitor-card__header">
              <span class="monitor-card__name">{{ service.name }}</span>
              <span class="monitor-card__badge" :class="service.statusClass">
                {{ service.statusLabel }}
              </span>
            </div>
            <div class="monitor-card__stats">
              <span>可用率 <span class="monitor-card__value">{{ service.uptime }}%</span></span>
              <span>请求 <span class="monitor-card__value">{{ service.total }}</span></span>
              <span>成功 <span class="monitor-card__value">{{ service.success }}</span></span>
            </div>
            <div class="monitor-card__beats">
              <div
                v-for="(beat, index) in service.beats"
                :key="`${service.key}-${index}`"
                class="monitor-beat"
                :class="beat.className"
              >
                <span v-if="beat.tooltip" class="monitor-beat__tooltip">{{ beat.tooltip }}</span>
              </div>
            </div>
          </div>
          <div v-if="!services.length && !errorMessage" class="rounded-2xl border border-border bg-card p-4 text-xs text-muted-foreground">
            暂无监控数据。
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useUptimeStatus } from '@/composables/useUptimeStatus'

const { services, updatedAt, errorMessage, refreshStatus } = useUptimeStatus()

onMounted(() => {
  refreshStatus()
})
</script>

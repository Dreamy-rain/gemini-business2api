<template>
  <div class="space-y-6">
    <section class="rounded-3xl border border-border bg-card p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-base font-semibold text-foreground">服务状态</p>
          <p class="mt-1 text-xs text-muted-foreground">
            最近更新：{{ updatedAt || '未获取' }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <a
            href="/#/public/uptime"
            target="_blank"
            class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                   hover:border-primary hover:text-primary"
          >
            打开监控页
          </a>
        </div>
      </div>

      <div
        v-if="errorMessage"
        class="mt-4 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
      >
        {{ errorMessage }}
      </div>

      <div class="mt-6 grid gap-8 md:grid-cols-2">
        <div
          v-for="service in services"
          :key="service.key"
          class="monitor-card"
        >
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
      </div>
    </section>
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

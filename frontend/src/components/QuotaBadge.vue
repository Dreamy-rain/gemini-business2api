<template>
  <span
    ref="triggerRef"
    class="inline-flex cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition-colors"
    :class="badgeClass"
    @mouseenter="showTooltip"
    @mouseleave="hideTooltip"
    @click="toggleTooltip"
  >
    {{ badgeText }}
  </span>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-100"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="visible"
        class="fixed z-[9999] w-64 rounded-lg border border-border bg-card p-3 shadow-lg"
        :style="tooltipStyle"
        @mouseenter="handleTooltipEnter"
        @mouseleave="handleTooltipLeave"
      >
        <!-- 箭头 -->
        <span
          class="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 border-x-[6px] border-t-[6px] border-x-transparent border-t-border"
        ></span>
        <span
          class="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 -translate-y-px border-x-[5px] border-t-[5px] border-x-transparent border-t-card"
        ></span>

        <div class="text-xs font-medium text-foreground mb-2">配额详情</div>
        <div class="space-y-2">
          <div v-for="(status, type) in quotaStatus.quotas" :key="type" class="flex items-center justify-between text-xs">
            <span class="flex items-center gap-1.5">
              <span class="text-sm">{{ getQuotaIcon(type) }}</span>
              <span class="text-muted-foreground">{{ getQuotaName(type) }}</span>
            </span>
            <span :class="getStatusClass(status)" class="text-xs font-medium">
              {{ getStatusText(status) }}
            </span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { AccountQuotaStatus, QuotaStatus } from '@/types/api'

const props = defineProps<{
  quotaStatus: AccountQuotaStatus
}>()

const triggerRef = ref<HTMLElement | null>(null)
const visible = ref(false)
const tooltipStyle = ref<Record<string, string>>({})
let hideTimeout: ReturnType<typeof setTimeout> | null = null

const updatePosition = () => {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const offset = 8
  tooltipStyle.value = {
    left: `${rect.left + rect.width / 2}px`,
    top: `${rect.top - offset}px`,
    transform: 'translate(-50%, -100%)',
  }
}

const showTooltip = () => {
  if (hideTimeout) {
    clearTimeout(hideTimeout)
    hideTimeout = null
  }
  visible.value = true
  nextTick(() => {
    updatePosition()
  })
}

const hideTooltip = () => {
  hideTimeout = setTimeout(() => {
    visible.value = false
  }, 150)
}

const handleTooltipEnter = () => {
  if (hideTimeout) {
    clearTimeout(hideTimeout)
    hideTimeout = null
  }
}

const handleTooltipLeave = () => {
  visible.value = false
}

const toggleTooltip = () => {
  if (visible.value) {
    visible.value = false
  } else {
    showTooltip()
  }
}

const badgeClass = computed(() => {
  const { limited_count, total_count } = props.quotaStatus
  if (limited_count === 0) return 'bg-green-500/10 text-green-500'
  if (limited_count === total_count) return 'bg-red-500/10 text-red-500'
  return 'bg-amber-500/10 text-amber-500'
})

const badgeText = computed(() => {
  const { limited_count, total_count, quotas, is_expired } = props.quotaStatus

  if (limited_count === 0) {
    return '✓ 可用'
  }

  // 过期账户显示"已过期"
  if (is_expired && limited_count === total_count) {
    return '✗ 已过期'
  }

  if (limited_count === total_count) {
    return '✗ 全部限流'
  }

  // 部分限流：显示具体哪些受限
  const limitedTypes: string[] = []
  if (!quotas.text.available) limitedTypes.push('💬')
  if (!quotas.images.available) limitedTypes.push('🎨')
  if (!quotas.videos.available) limitedTypes.push('🎬')

  return limitedTypes.join(' ') + ' 限流'
})

const getQuotaIcon = (type: string) => {
  const icons: Record<string, string> = { text: '💬', images: '🎨', videos: '🎬' }
  return icons[type] || '❓'
}

const getQuotaName = (type: string) => {
  const names: Record<string, string> = { text: '对话', images: '绘图', videos: '视频' }
  return names[type] || type
}

const getStatusClass = (status: QuotaStatus) => {
  if (status.available) {
    return 'text-green-500 font-medium'
  }
  // 有倒计时是限流（琥珀色），没有倒计时是过期（红色）
  return status.remaining_seconds ? 'text-amber-500 font-medium' : 'text-red-500 font-medium'
}

const getStatusText = (status: QuotaStatus) => {
  if (status.available) {
    return '✓ 正常'
  }

  // 有倒计时显示倒计时，否则显示"已过期"
  if (status.remaining_seconds) {
    return `⏳ ${formatTime(status.remaining_seconds)}`
  }

  // 过期账户（没有 remaining_seconds）
  return '✗ 已过期'
}

const formatTime = (seconds: number) => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) {
    return `${h}h ${m}m`
  }
  return `${m}m`
}
</script>

<template>
  <span
    ref="triggerRef"
    class="inline-flex"
    @mouseenter="showTooltip"
    @mouseleave="hideTooltip"
    @focusin="showTooltip"
    @focusout="hideTooltip"
  >
    <slot />
  </span>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed z-[9999] -translate-x-1/2 -translate-y-full rounded-md bg-foreground px-2 py-1 text-[10px]
             text-background shadow-lg"
      :style="tooltipStyle"
    >
      {{ text }}
      <span
        class="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 border-x-4 border-t-4
               border-x-transparent border-t-foreground"
      ></span>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'

const props = defineProps<{
  text: string
  offset?: number
}>()

const triggerRef = ref<HTMLElement | null>(null)
const visible = ref(false)
const tooltipStyle = ref<Record<string, string>>({})

const showTooltip = () => {
  visible.value = true
  nextTick(() => {
    if (!triggerRef.value) return
    const rect = triggerRef.value.getBoundingClientRect()
    const offset = props.offset ?? 8
    tooltipStyle.value = {
      left: `${rect.left + rect.width / 2}px`,
      top: `${rect.top - offset}px`,
    }
  })
}

const hideTooltip = () => {
  visible.value = false
}
</script>

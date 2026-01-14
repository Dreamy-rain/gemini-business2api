<template>
  <label class="inline-flex items-center gap-2">
    <input
      type="checkbox"
      class="sr-only peer"
      :checked="modelValue"
      :disabled="disabled"
      @change="onChange"
    />
    <span
      class="flex h-4 w-4 items-center justify-center rounded border border-border bg-background text-transparent transition-colors
             peer-checked:border-foreground peer-checked:bg-foreground peer-checked:text-white peer-disabled:opacity-50"
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 20 20"
        class="h-3.5 w-3.5"
        fill="currentColor"
      >
        <path d="M7.6 13.2 4.4 10l1.2-1.2 2 2 6-6 1.2 1.2-7.2 7.2z" />
      </svg>
    </span>
    <span v-if="$slots.default" class="text-xs text-muted-foreground">
      <slot />
    </span>
  </label>
</template>

<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const onChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.checked)
}
</script>

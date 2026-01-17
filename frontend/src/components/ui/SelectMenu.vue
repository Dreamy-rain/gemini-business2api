<template>
  <div ref="root" class="relative w-full">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 rounded-full border border-input bg-background px-4 py-2 text-sm
             text-foreground transition-colors hover:border-primary"
      @click="toggle"
    >
      <span class="truncate">{{ currentLabel }}</span>
      <svg aria-hidden="true" viewBox="0 0 20 20" class="h-4 w-4" fill="currentColor">
        <path d="M5 7l5 6 5-6H5z" />
      </svg>
    </button>
    <div
      v-if="open"
      class="absolute right-0 z-30 w-full space-y-1 rounded-2xl border border-border bg-card p-2 shadow-lg"
      :class="menuPositionClass"
    >
      <button
        v-for="option in normalizedOptions"
        :key="option.value"
        type="button"
        class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors
               hover:bg-accent"
        :class="isSelected(option.value) ? 'bg-accent text-accent-foreground' : 'text-muted-foreground'"
        @click="select(option.value)"
      >
        <span>{{ option.label }}</span>
        <span v-if="isSelected(option.value)" class="text-xs">OK</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type Option = { label: string; value: string }

const props = defineProps<{
  modelValue: string | string[]
  options: Array<string | Option>
  multiple?: boolean
  placeholder?: string
  placement?: 'up' | 'down'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | string[]): void
}>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const normalizedOptions = computed<Option[]>(() =>
  props.options.map(option =>
    typeof option === 'string' ? { label: option, value: option } : option
  )
)

const currentLabel = computed(() => {
  if (props.multiple) {
    const values = Array.isArray(props.modelValue) ? props.modelValue : []
    if (!values.length) return props.placeholder || '请选择'
    if (values.length === 1) {
      const match = normalizedOptions.value.find(option => option.value === values[0])
      return match?.label || values[0]
    }
    return `已选 ${values.length} 项`
  }

  const match = normalizedOptions.value.find(option => option.value === props.modelValue)
  return match?.label || String(props.modelValue ?? '')
})

const menuPositionClass = computed(() =>
  props.placement === 'up' ? 'bottom-full mb-2' : 'mt-2'
)

const toggle = () => {
  open.value = !open.value
}

const isSelected = (value: string) => {
  if (props.multiple) {
    return Array.isArray(props.modelValue) && props.modelValue.includes(value)
  }
  return props.modelValue === value
}

const select = (value: string) => {
  if (props.multiple) {
    const current = Array.isArray(props.modelValue) ? props.modelValue : []
    const exists = current.includes(value)
    const next = exists ? current.filter(item => item !== value) : [...current, value]
    emit('update:modelValue', next)
    return
  }

  emit('update:modelValue', value)
  open.value = false
}

const handleClickOutside = (event: MouseEvent) => {
  if (!root.value) return
  if (root.value.contains(event.target as Node)) return
  open.value = false
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

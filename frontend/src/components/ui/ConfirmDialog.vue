<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4"
      @click.self="$emit('cancel')"
    >
      <div class="w-full max-w-sm rounded-3xl border border-border bg-card p-6 shadow-2xl">
        <p class="text-sm font-semibold text-foreground">{{ title }}</p>
        <p class="mt-2 text-sm text-muted-foreground">{{ message }}</p>
        <div class="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                   hover:border-foreground hover:text-foreground"
            @click="$emit('cancel')"
          >
            {{ cancelText }}
          </button>
          <button
            type="button"
            class="rounded-full bg-primary px-4 py-2 text-sm text-primary-foreground transition-opacity
                   hover:opacity-90"
            @click="$emit('confirm')"
          >
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
defineProps<{
  open: boolean
  title: string
  message: string
  confirmText: string
  cancelText: string
}>()

defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()
</script>

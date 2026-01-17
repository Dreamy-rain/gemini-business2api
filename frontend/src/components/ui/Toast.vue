<template>
  <Teleport to="body">
    <div class="fixed right-4 top-4 z-[200] flex flex-col gap-2">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="flex min-w-[320px] items-start gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-lg"
          :class="toastClass(toast.type)"
        >
          <div class="flex-shrink-0">
            <svg
              v-if="toast.type === 'success'"
              class="h-5 w-5 text-emerald-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <svg
              v-else-if="toast.type === 'error'"
              class="h-5 w-5 text-rose-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            <svg
              v-else-if="toast.type === 'warning'"
              class="h-5 w-5 text-amber-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <svg
              v-else
              class="h-5 w-5 text-sky-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div class="flex-1">
            <p v-if="toast.title" class="text-sm font-medium text-foreground">{{ toast.title }}</p>
            <p class="text-sm text-muted-foreground" :class="{ 'mt-1': toast.title }">{{ toast.message }}</p>
          </div>
          <button
            class="flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground"
            @click="removeToast(toast.id)"
          >
            <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { toastState, removeToast } from '@/composables/useToast'

const toasts = toastState.toasts

const toastClass = (type: string) => {
  switch (type) {
    case 'success':
      return 'border-emerald-200 bg-emerald-50'
    case 'error':
      return 'border-rose-200 bg-rose-50'
    case 'warning':
      return 'border-amber-200 bg-amber-50'
    default:
      return 'border-sky-200 bg-sky-50'
  }
}
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.toast-move {
  transition: transform 0.3s ease;
}
</style>

import { reactive } from 'vue'
import type { ToastItem } from 'nanocat-ui'

export const toastState = reactive<{ toasts: ToastItem[] }>({
  toasts: [],
})

let toastId = 0

export const showToast = (options: Omit<ToastItem, 'id'>) => {
  const id = `toast-${++toastId}`
  const duration = options.duration ?? 3000

  const toast: ToastItem = {
    id,
    type: options.type,
    title: options.title,
    message: options.message,
    duration,
  }

  toastState.toasts.push(toast)

  if (duration > 0) {
    setTimeout(() => {
      removeToast(id)
    }, duration)
  }

  return id
}

export const removeToast = (id: string) => {
  const index = toastState.toasts.findIndex((toast) => toast.id === id)
  if (index > -1) {
    toastState.toasts.splice(index, 1)
  }
}

export const useToast = () => ({
  success: (message: string, title?: string, duration?: number) =>
    showToast({ type: 'success', message, title, duration }),
  error: (message: string, title?: string, duration?: number) =>
    showToast({ type: 'error', message, title, duration }),
  warning: (message: string, title?: string, duration?: number) =>
    showToast({ type: 'warning', message, title, duration }),
  info: (message: string, title?: string, duration?: number) =>
    showToast({ type: 'info', message, title, duration }),
})

import { ref } from 'vue'

type ConfirmOptions = {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
}

export function useConfirmDialog() {
  const open = ref(false)
  const title = ref('确认操作')
  const message = ref('')
  const confirmText = ref('确定')
  const cancelText = ref('取消')
  let resolver: ((value: boolean) => void) | null = null

  const ask = (options: ConfirmOptions) =>
    new Promise<boolean>((resolve) => {
      title.value = options.title || '确认操作'
      message.value = options.message
      confirmText.value = options.confirmText || '确定'
      cancelText.value = options.cancelText || '取消'
      open.value = true
      resolver = resolve
    })

  const confirm = () => {
    open.value = false
    resolver?.(true)
    resolver = null
  }

  const cancel = () => {
    open.value = false
    resolver?.(false)
    resolver = null
  }

  return {
    open,
    title,
    message,
    confirmText,
    cancelText,
    ask,
    confirm,
    cancel,
  }
}

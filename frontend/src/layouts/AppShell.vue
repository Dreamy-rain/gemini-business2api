<template>
  <div class="min-h-screen">
    <div class="flex min-h-screen flex-col lg:flex-row">
      <div
        v-if="isSidebarOpen"
        class="fixed inset-0 z-30 bg-black/20 backdrop-blur-sm lg:hidden"
        @click="isSidebarOpen = false"
      ></div>
      <aside
        class="fixed inset-y-0 left-0 z-40 w-72 -translate-x-full bg-card/90 backdrop-blur-sm lg:backdrop-blur-none border-r border-border
               transition-[width,transform] duration-200 ease-out will-change-[transform] transform-gpu flex flex-col lg:static lg:translate-x-0 lg:bg-card/80
               lg:border-b-0 lg:border-r lg:sticky lg:top-0 lg:h-screen"
        :class="[
          { 'translate-x-0': isSidebarOpen, 'w-20 lg:w-20': isSidebarCollapsed },
        ]"
      >
        <div
          class="flex h-16 items-center justify-between px-6 pt-4 lg:h-20 lg:pt-5"
          :class="isSidebarCollapsed ? 'justify-center px-0' : ''"
        >
          <div class="flex items-center gap-2" :class="isSidebarCollapsed ? 'gap-0 justify-center w-full' : ''">
            <a
              href="https://github.com/Dreamy-rain/gemini-business2api"
              target="_blank"
              rel="noopener noreferrer"
              class="text-foreground transition-colors hover:text-primary"
              aria-label="GitHub"
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                class="h-6 w-6"
                fill="currentColor"
              >
                <path d="M12 2C6.477 2 2 6.477 2 12c0 4.419 2.865 8.166 6.839 9.489.5.09.682-.217.682-.483 0-.237-.009-.868-.014-1.703-2.782.604-3.369-1.341-3.369-1.341-.454-1.154-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.004.071 1.532 1.031 1.532 1.031.892 1.529 2.341 1.087 2.91.832.091-.647.349-1.087.636-1.337-2.22-.253-4.555-1.11-4.555-4.944 0-1.092.39-1.987 1.029-2.687-.103-.253-.446-1.272.098-2.65 0 0 .84-.269 2.75 1.026A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.295 2.748-1.026 2.748-1.026.546 1.378.202 2.397.1 2.65.64.7 1.028 1.595 1.028 2.687 0 3.842-2.338 4.687-4.566 4.936.359.309.678.919.678 1.852 0 1.337-.012 2.418-.012 2.747 0 .268.18.577.688.479A10.002 10.002 0 0 0 22 12c0-5.523-4.477-10-10-10z" />
              </svg>
            </a>
            <span v-if="!isSidebarCollapsed" class="text-base font-semibold text-foreground">Gemini Business2API</span>
          </div>
        </div>

        <nav
          class="pb-4 pt-4 lg:pt-6 flex-1 overflow-y-auto"
          :class="isSidebarCollapsed ? 'px-2' : 'px-3'"
        >
          <p
            v-if="!isSidebarCollapsed"
            class="px-3 pb-2 text-xs uppercase tracking-[0.28em] text-muted-foreground"
          >
            导航
          </p>
          <div class="space-y-1">
            <RouterLink
              v-for="item in menuItems"
              :key="item.path"
              :to="item.path"
              class="group flex items-center rounded-2xl py-2 text-sm font-medium transition-colors overflow-hidden"
              :class="navItemClass(item.path)"
              :title="isSidebarCollapsed ? item.label : undefined"
            >
              <span
                class="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-border"
                :class="navIconClass(item.path)"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" class="h-5 w-5" fill="currentColor">
                  <path :d="item.icon" />
                </svg>
              </span>
              <span v-if="!isSidebarCollapsed" class="flex-1 min-w-0 truncate">{{ item.label }}</span>
              <span v-if="!isSidebarCollapsed" class="ml-auto text-xs opacity-0 transition-opacity group-hover:opacity-100">
                进入
              </span>
            </RouterLink>
          </div>
        </nav>

        <div class="mt-auto border-t border-border px-6 py-3 lg:py-4">
          <div v-if="!isSidebarCollapsed" class="rounded-2xl bg-secondary/60 p-3">
            <p class="text-xs tracking-[0.12em] text-muted-foreground">
              <a
                href="https://github.com/Dreamy-rain/gemini-business2api"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex items-center gap-1 transition-colors hover:text-foreground"
              >
                gemini-business2api
              </a>
              <span> · 声明</span>
            </p>
            <p class="mt-2 text-xs text-muted-foreground">
              本项目仅限学习与研究用途，禁止用于商业用途。请保留本声明、原作者信息与开源来源。
            </p>
          </div>
          <div
            class="mt-4 flex items-center gap-3"
            :class="isSidebarCollapsed ? 'justify-center' : ''"
          >
            <button
              v-if="!isSidebarCollapsed"
              @click="handleLogout"
              class="flex-1 rounded-2xl border border-border bg-background px-4 py-3 text-sm font-medium
                     text-muted-foreground transition-colors hover:border-destructive/40 hover:text-destructive"
            >
              退出登录
            </button>
            <button
              class="h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-border text-muted-foreground transition-all
                     hover:border-primary hover:text-primary flex"
              @click="isSidebarCollapsed = !isSidebarCollapsed"
              :title="isSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                class="h-4 w-4 shrink-0"
                fill="currentColor"
              >
                <path d="M6 4h2v16H6V4zm4 4h8v2h-8V8zm0 6h8v2h-8v-2z" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      <main class="min-w-0 flex-1 overflow-hidden lg:ml-0">
        <header class="min-w-0 flex flex-col gap-4 border-b border-border bg-card/70 px-6 py-5 backdrop-blur lg:flex-row lg:items-center lg:justify-between lg:px-10">
          <div class="flex items-center gap-3">
            <button
              class="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border text-foreground transition-colors
                     hover:border-primary hover:text-primary lg:hidden"
              @click="isSidebarOpen = true"
              aria-label="打开导航"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" class="h-5 w-5" fill="currentColor">
                <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h16v2H4v-2z" />
              </svg>
            </button>
            <svg
              aria-hidden="true"
              viewBox="0 0 130 150"
              class="logo-mark h-9 w-9 shrink-0 text-foreground"
            >
              <defs>
                <filter id="head-shadow" x="-50%" y="-50%" width="200%" height="200%">
                  <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="rgba(0, 188, 212, 0.2)"/>
                </filter>
              </defs>
              <g class="logo-cat-wrapper" transform="translate(0, 12)">
                <g transform="translate(16, 20) rotate(-10, 9, 12)">
                  <path d="M14 0 L18 24 L0 24 Z" fill="#2c3e50" />
                </g>
                <g transform="translate(96, 20) rotate(10, 9, 12)">
                  <path d="M4 0 L18 24 L0 24 Z" fill="#2c3e50" />
                </g>
                <g filter="url(#head-shadow)">
                  <path d="M 32 40 L 98 40 A 12 12 0 0 1 110 52 L 110 90 A 30 30 0 0 1 80 120 L 50 120 A 30 30 0 0 1 20 90 L 20 52 A 12 12 0 0 1 32 40 Z"
                    fill="rgba(255, 255, 255, 0.9)"
                    stroke="#2c3e50"
                    stroke-width="3"
                  />
                </g>
                <rect class="logo-eye" x="35" y="68" width="14" height="4" rx="1" />
                <rect class="logo-eye" x="81" y="68" width="14" height="4" rx="1" />
              </g>
            </svg>
            <h2 class="text-xl font-semibold text-foreground lg:text-2xl">
              {{ currentPageTitle }}
            </h2>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <button
              @click="refreshPage"
              class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              title="刷新"
            >
              刷新
            </button>
            <button
              class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click="openApiInfo"
            >
              接口信息
            </button>
            <RouterLink
              to="/public/uptime"
              target="_blank"
              class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                     hover:border-primary hover:text-primary"
            >
              状态监控
            </RouterLink>
            <RouterLink
              to="/public/logs"
              target="_blank"
              class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                     hover:border-primary hover:text-primary"
            >
              公开日志
            </RouterLink>
          </div>
        </header>

        <div class="h-full overflow-y-auto overflow-x-hidden bg-card/70 px-4 pb-10 pt-6 backdrop-blur lg:px-10 lg:pt-10">
          <RouterView />
        </div>
      </main>
    </div>
    <ConfirmDialog
      :open="confirmDialog.open.value"
      :title="confirmDialog.title.value"
      :message="confirmDialog.message.value"
      :confirm-text="confirmDialog.confirmText.value"
      :cancel-text="confirmDialog.cancelText.value"
      @confirm="confirmDialog.confirm"
      @cancel="confirmDialog.cancel"
    />
    <Teleport to="body">
      <div v-if="isApiInfoOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
        <div class="w-full max-w-lg rounded-3xl border border-border bg-card p-6 shadow-xl">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-foreground">API 接口</p>
            <button
              class="text-xs text-muted-foreground transition-colors hover:text-foreground"
              @click="isApiInfoOpen = false"
            >
              关闭
            </button>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">根据客户端选择对应接口</p>

          <div class="mt-4 space-y-3 text-sm">
            <div>
              <p class="text-xs text-muted-foreground">基础端点</p>
              <div class="mt-1 flex items-start gap-2">
                <p class="min-w-0 flex-1 break-all rounded-2xl border border-border bg-background px-3 py-2 font-mono text-xs">
                  {{ apiBaseUrl }}
                </p>
                <button
                  class="shrink-0 rounded-full border border-border px-3 py-1 text-[11px] text-muted-foreground transition-colors
                         hover:border-primary hover:text-primary"
                  @click="copyText(apiBaseUrl)"
                >
                  复制
                </button>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">SDK 接口</p>
              <div class="mt-1 flex items-start gap-2">
                <p class="min-w-0 flex-1 break-all rounded-2xl border border-border bg-background px-3 py-2 font-mono text-xs">
                  {{ apiSdkUrl }}
                </p>
                <button
                  class="shrink-0 rounded-full border border-border px-3 py-1 text-[11px] text-muted-foreground transition-colors
                         hover:border-primary hover:text-primary"
                  @click="copyText(apiSdkUrl)"
                >
                  复制
                </button>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">完整接口</p>
              <div class="mt-1 flex items-start gap-2">
                <p class="min-w-0 flex-1 break-all rounded-2xl border border-border bg-background px-3 py-2 font-mono text-xs">
                  {{ apiFullUrl }}
                </p>
                <button
                  class="shrink-0 rounded-full border border-border px-3 py-1 text-[11px] text-muted-foreground transition-colors
                         hover:border-primary hover:text-primary"
                  @click="copyText(apiFullUrl)"
                >
                  复制
                </button>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">支持模型</p>
              <div class="mt-1 rounded-2xl border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                <div class="flex flex-wrap gap-2 text-foreground">
                  <span
                    v-for="model in supportedModels"
                    :key="model"
                    class="rounded-full border border-border px-2 py-0.5 text-[11px]"
                  >
                    {{ model }}
                  </span>
                </div>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">API 密钥</p>
              <div class="mt-1 flex items-start gap-2">
                <p class="min-w-0 flex-1 rounded-2xl border border-border bg-background px-3 py-2 font-mono text-xs">
                  {{ apiKeyDisplay }}
                </p>
                <button
                  class="shrink-0 rounded-full border border-border px-3 py-1 text-[11px] text-muted-foreground transition-colors
                         hover:border-primary hover:text-primary"
                  @click="copyText(apiKeyDisplay)"
                >
                  复制
                </button>
              </div>
            </div>
          </div>

          <div class="mt-6 flex items-center justify-end">
            <button
              class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                     hover:opacity-90"
              @click="isApiInfoOpen = false"
            >
              知道了
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const isSidebarOpen = ref(false)
const isSidebarCollapsed = ref(false)
const confirmDialog = useConfirmDialog()
const isApiInfoOpen = ref(false)

const menuItems = [
  {
    path: '/',
    label: '概览',
    icon: 'M4 4h7v7H4V4zm9 0h7v4h-7V4zm0 6h7v10h-7V10zM4 13h7v7H4v-7z',
  },
  {
    path: '/accounts',
    label: '账号管理',
    icon: 'M12 12a3.5 3.5 0 1 0-3.5-3.5A3.5 3.5 0 0 0 12 12zm0 2c-4.1 0-7.5 2.2-7.5 5v1h15v-1c0-2.8-3.4-5-7.5-5z',
  },
  {
    path: '/settings',
    label: '系统设置',
    icon: 'M4 6h10v2H4V6zm12 0h4v2h-4V6zM4 11h6v2H4v-2zm8 0h8v2h-8v-2zM4 16h10v2H4v-2zm12 0h4v2h-4v-2z',
  },
  {
    path: '/monitor',
    label: '监控状态',
    icon: 'M3 12h4l2-4 4 8 3-6h5v2h-4l-4 8-4-8-2 4H3v-2z',
  },
          {
            path: '/logs',
            label: '运行日志',
            icon: 'M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z',
          },
          {
            path: '/docs',
            label: '文档中心',
            icon: 'M6 3h9l4 4v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm8 1.5V8h3.5L14 4.5zM8 11h8v2H8v-2zm0 4h8v2H8v-2z',
          },
        ]

const currentPageTitle = computed(() => {
  const item = menuItems.find(item => item.path === route.path)
  return item?.label || '概览'
})

const navItemClass = (path: string) => {
  const baseLayout = isSidebarCollapsed.value ? 'px-2 justify-center gap-0' : 'px-3 gap-3'
  const base = `transition-colors ${baseLayout}`
  if (route.path === path) {
    return `${base} bg-primary text-primary-foreground`
  }
  return `${base} text-muted-foreground hover:bg-accent hover:text-accent-foreground`
}

const navIconClass = (path: string) => {
  if (route.path === path) {
    return 'bg-primary-foreground/15 text-primary-foreground border-primary-foreground/40'
  }
  return 'bg-secondary text-muted-foreground group-hover:text-accent-foreground'
}


const apiBaseUrl = computed(() => {
  const raw = settingsStore.settings?.basic?.base_url
    || import.meta.env.VITE_API_URL
    || window.location.origin
  return raw.replace(/\/$/, '')
})

const apiSdkUrl = computed(() => `${apiBaseUrl.value}/v1`)
const apiFullUrl = computed(() => `${apiBaseUrl.value}/v1/chat/completions`)
const apiKeyDisplay = computed(() => settingsStore.settings?.basic?.api_key || '未设置')
const supportedModels = [
  'gemini-auto',
  'gemini-2.5-flash',
  'gemini-2.5-pro',
  'gemini-3-flash-preview',
  'gemini-3-pro-preview',
  'gemini-imagen',
  'gemini-veo',
]

watch(
  () => route.path,
  () => {
    isSidebarOpen.value = false
  }
)

const storedCollapse = localStorage.getItem('sidebar-collapsed')
if (storedCollapse) {
  isSidebarCollapsed.value = storedCollapse === 'true'
}

watch(isSidebarCollapsed, (value) => {
  localStorage.setItem('sidebar-collapsed', value ? 'true' : 'false')
})

async function handleLogout() {
  const confirmed = await confirmDialog.ask({
    title: '退出登录',
    message: '确定退出管理控制台吗？',
  })
  if (!confirmed) return
  await authStore.logout()
  router.push({ name: 'login' })
}

function refreshPage() {
  window.location.reload()
}

async function openApiInfo() {
  isApiInfoOpen.value = true
  if (!settingsStore.settings && !settingsStore.isLoading) {
    await settingsStore.loadSettings()
  }
}

async function copyText(value: string) {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
  } catch (error) {
    console.error('Copy failed', error)
  }
}

</script>

<template>
  <div class="space-y-8">
    <section v-if="isLoading" class="rounded-3xl border border-border bg-card p-6 text-sm text-muted-foreground">
      正在加载设置...
    </section>

    <section v-else class="rounded-3xl border border-border bg-card p-6">
      <div class="flex items-center justify-between">
        <p class="text-base font-semibold text-foreground">配置面板</p>
        <button
          class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="isSaving || !localSettings"
          @click="handleSave"
        >
          保存设置
        </button>
      </div>

      <div v-if="errorMessage" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {{ errorMessage }}
      </div>

      <div v-if="localSettings" class="mt-6 space-y-8">
        <div class="grid gap-4 lg:grid-cols-3">
          <div class="space-y-4">
            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="text-xs uppercase tracking-[0.3em] text-muted-foreground">基础</p>
              <div class="mt-4 space-y-3">
                <label class="block text-xs text-muted-foreground">API 密钥</label>
                <input
                  v-model="localSettings.basic.api_key"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="可选"
                />
                <label class="block text-xs text-muted-foreground">基础地址</label>
                <input
                  v-model="localSettings.basic.base_url"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="自动检测或手动填写"
                />
                <label class="block text-xs text-muted-foreground">代理地址</label>
                <input
                  v-model="localSettings.basic.proxy"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="http://127.0.0.1:7890"
                />
              </div>
            </div>

            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="text-xs uppercase tracking-[0.3em] text-muted-foreground">自动注册/刷新</p>
              <div class="mt-4 space-y-3">
                <div class="grid grid-cols-2 items-center gap-x-6 gap-y-2">
                  <Checkbox v-model="localSettings.basic.duckmail_verify_ssl">
                    DuckMail SSL 校验
                  </Checkbox>
                  <div class="flex items-center justify-end gap-2">
                    <Checkbox
                      v-model="localSettings.basic.browser_headless"
                      :disabled="localSettings.basic.browser_engine === 'dp'"
                    >
                      无头浏览器
                    </Checkbox>
                    <HelpTip text="仅 UC 引擎支持无头模式。若无头注册/刷新失败，建议关闭。" />
                  </div>
                </div>
                <div class="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>浏览器引擎</span>
                  <HelpTip text="UC: 支持无头/有头，但可能失败。DP: 仅有头模式，更稳定，UC 失败时推荐使用。" />
                </div>
                <SelectMenu
                  v-model="localSettings.basic.browser_engine"
                  :options="browserEngineOptions"
                  class="w-full"
                />
                <label class="block text-xs text-muted-foreground">DuckMail API</label>
                <input
                  v-model="localSettings.basic.duckmail_base_url"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="https://api.duckmail.sbs"
                />
                <div class="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>过期刷新窗口（小时）</span>
                  <HelpTip text="当账号距离过期小于等于该值时，会触发自动登录刷新（更新 cookie/session）。" />
                </div>
                <input
                  v-model.number="localSettings.basic.refresh_window_hours"
                  type="number"
                  min="0"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                />
                <label class="block text-xs text-muted-foreground">默认注册数量</label>
                <input
                  v-model.number="localSettings.basic.register_default_count"
                  type="number"
                  min="1"
                  max="30"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                />
                <label class="block text-xs text-muted-foreground">默认注册域名（推荐）</label>
                <input
                  v-model="localSettings.basic.register_domain"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="留空则自动选择"
                />
                <label class="block text-xs text-muted-foreground">DuckMail API 密钥</label>
                <input
                  v-model="localSettings.basic.duckmail_api_key"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="dk_xxx"
                />
              </div>
            </div>

          </div>

          <div class="space-y-4">
            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="text-xs uppercase tracking-[0.3em] text-muted-foreground">重试</p>
              <div class="mt-4 grid grid-cols-2 gap-3 text-sm">
                <label class="col-span-2 text-xs text-muted-foreground">新会话尝试次数</label>
                <input v-model.number="localSettings.retry.max_new_session_tries" type="number" min="1" class="col-span-2 rounded-2xl border border-input bg-background px-3 py-2" />

                <label class="col-span-2 text-xs text-muted-foreground">请求重试次数</label>
                <input v-model.number="localSettings.retry.max_request_retries" type="number" min="0" class="col-span-2 rounded-2xl border border-input bg-background px-3 py-2" />

                <label class="col-span-2 text-xs text-muted-foreground">账号切换次数</label>
                <input v-model.number="localSettings.retry.max_account_switch_tries" type="number" min="1" class="col-span-2 rounded-2xl border border-input bg-background px-3 py-2" />

                <label class="col-span-2 text-xs text-muted-foreground">失败阈值</label>
                <input v-model.number="localSettings.retry.account_failure_threshold" type="number" min="1" class="col-span-2 rounded-2xl border border-input bg-background px-3 py-2" />

                <label class="col-span-2 text-xs text-muted-foreground">限流冷却秒数</label>
                <input v-model.number="localSettings.retry.rate_limit_cooldown_seconds" type="number" min="0" class="col-span-2 rounded-2xl border border-input bg-background px-3 py-2" />

                <label class="col-span-2 text-xs text-muted-foreground">会话缓存秒数</label>
                <input v-model.number="localSettings.retry.session_cache_ttl_seconds" type="number" min="0" class="col-span-2 rounded-2xl border border-input bg-background px-3 py-2" />

                <div class="col-span-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>自动刷新账号间隔（秒，0禁用）</span>
                  <HelpTip text="仅在数据库存储启用时生效：用于检测账号配置变化并重载列表，不会刷新 cookie。文件存储模式不会触发。" />
                </div>
                <input v-model.number="localSettings.retry.auto_refresh_accounts_seconds" type="number" min="0" max="600" class="col-span-2 rounded-2xl border border-input bg-background px-3 py-2" />
              </div>
            </div>
          </div>

          <div class="space-y-4">
            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="text-xs uppercase tracking-[0.3em] text-muted-foreground">图像生成</p>
              <div class="mt-4 space-y-3">
                <Checkbox v-model="localSettings.image_generation.enabled">
                  启用图像生成
                </Checkbox>
                <label class="block text-xs text-muted-foreground">输出格式</label>
                <SelectMenu
                  v-model="localSettings.image_generation.output_format"
                  :options="imageOutputOptions"
                  placement="up"
                  class="w-full"
                />
                <label class="block text-xs text-muted-foreground">支持模型</label>
                <SelectMenu
                  v-model="localSettings.image_generation.supported_models"
                  :options="imageModelOptions"
                  placeholder="选择模型"
                  placement="up"
                  multiple
                  class="w-full"
                />
              </div>
            </div>

            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="text-xs uppercase tracking-[0.3em] text-muted-foreground">公开展示</p>
              <div class="mt-4 space-y-3">
                <label class="block text-xs text-muted-foreground">Logo 地址</label>
                <input
                  v-model="localSettings.public_display.logo_url"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="logo 地址"
                />
                <label class="block text-xs text-muted-foreground">聊天入口</label>
                <input
                  v-model="localSettings.public_display.chat_url"
                  type="text"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                  placeholder="聊天入口地址"
                />
                <label class="block text-xs text-muted-foreground">会话有效时长</label>
                <input
                  v-model.number="localSettings.session.expire_hours"
                  type="number"
                  min="1"
                  class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="text-xs uppercase tracking-[0.3em] text-muted-foreground">说明</p>
              <p class="mt-4 text-sm text-muted-foreground">
                保存后会直接写入配置文件并热更新。修改后请关注日志面板确认是否生效。
              </p>
              <p class="mt-3 text-sm text-muted-foreground">
                自动注册/刷新默认启用，若依赖缺失会自动降级并提示。
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useSettingsStore } from '@/stores'
import { useToast } from '@/composables/useToast'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import HelpTip from '@/components/ui/HelpTip.vue'
import type { Settings } from '@/types/api'

const settingsStore = useSettingsStore()
const { settings, isLoading } = storeToRefs(settingsStore)
const toast = useToast()

const localSettings = ref<Settings | null>(null)
const isSaving = ref(false)
const errorMessage = ref('')
const browserEngineOptions = [
  { label: 'UC - 支持无头/有头', value: 'uc' },
  { label: 'DP - 有头模式（推荐）', value: 'dp' },
]
const imageOutputOptions = [
  { label: 'Base64 编码', value: 'base64' },
  { label: 'URL 链接', value: 'url' },
]
const imageModelOptions = computed(() => {
  const baseOptions = [
    { label: 'Gemini 3 Pro Preview', value: 'gemini-3-pro-preview' },
    { label: 'Gemini 3 Flash Preview', value: 'gemini-3-flash-preview' },
    { label: 'Gemini 2.5 Pro', value: 'gemini-2.5-pro' },
    { label: 'Gemini 2.5 Flash', value: 'gemini-2.5-flash' },
    { label: 'Gemini Auto', value: 'gemini-auto' },
  ]

  const selected = localSettings.value?.image_generation.supported_models || []
  for (const value of selected) {
    if (!baseOptions.some(option => option.value === value)) {
      baseOptions.push({ label: value, value })
    }
  }

  return baseOptions
})

watch(settings, (value) => {
  if (!value) return
  const next = JSON.parse(JSON.stringify(value))
  next.image_generation = next.image_generation || { enabled: false, supported_models: [], output_format: 'base64' }
  next.image_generation.output_format ||= 'base64'
  next.basic = next.basic || {}
  next.basic.duckmail_base_url ||= 'https://api.duckmail.sbs'
  next.basic.duckmail_verify_ssl = next.basic.duckmail_verify_ssl ?? true
  next.basic.browser_engine = next.basic.browser_engine || 'dp'
  next.basic.browser_headless = next.basic.browser_headless ?? false
  next.basic.refresh_window_hours = Number.isFinite(next.basic.refresh_window_hours)
    ? next.basic.refresh_window_hours
    : 1
  next.basic.register_default_count = Number.isFinite(next.basic.register_default_count)
    ? next.basic.register_default_count
    : 1
  next.basic.register_domain = typeof next.basic.register_domain === 'string'
    ? next.basic.register_domain
    : ''
  next.basic.duckmail_api_key = typeof next.basic.duckmail_api_key === 'string'
    ? next.basic.duckmail_api_key
    : ''
  next.retry = next.retry || {}
  next.retry.auto_refresh_accounts_seconds = Number.isFinite(next.retry.auto_refresh_accounts_seconds)
    ? next.retry.auto_refresh_accounts_seconds
    : 60
  localSettings.value = next
})

onMounted(async () => {
  await settingsStore.loadSettings()
})

const handleSave = async () => {
  if (!localSettings.value) return
  errorMessage.value = ''
  isSaving.value = true

  try {
    await settingsStore.updateSettings(localSettings.value)
    toast.success('设置保存成功')
  } catch (error: any) {
    errorMessage.value = error.message || '保存失败'
    toast.error(error.message || '保存失败')
  } finally {
    isSaving.value = false
  }
}
</script>

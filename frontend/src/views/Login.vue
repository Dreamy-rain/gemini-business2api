<template>
  <div class="min-h-screen px-4">
    <div class="flex min-h-screen items-center justify-center">
      <div class="w-full max-w-md rounded-[2.5rem] border border-border bg-card p-10 shadow-2xl shadow-black/10">
        <div class="text-center">
          <h1 class="text-3xl font-semibold text-foreground">Gemini Business 2API</h1>
          <p class="mt-2 text-sm text-muted-foreground">管理员登录</p>
        </div>

        <form @submit.prevent="handleLogin" class="mt-8 space-y-6">
          <div class="space-y-2">
            <label for="password" class="block text-sm font-medium text-foreground">
              管理员密钥
            </label>
            <input
              id="password"
              v-model="password"
              type="password"
              required
              class="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm
                     focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent
                     transition-all"
              placeholder="请输入管理员密钥"
              :disabled="isLoading"
            />
          </div>

          <div v-if="errorMessage" class="rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {{ errorMessage }}
          </div>

          <Checkbox v-model="agreedToDisclaimer" @update:modelValue="handleCheckboxChange">
            我已阅读并同意使用声明与免责条款
          </Checkbox>

          <button
            type="submit"
            :disabled="isLoading || !password || !agreedToDisclaimer"
            class="w-full rounded-2xl bg-primary py-3 text-sm font-medium text-primary-foreground
                   transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {{ isLoading ? '登录中...' : '登录' }}
          </button>
        </form>

        <div class="mt-8 flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <a
            href="https://github.com/Dreamy-rain/gemini-business2api"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-2 transition-colors hover:text-foreground"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              class="h-4 w-4"
              fill="currentColor"
            >
              <path d="M12 2C6.477 2 2 6.477 2 12c0 4.419 2.865 8.166 6.839 9.489.5.09.682-.217.682-.483 0-.237-.009-.868-.014-1.703-2.782.604-3.369-1.341-3.369-1.341-.454-1.154-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.004.071 1.532 1.031 1.532 1.031.892 1.529 2.341 1.087 2.91.832.091-.647.349-1.087.636-1.337-2.22-.253-4.555-1.11-4.555-4.944 0-1.092.39-1.987 1.029-2.687-.103-.253-.446-1.272.098-2.65 0 0 .84-.269 2.75 1.026A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.295 2.748-1.026 2.748-1.026.546 1.378.202 2.397.1 2.65.64.7 1.028 1.595 1.028 2.687 0 3.842-2.338 4.687-4.566 4.936.359.309.678.919.678 1.852 0 1.337-.012 2.418-.012 2.747 0 .268.18.577.688.479A10.002 10.002 0 0 0 22 12c0-5.523-4.477-10-10-10z" />
            </svg>
            GitHub
          </a>
          <span>Powered by Gemini Business API</span>
        </div>
      </div>
    </div>

    <!-- 免责声明弹窗 -->
    <Teleport to="body">
      <div
        v-if="showDisclaimer"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        @click.self="showDisclaimer = false"
      >
          <div class="relative max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-3xl border border-border bg-card shadow-2xl">
            <div class="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-card px-6 py-4">
              <h2 class="text-lg font-semibold text-foreground">使用声明与免责条款</h2>
              <button
                type="button"
                @click="showDisclaimer = false"
                class="rounded-full p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="overflow-y-auto p-6" style="max-height: calc(90vh - 140px)">
              <div class="space-y-4 text-sm leading-relaxed">
                <div class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3">
                  <p class="font-bold text-rose-600">⚠️ 严禁滥用：禁止将本工具用于商业用途或任何形式的滥用（无论规模大小）</p>
                </div>

                <div class="space-y-2">
                  <p class="font-semibold text-foreground">本工具严禁用于以下行为：</p>
                  <ul class="list-disc space-y-1 pl-6 text-muted-foreground">
                    <li>商业用途或盈利性使用</li>
                    <li>任何形式的批量操作或自动化滥用（无论规模大小）</li>
                    <li>破坏市场秩序或恶意竞争</li>
                    <li>违反 Google 服务条款的任何行为</li>
                    <li>违反 Microsoft 服务条款的任何行为</li>
                  </ul>
                  <p class="mt-2 text-muted-foreground"><strong class="text-foreground">违规后果：</strong>滥用行为可能导致账号永久封禁、法律追责，一切后果由使用者自行承担。</p>
                </div>

                <div class="space-y-2">
                  <p class="font-semibold text-foreground">📖 合法用途</p>
                  <p class="text-muted-foreground">本项目仅限于以下场景：</p>
                  <ul class="list-disc space-y-1 pl-6 text-muted-foreground">
                    <li>个人学习与技术研究</li>
                    <li>浏览器自动化技术探索</li>
                    <li>非商业性技术交流</li>
                  </ul>
                </div>

                <div class="space-y-2">
                  <p class="font-semibold text-foreground">⚖️ 法律责任</p>
                  <ol class="list-decimal space-y-1 pl-6 text-muted-foreground">
                    <li><strong class="text-foreground">使用者责任：</strong>使用本工具产生的一切后果（包括但不限于账号封禁、数据损失、法律纠纷）由使用者完全承担</li>
                    <li><strong class="text-foreground">合规义务：</strong>使用者必须遵守所在地法律法规及第三方服务条款（包括但不限于 Google Workspace、Microsoft 365 等服务条款）</li>
                    <li><strong class="text-foreground">作者免责：</strong>作者不对任何违规使用、滥用行为或由此产生的后果承担责任</li>
                  </ol>
                </div>

                <div class="space-y-2">
                  <p class="font-semibold text-foreground">📋 技术声明</p>
                  <ul class="list-disc space-y-1 pl-6 text-muted-foreground">
                    <li><strong class="text-foreground">无担保：</strong>本项目按"现状"提供，不提供任何形式的担保</li>
                    <li><strong class="text-foreground">第三方依赖：</strong>依赖的第三方服务（如 DuckMail API、Microsoft Graph API 等）可用性不受作者控制</li>
                    <li><strong class="text-foreground">维护权利：</strong>作者保留随时停止维护、变更功能或关闭项目的权利</li>
                  </ul>
                </div>

                <div class="space-y-2">
                  <p class="font-semibold text-foreground">🔗 相关服务条款</p>
                  <p class="text-muted-foreground">使用本工具时，您必须同时遵守以下第三方服务的条款：</p>
                  <ul class="space-y-1 pl-6 text-muted-foreground">
                    <li>• <a href="https://policies.google.com/terms" target="_blank" class="text-primary hover:underline">Google 服务条款</a></li>
                    <li>• <a href="https://workspace.google.com/terms/service-terms.html" target="_blank" class="text-primary hover:underline">Google Workspace 附加条款</a></li>
                    <li>• <a href="https://www.microsoft.com/servicesagreement" target="_blank" class="text-primary hover:underline">Microsoft 服务协议</a></li>
                    <li>• <a href="https://www.microsoft.com/licensing/terms" target="_blank" class="text-primary hover:underline">Microsoft 365 使用条款</a></li>
                  </ul>
                </div>

                <div class="rounded-2xl border border-border bg-muted/30 px-4 py-3 text-center">
                  <p class="text-xs text-muted-foreground mb-2">使用本工具即表示您已阅读、理解并同意遵守以上所有条款。</p>
                  <p class="text-xs text-muted-foreground">完整声明请查看 <a href="https://github.com/Dreamy-rain/gemini-business2api/blob/main/docs/DISCLAIMER.md" target="_blank" class="text-primary hover:underline font-medium">GitHub - DISCLAIMER.md</a></p>
                </div>
              </div>
            </div>

            <div class="sticky bottom-0 border-t border-border bg-card px-6 py-4">
              <button
                type="button"
                @click="showDisclaimer = false"
                class="w-full rounded-2xl bg-primary py-3 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                我已知晓
              </button>
            </div>
          </div>
        </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Checkbox from '@/components/ui/Checkbox.vue'

const router = useRouter()
const authStore = useAuthStore()

const password = ref('')
const errorMessage = ref('')
const isLoading = ref(false)
const showDisclaimer = ref(false)
const agreedToDisclaimer = ref(false)

function handleCheckboxChange(checked: boolean) {
  if (checked) {
    showDisclaimer.value = true
  }
}

async function handleLogin() {
  if (!password.value || !agreedToDisclaimer.value) return

  errorMessage.value = ''
  isLoading.value = true

  try {
    await authStore.login(password.value)
    router.push({ name: 'dashboard' })
  } catch (error: any) {
    errorMessage.value = error.message || '登录失败，请检查密钥。'
  } finally {
    isLoading.value = false
  }
}
</script>

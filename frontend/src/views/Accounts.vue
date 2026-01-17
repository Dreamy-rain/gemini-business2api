<template>
  <div class="space-y-8">
    <section class="rounded-3xl border border-border bg-card p-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="grid w-full grid-cols-2 gap-3 sm:flex sm:w-auto sm:items-center">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索账号 ID"
            class="w-full rounded-full border border-input bg-background px-4 py-2 text-sm sm:w-48"
          />
          <SelectMenu
            v-model="statusFilter"
            :options="statusOptions"
            class="!w-full sm:!w-40"
          />
        </div>
        <div class="flex w-full flex-wrap items-center gap-3 text-xs text-muted-foreground sm:w-auto sm:flex-nowrap">
          <Checkbox :modelValue="allSelected" @update:modelValue="toggleSelectAll">
            全选
          </Checkbox>
          <span>已选 {{ selectedCount }} / {{ filteredAccounts.length }} 个账号</span>
          <div class="ml-auto flex items-center gap-2 sm:ml-0">
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary"
              :class="viewMode === 'table' ? 'bg-accent text-accent-foreground' : ''"
              @click="viewMode = 'table'"
              aria-label="列表视图"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor">
                <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h16v2H4v-2z" />
              </svg>
            </button>
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary"
              :class="viewMode === 'card' ? 'bg-accent text-accent-foreground' : ''"
              @click="viewMode = 'card'"
              aria-label="卡片视图"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor">
                <path d="M4 6h7v6H4V6zm9 0h7v6h-7V6zM4 14h7v4H4v-4zm9 0h7v4h-7v-4z" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-2">
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                 hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="isLoading"
          @click="refreshAccounts"
        >
          刷新列表
        </button>
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                 hover:border-primary hover:text-primary"
          @click="openConfigPanel"
        >
          账户配置
        </button>
        <button
          class="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors
                 hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="isRegistering"
          @click="openRegisterModal"
        >
          添加账户
        </button>
        
        <div ref="moreActionsRef" class="relative">
          <button
            class="flex items-center gap-2 rounded-full border border-input bg-background px-4 py-2 text-sm font-medium
                   text-foreground transition-colors hover:border-primary"
            :class="showMoreActions ? 'bg-accent text-accent-foreground' : ''"
            @click="toggleMoreActions"
          >
            更多操作
            <svg aria-hidden="true" viewBox="0 0 20 20" class="h-4 w-4" fill="currentColor">
              <path d="M5 7l5 6 5-6H5z" />
            </svg>
            <span
              v-if="hasTaskData"
              class="ml-1 h-2 w-2 rounded-full"
              :class="taskIndicatorClass"
              aria-hidden="true"
            ></span>
          </button>
          <div
            v-if="showMoreActions"
            class="absolute right-0 z-10 mt-2 w-full space-y-1 rounded-2xl border border-border bg-card p-2 shadow-lg"
          >
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm text-foreground transition-colors
                     hover:bg-accent"
              @click="openTaskModal(); closeMoreActions()"
            >
              任务状态
            </button>
            <div class="my-1 border-t border-border/60"></div>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="isRefreshing
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="isRefreshing"
              @click="handleRefreshExpiring(); closeMoreActions()"
            >
              刷新过期
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount || isRefreshing
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="!selectedCount || isRefreshing"
              @click="handleRefreshSelected(); closeMoreActions()"
            >
              刷新选中
            </button>
            <div class="my-1 border-t border-border/60"></div>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="!selectedCount"
              @click="handleBulkEnable(); closeMoreActions()"
            >
              批量启用
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="!selectedCount"
              @click="handleBulkDisable(); closeMoreActions()"
            >
              批量禁用
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-destructive hover:bg-destructive/10'"
              :disabled="!selectedCount"
              @click="handleBulkDelete(); closeMoreActions()"
            >
              批量删除
            </button>
          </div>
        </div>
      </div>

      <div v-if="viewMode === 'card'" class="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="account in filteredAccounts"
          :key="account.id"
          class="rounded-2xl border border-border bg-card p-4"
          :class="rowClass(account)"
          @click="toggleSelect(account.id)"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-xs text-muted-foreground">账号 ID</p>
              <p class="mt-1 font-mono text-xs text-foreground">{{ account.id }}</p>
            </div>
            <div class="flex items-center gap-2">
              <Checkbox
                :modelValue="selectedIds.has(account.id)"
                @update:modelValue="toggleSelect(account.id)"
                @click.stop
              />
              <span
                class="inline-flex items-center rounded-full border border-border px-3 py-1 text-xs"
                :class="statusClass(account)"
              >
                {{ statusLabel(account) }}
              </span>
            </div>
          </div>

          <div class="mt-4 grid grid-cols-2 gap-3 text-xs text-muted-foreground">
            <div>
              <p>剩余时间</p>
              <p class="mt-1 text-sm font-semibold" :class="remainingClass(account)">
                {{ displayRemaining(account.remaining_display) }}
              </p>
              <p v-if="account.expires_at" class="mt-1 text-[11px]">
                {{ account.expires_at }}
              </p>
            </div>
            <div>
              <p>冷却</p>
              <p class="mt-1" :class="cooldownClass(account)">
                <span v-if="account.cooldown_seconds > 0">
                  {{ formatCooldown(account.cooldown_seconds) }} · {{ account.cooldown_reason }}
                </span>
                <span v-else>
                  {{ account.cooldown_reason || '无冷却' }}
                </span>
              </p>
            </div>
            <div>
              <p>失败数</p>
              <p class="mt-1 text-sm font-semibold text-foreground">{{ account.error_count }}</p>
            </div>
            <div>
              <p>会话数</p>
              <p class="mt-1 text-sm font-semibold text-foreground">{{ account.conversation_count }}</p>
            </div>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2">
            <button
              class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click.stop="openEdit(account.id)"
            >
              编辑
            </button>
            <button
              v-if="shouldShowEnable(account)"
              class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click.stop
              @click="handleEnable(account.id)"
            >
              启用
            </button>
            <button
              v-else
              class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click.stop
              @click="handleDisable(account.id)"
            >
              禁用
            </button>
            <button
              class="rounded-full border border-border px-3 py-1 text-xs text-destructive transition-colors
                     hover:border-destructive hover:text-destructive"
              @click.stop
              @click="handleDelete(account.id)"
            >
              删除
            </button>
          </div>
        </div>
        <div v-if="!filteredAccounts.length && !isLoading" class="rounded-2xl border border-border bg-background p-4 text-center text-xs text-muted-foreground">
          暂无账号数据，请检查后台配置。
        </div>
      </div>

      <div v-else class="relative mt-6 overflow-x-auto overflow-y-visible">
        <table class="min-w-full text-left text-sm">
          <thead class="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            <tr>
              <th class="py-3 pr-4">
                <Checkbox :modelValue="allSelected" @update:modelValue="toggleSelectAll" />
              </th>
              <th class="py-3 pr-6">账号 ID</th>
              <th class="py-3 pr-6">状态</th>
              <th class="py-3 pr-6">
                <span class="inline-flex items-center gap-2">
                  剩余/过期
                  <HelpTip text="过期时间为 12 小时，账户过期以北京时间为准。" />
                </span>
              </th>
              <th class="py-3 pr-6">冷却</th>
              <th class="py-3 pr-6">失败数</th>
              <th class="py-3 pr-6">会话数</th>
              <th class="py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="text-sm text-foreground">
            <tr v-if="!filteredAccounts.length && !isLoading">
              <td colspan="8" class="py-8 text-center text-muted-foreground">
                暂无账号数据，请检查后台配置。
              </td>
            </tr>
            <tr
              v-for="account in filteredAccounts"
              :key="account.id"
              class="border-t border-border"
              :class="rowClass(account)"
              @click="toggleSelect(account.id)"
            >
              <td class="py-4 pr-4" @click.stop>
                <Checkbox
                  :modelValue="selectedIds.has(account.id)"
                  @update:modelValue="toggleSelect(account.id)"
                />
              </td>
              <td class="py-4 pr-6 font-mono text-xs text-foreground">
                {{ account.id }}
              </td>
              <td class="py-4 pr-6">
                <span
                  class="inline-flex items-center rounded-full border border-border px-3 py-1 text-xs"
                  :class="statusClass(account)"
                >
                  {{ statusLabel(account) }}
                </span>
              </td>
              <td class="py-4 pr-6">
                <div class="text-sm font-semibold" :class="remainingClass(account)">
                  {{ displayRemaining(account.remaining_display) }}
                </div>
                <span v-if="account.expires_at" class="block text-[11px] text-muted-foreground">
                  {{ account.expires_at }}
                </span>
              </td>
              <td class="py-4 pr-6 text-xs">
                <span v-if="account.cooldown_seconds > 0" :class="cooldownClass(account)">
                  {{ formatCooldown(account.cooldown_seconds) }} · {{ account.cooldown_reason }}
                </span>
                <span v-else :class="cooldownClass(account)">
                  {{ account.cooldown_reason || '无冷却' }}
                </span>
              </td>
              <td class="py-4 pr-6 text-xs text-muted-foreground">
                {{ account.error_count }}
              </td>
              <td class="py-4 pr-6 text-xs text-muted-foreground">
                {{ account.conversation_count }}
              </td>
              <td class="py-4 text-right">
                <div class="flex flex-wrap justify-end gap-2">
                  <button
                    class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                           hover:border-primary hover:text-primary"
                    @click.stop="openEdit(account.id)"
                  >
                    编辑
                  </button>
                  <button
                    v-if="shouldShowEnable(account)"
                    class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                           hover:border-primary hover:text-primary"
                    @click.stop="handleEnable(account.id)"
                  >
                    启用
                  </button>
                  <button
                    v-else
                    class="rounded-full border border-border px-3 py-1 text-xs text-foreground transition-colors
                           hover:border-primary hover:text-primary"
                    @click.stop="handleDisable(account.id)"
                  >
                    禁用
                  </button>
                  <button
                    class="rounded-full border border-border px-3 py-1 text-xs text-destructive transition-colors
                           hover:border-destructive hover:text-destructive"
                    @click.stop="handleDelete(account.id)"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
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
    <div v-if="isRegisterOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-xl">
        <div class="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <p class="text-sm font-medium text-foreground">添加账户</p>
            <p class="mt-1 text-xs text-muted-foreground">
              {{ addMode === 'register' ? '创建 DuckMail 账号并自动注册' : '批量导入账户配置' }}
            </p>
          </div>
          <button
            class="text-xs text-muted-foreground transition-colors hover:text-foreground"
            @click="closeRegisterModal"
          >
            关闭
          </button>
        </div>

        <div class="scrollbar-slim flex-1 overflow-y-auto px-6 py-4">
          <div class="space-y-4 text-sm">
          <div class="flex rounded-full border border-border bg-muted/30 p-1 text-xs">
            <button
              type="button"
              class="flex-1 rounded-full px-3 py-2 font-medium transition-colors"
              :class="addMode === 'register' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'"
              @click="addMode = 'register'"
            >
              自动注册
            </button>
            <button
              type="button"
              class="flex-1 rounded-full px-3 py-2 font-medium transition-colors"
              :class="addMode === 'import' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'"
              @click="addMode = 'import'"
            >
              批量导入
            </button>
          </div>

          <div v-if="addMode === 'register'" class="space-y-4">
            <label class="block text-xs text-muted-foreground">注册数量</label>
            <input
              v-model.number="registerCount"
              type="number"
              min="1"
              class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            />
            <div class="rounded-2xl border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <p>默认域名（可在配置面板修改，推荐使用）</p>
              <p class="mt-1">注册失败建议关闭无头浏览器再试</p>
            </div>
          </div>

          <div v-else class="space-y-4">
            <label class="block text-xs text-muted-foreground">批量导入（每行一个）</label>
            <textarea
              v-model="importText"
              class="min-h-[140px] w-full rounded-2xl border border-input bg-background px-3 py-2 text-xs font-mono"
              placeholder="duckmail----you@example.com----password&#10;user@outlook.com----loginPassword----clientId----refreshToken"
            ></textarea>
            <div class="rounded-2xl border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <p>支持两种格式：</p>
              <p class="mt-1 font-mono">duckmail----email----password</p>
              <p class="mt-1 font-mono">email----password----clientId----refreshToken</p>
              <p class="mt-2">导入后请执行一次"刷新选中"以获取 Cookie。</p>
              <p class="mt-1">注册失败建议关闭无头浏览器再试</p>
            </div>
            <div v-if="importError" class="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-600">
              {{ importError }}
            </div>
          </div>

          <div class="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] leading-relaxed">
            <p class="text-xs font-bold text-rose-600">⚠️ 严禁滥用：禁止将本工具用于商业用途或任何形式的滥用（无论规模大小）</p>
            <p class="mt-1 text-muted-foreground">详细声明请查看项目 <a href="https://github.com/Dreamy-rain/gemini-business2api/blob/main/docs/DISCLAIMER.md" target="_blank" class="text-primary hover:underline font-medium">DISCLAIMER.md</a></p>
          </div>
          <Checkbox v-model="registerAgreed">
            我已阅读并同意上述说明与限制
          </Checkbox>
          </div>
        </div>

        <div class="border-t border-border/60 px-6 py-4">
          <div class="flex items-center justify-end gap-2">
            <button
              class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click="closeRegisterModal"
            >
              取消
            </button>
            <button
              v-if="addMode === 'register'"
              class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                     hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="isRegistering || !registerAgreed"
              @click="handleRegister"
            >
              开始注册
            </button>
            <button
              v-else
              class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                     hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="isImporting || !registerAgreed"
              @click="handleImport"
            >
              导入并保存
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="isTaskOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="flex h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-xl">
        <div class="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <p class="text-sm font-medium text-foreground">任务状态</p>
            <p class="mt-1 text-xs text-muted-foreground">注册与刷新任务的状态与日志</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!registerLogs.length && !loginLogs.length && !registerTask && !loginTask && !automationError"
              @click="clearTaskLogs"
            >
              清空日志
            </button>
            <button
              class="text-xs text-muted-foreground transition-colors hover:text-foreground"
              @click="closeTaskModal"
            >
              关闭
            </button>
          </div>
        </div>
        <div class="flex min-h-0 flex-1 flex-col px-6 py-4">
          <div v-if="automationError" class="rounded-2xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {{ automationError }}
          </div>

          <div v-if="registerTask || loginTask" class="grid gap-3 text-xs text-muted-foreground">
            <div v-if="registerTask" class="space-y-1">
              <div class="flex items-center gap-2 font-medium text-foreground">
                <span
                  class="h-2.5 w-2.5 rounded-full"
                  :class="getTaskStatusIndicatorClass(registerTask)"
                  aria-hidden="true"
                ></span>
                注册任务
              </div>
              <div class="flex flex-wrap gap-x-4 gap-y-1">
                <span>状态：{{ formatTaskStatus(registerTask.status) }}</span>
                <span>进度：{{ registerTask.progress }}/{{ registerTask.count }}</span>
                <span>成功：{{ registerTask.success_count }}</span>
                <span>失败：{{ registerTask.fail_count }}</span>
              </div>
            </div>
            <div v-if="loginTask" class="space-y-1">
              <div class="flex items-center gap-2 font-medium text-foreground">
                <span
                  class="h-2.5 w-2.5 rounded-full"
                  :class="getTaskStatusIndicatorClass(loginTask)"
                  aria-hidden="true"
                ></span>
                刷新任务
              </div>
              <div class="flex flex-wrap gap-x-4 gap-y-1">
                <span>状态：{{ formatTaskStatus(loginTask.status) }}</span>
                <span>进度：{{ loginTask.progress }}/{{ loginTask.account_ids.length }}</span>
                <span>成功：{{ loginTask.success_count }}</span>
                <span>失败：{{ loginTask.fail_count }}</span>
              </div>
            </div>
          </div>

          <div
            v-if="registerLogs.length || loginLogs.length"
            class="mt-4 flex min-h-0 flex-1 flex-col"
          >
            <div
              ref="taskLogsRef"
              class="scrollbar-slim flex-1 overflow-y-auto rounded-2xl border border-border bg-muted/30 p-3"
            >
              <div v-if="registerLogs.length" class="space-y-2">
                <p class="text-xs font-semibold text-foreground">注册日志</p>
                <div class="space-y-1 text-[11px] text-muted-foreground">
                  <div v-for="(log, index) in registerLogs" :key="`reg-${index}`" class="font-mono">
                    {{ formatLogLine(log) }}
                  </div>
                </div>
              </div>
              <div v-if="loginLogs.length" class="mt-4 space-y-2">
                <p class="text-xs font-semibold text-foreground">刷新日志</p>
                <div class="space-y-1 text-[11px] text-muted-foreground">
                  <div v-for="(log, index) in loginLogs" :key="`login-${index}`" class="font-mono">
                    {{ formatLogLine(log) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div
            v-if="!automationError && !registerTask && !loginTask && !registerLogs.length && !loginLogs.length"
            class="mt-4 rounded-2xl border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
          >
            暂无任务
          </div>
        </div>
      </div>
    </div>
  </Teleport>
  <Teleport to="body">
    <div v-if="isEditOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="w-full max-w-lg rounded-3xl border border-border bg-card p-6 shadow-xl">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium text-foreground">编辑账号</p>
          <button
            class="text-xs text-muted-foreground transition-colors hover:text-foreground"
            @click="closeEdit"
          >
            关闭
          </button>
        </div>

        <div v-if="editError" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {{ editError }}
        </div>

        <div class="mt-4 space-y-3 text-sm">
          <label class="block text-xs text-muted-foreground">账号 ID</label>
          <input
            v-model="editForm.id"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            disabled
          />

          <label class="block text-xs text-muted-foreground">secure_c_ses</label>
          <textarea
            v-model="editForm.secure_c_ses"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            rows="3"
          ></textarea>

          <label class="block text-xs text-muted-foreground">csesidx</label>
          <input
            v-model="editForm.csesidx"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
          />

          <label class="block text-xs text-muted-foreground">config_id</label>
          <input
            v-model="editForm.config_id"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
          />

          <label class="block text-xs text-muted-foreground">host_c_oses</label>
          <input
            v-model="editForm.host_c_oses"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
          />

          <label class="block text-xs text-muted-foreground">expires_at</label>
          <input
            v-model="editForm.expires_at"
            type="text"
            class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            placeholder="2025-12-23 10:59:21"
          />
        </div>

        <div class="mt-6 flex items-center justify-end gap-2">
          <button
            class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                   hover:border-primary hover:text-primary"
            @click="closeEdit"
          >
            取消
          </button>
          <button
            class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                   hover:opacity-90"
            @click="saveEdit"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="isConfigOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="w-full max-w-3xl rounded-3xl border border-border bg-card p-6 shadow-xl">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium text-foreground">账户配置（JSON）</p>
          <div class="flex items-center gap-2">
            <button
              class="rounded-full bg-foreground px-3 py-1 text-xs text-background transition-opacity
                     hover:opacity-90"
              @click="toggleConfigMask"
            >
              {{ configMasked ? '显示原文' : '脱敏显示' }}
            </button>
            <button
              class="text-xs text-muted-foreground transition-colors hover:text-foreground"
              @click="closeConfigPanel"
            >
              关闭
            </button>
          </div>
        </div>

        <div v-if="configError" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {{ configError }}
        </div>

        <div class="mt-4">
          <textarea
            v-model="configJson"
            class="h-96 w-full rounded-2xl border border-input bg-background px-4 py-3 font-mono text-xs text-foreground"
            spellcheck="false"
            :readonly="configMasked"
          ></textarea>
        </div>

        <div class="mt-6 flex items-center justify-end gap-2">
          <button
            class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                   hover:border-primary hover:text-primary"
            @click="closeConfigPanel"
          >
            取消
          </button>
          <button
            class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                   hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            @click="saveConfigPanel"
            :disabled="configMasked"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAccountsStore } from '@/stores'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import HelpTip from '@/components/ui/HelpTip.vue'
import { accountsApi } from '@/api'
import type { AdminAccount, AccountConfigItem, RegisterTask, LoginTask } from '@/types/api'

const accountsStore = useAccountsStore()
const { accounts, isLoading } = storeToRefs(accountsStore)
const confirmDialog = useConfirmDialog()
const toast = useToast()

const searchQuery = ref('')
const statusFilter = ref('all')
const selectedIds = ref<Set<string>>(new Set())
const viewMode = ref<'table' | 'card'>('table')
const isEditOpen = ref(false)
const editError = ref('')
const isConfigOpen = ref(false)
const configError = ref('')
const configJson = ref('')
const configMasked = ref(false)
const configData = ref<AccountConfigItem[]>([])
const registerCount = ref(1)
const isRegisterOpen = ref(false)
const addMode = ref<'register' | 'import'>('register')
const importText = ref('')
const importError = ref('')
const isImporting = ref(false)
const isTaskOpen = ref(false)
const showMoreActions = ref(false)
const moreActionsRef = ref<HTMLDivElement | null>(null)
const lastRegisterTaskId = ref<string | null>(null)
const lastLoginTaskId = ref<string | null>(null)
const clearedRegisterTaskId = ref<string | null>(null)
const clearedLoginTaskId = ref<string | null>(null)
const registerLogClearOffset = ref(0)
const loginLogClearOffset = ref(0)
const registerAgreed = ref(false)
const registerTask = ref<RegisterTask | null>(null)
const loginTask = ref<LoginTask | null>(null)
const taskLogsRef = ref<HTMLDivElement | null>(null)
const isRegistering = ref(false)
const isRefreshing = ref(false)
const automationError = ref('')
const REGISTER_TASK_CACHE_KEY = 'accounts-register-task-cache'
const LOGIN_TASK_CACHE_KEY = 'accounts-login-task-cache'
const REGISTER_CLEAR_KEY = 'accounts-register-log-clear'
const LOGIN_CLEAR_KEY = 'accounts-login-log-clear'
const REGISTER_CLEARED_TASK_KEY = 'accounts-register-task-cleared-id'
const LOGIN_CLEARED_TASK_KEY = 'accounts-login-task-cleared-id'
const editForm = ref<AccountConfigItem>({
  id: '',
  secure_c_ses: '',
  csesidx: '',
  config_id: '',
  host_c_oses: '',
  expires_at: '',
})
const editIndex = ref<number | null>(null)
const configAccounts = ref<AccountConfigItem[]>([])
const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '正常', value: '正常' },
  { label: '即将过期', value: '即将过期' },
  { label: '已过期', value: '已过期' },
  { label: '手动禁用', value: '手动禁用' },
  { label: '错误禁用', value: '错误禁用' },
  { label: '429限流', value: '429限流' },
]

const filteredAccounts = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return accounts.value.filter(account => {
    const matchesQuery = !query || account.id.toLowerCase().includes(query)
    const matchesStatus = statusFilter.value === 'all' || statusLabel(account) === statusFilter.value
    return matchesQuery && matchesStatus
  })
})

const selectedCount = computed(() => selectedIds.value.size)
const allSelected = computed(() =>
  filteredAccounts.value.length > 0 && filteredAccounts.value.every(account => selectedIds.value.has(account.id))
)

const refreshAccounts = async () => {
  await accountsStore.loadAccounts()
  selectedIds.value = new Set()
  showMoreActions.value = false
}

const readCachedTask = <T,>(key: string): T | null => {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

const readClearedTaskId = (key: string) => {
  try {
    return localStorage.getItem(key) || null
  } catch {
    return null
  }
}

const writeClearedTaskId = (key: string, value: string | null) => {
  try {
    if (value) {
      localStorage.setItem(key, value)
      return
    }
    localStorage.removeItem(key)
  } catch {
    // ignore storage errors
  }
}

const writeCachedTask = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore storage errors
  }
}

const clearCachedTask = (key: string) => {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore storage errors
  }
}

const readClearOffset = (key: string) => {
  const raw = localStorage.getItem(key)
  const value = Number(raw)
  return Number.isFinite(value) ? value : 0
}

const writeClearOffset = (key: string, value: number) => {
  try {
    localStorage.setItem(key, String(value))
  } catch {
    // ignore storage errors
  }
}

const syncRegisterTask = (task: RegisterTask | null, persist = true) => {
  if (!task) return
  if (task.id && task.id === clearedRegisterTaskId.value) return
  if (task.id && clearedRegisterTaskId.value && task.id !== clearedRegisterTaskId.value) {
    clearedRegisterTaskId.value = null
    writeClearedTaskId(REGISTER_CLEARED_TASK_KEY, null)
  }
  registerTask.value = task
  if (task.id && task.id !== lastRegisterTaskId.value) {
    lastRegisterTaskId.value = task.id
    registerLogClearOffset.value = 0
    writeClearOffset(REGISTER_CLEAR_KEY, 0)
  }
  if (persist) {
    writeCachedTask(REGISTER_TASK_CACHE_KEY, task)
  }
}

const syncLoginTask = (task: LoginTask | null, persist = true) => {
  if (!task) return
  if (task.id && task.id === clearedLoginTaskId.value) return
  if (task.id && clearedLoginTaskId.value && task.id !== clearedLoginTaskId.value) {
    clearedLoginTaskId.value = null
    writeClearedTaskId(LOGIN_CLEARED_TASK_KEY, null)
  }
  loginTask.value = task
  if (task.id && task.id !== lastLoginTaskId.value) {
    lastLoginTaskId.value = task.id
    loginLogClearOffset.value = 0
    writeClearOffset(LOGIN_CLEAR_KEY, 0)
  }
  if (persist) {
    writeCachedTask(LOGIN_TASK_CACHE_KEY, task)
  }
}

const hydrateTaskCache = () => {
  registerLogClearOffset.value = readClearOffset(REGISTER_CLEAR_KEY)
  loginLogClearOffset.value = readClearOffset(LOGIN_CLEAR_KEY)
  clearedRegisterTaskId.value = readClearedTaskId(REGISTER_CLEARED_TASK_KEY)
  clearedLoginTaskId.value = readClearedTaskId(LOGIN_CLEARED_TASK_KEY)
  const cachedRegister = readCachedTask<RegisterTask>(REGISTER_TASK_CACHE_KEY)
  if (cachedRegister && cachedRegister.id !== clearedRegisterTaskId.value) {
    registerTask.value = cachedRegister
    lastRegisterTaskId.value = cachedRegister.id || null
  }
  const cachedLogin = readCachedTask<LoginTask>(LOGIN_TASK_CACHE_KEY)
  if (cachedLogin && cachedLogin.id !== clearedLoginTaskId.value) {
    loginTask.value = cachedLogin
    lastLoginTaskId.value = cachedLogin.id || null
  }
}

const openRegisterModal = () => {
  isRegisterOpen.value = true
  addMode.value = 'register'
  importText.value = ''
  importError.value = ''
  isImporting.value = false
  registerAgreed.value = false
}

const closeRegisterModal = () => {
  isRegisterOpen.value = false
}

const IMPORT_EXPIRES_AT = '1970-01-01 00:00:00'

const parseImportLines = (raw: string) => {
  const items: AccountConfigItem[] = []
  const errors: string[] = []
  const lines = raw.split(/\r?\n/).map(line => line.trim()).filter(Boolean)

  lines.forEach((line, index) => {
    const parts = line.split('----').map(part => part.trim())
    const lineNo = index + 1

    if (!parts.length) return

    if (parts[0].toLowerCase() === 'duckmail') {
      if (parts.length < 3 || !parts[1] || !parts[2]) {
        errors.push(`第 ${lineNo} 行格式错误（duckmail）`)
        return
      }
      const email = parts[1]
      const password = parts.slice(2).join('----')
      items.push({
        id: email,
        secure_c_ses: '',
        csesidx: '',
        config_id: '',
        expires_at: IMPORT_EXPIRES_AT,
        mail_provider: 'duckmail',
        mail_address: email,
        mail_password: password,
      })
      return
    }

    if (parts.length >= 4 && parts[0] && parts[2] && parts[3]) {
      const email = parts[0]
      const password = parts[1] || ''
      const clientId = parts[2]
      const refreshToken = parts.slice(3).join('----')
      items.push({
        id: email,
        secure_c_ses: '',
        csesidx: '',
        config_id: '',
        expires_at: IMPORT_EXPIRES_AT,
        mail_provider: 'microsoft',
        mail_address: email,
        mail_password: password,
        mail_client_id: clientId,
        mail_refresh_token: refreshToken,
        mail_tenant: 'consumers',
      })
      return
    }

    errors.push(`第 ${lineNo} 行格式错误`)
  })

  return { items, errors }
}

const handleImport = async () => {
  importError.value = ''
  if (!importText.value.trim()) {
    importError.value = '请输入导入内容'
    return
  }
  const { items, errors } = parseImportLines(importText.value)
  if (!items.length) {
    importError.value = errors.length ? errors.join('，') : '未识别到有效账号'
    return
  }
  if (errors.length) {
    importError.value = errors.slice(0, 3).join('，')
    return
  }

  isImporting.value = true
  try {
    const list = await loadConfigList()
    const next = [...list]
    const indexMap = new Map(next.map((acc, idx) => [acc.id, idx]))
    const importedIds: string[] = []

    items.forEach((item) => {
      const idx = indexMap.get(item.id || '')
      if (idx === undefined) {
        next.push(item)
        importedIds.push(item.id)
        return
      }

      const existing = next[idx]
      const updated: AccountConfigItem = {
        ...existing,
        mail_provider: item.mail_provider,
        mail_address: item.mail_address,
      }

      if (item.mail_provider === 'microsoft') {
        updated.mail_client_id = item.mail_client_id
        updated.mail_refresh_token = item.mail_refresh_token
        updated.mail_tenant = item.mail_tenant
        updated.mail_password = item.mail_password
      } else {
        updated.mail_password = item.mail_password
        updated.mail_client_id = undefined
        updated.mail_refresh_token = undefined
        updated.mail_tenant = undefined
      }

      next[idx] = updated
      importedIds.push(item.id)
    })

    await accountsStore.updateConfig(next)
    await refreshAccounts()

    selectedIds.value = new Set(importedIds)
    toast.success(`成功导入 ${importedIds.length} 个账户`)
    closeRegisterModal()

    const confirmed = await confirmDialog.ask({
      title: '导入成功',
      message: `已导入 ${importedIds.length} 个账户并自动选中。是否立即刷新这些账户以获取 Cookie？`,
      confirmText: '立即刷新',
      cancelText: '稍后手动刷新',
    })

    if (confirmed) {
      await handleRefreshSelected()
    }
  } catch (error: any) {
    importError.value = error.message || '导入失败'
    toast.error(error.message || '导入失败')
  } finally {
    isImporting.value = false
  }
}

const refreshTaskSnapshot = async () => {
  try {
    const tasks: Promise<void>[] = []
    const registerId = registerTask.value?.id
    const loginId = loginTask.value?.id

    if (registerId && !isClearedRegisterTaskId(registerId)) {
      tasks.push(updateRegisterTask(registerId))
    }
    if (loginId && !isClearedLoginTaskId(loginId)) {
      tasks.push(updateLoginTask(loginId))
    }

    if (!tasks.length) {
      await loadCurrentTasks()
      return
    }

    await Promise.all(tasks)
  } catch (error: any) {
    automationError.value = error?.message || '任务状态更新失败'
  }
}

const openTaskModal = async () => {
  isTaskOpen.value = true
  await refreshTaskSnapshot()
}

const closeTaskModal = () => {
  isTaskOpen.value = false
}

const clearTaskLogs = () => {
  const registerId = registerTask.value?.id || null
  const loginId = loginTask.value?.id || null
  clearedRegisterTaskId.value = registerId
  clearedLoginTaskId.value = loginId
  writeClearedTaskId(REGISTER_CLEARED_TASK_KEY, registerId)
  writeClearedTaskId(LOGIN_CLEARED_TASK_KEY, loginId)
  registerLogClearOffset.value = registerTask.value?.logs?.length || 0
  loginLogClearOffset.value = loginTask.value?.logs?.length || 0
  writeClearOffset(REGISTER_CLEAR_KEY, registerLogClearOffset.value)
  writeClearOffset(LOGIN_CLEAR_KEY, loginLogClearOffset.value)
  registerTask.value = null
  loginTask.value = null
  lastRegisterTaskId.value = null
  lastLoginTaskId.value = null
  automationError.value = ''
  isRegistering.value = false
  isRefreshing.value = false
  clearRegisterTimer()
  clearLoginTimer()
  clearCachedTask(REGISTER_TASK_CACHE_KEY)
  clearCachedTask(LOGIN_TASK_CACHE_KEY)
}

const isClearedRegisterTaskId = (taskId?: string | null) =>
  Boolean(taskId && taskId === clearedRegisterTaskId.value)

const isClearedLoginTaskId = (taskId?: string | null) =>
  Boolean(taskId && taskId === clearedLoginTaskId.value)

const toggleMoreActions = () => {
  showMoreActions.value = !showMoreActions.value
}

const closeMoreActions = () => {
  showMoreActions.value = false
}

const handleMoreActionsClick = (event: MouseEvent) => {
  if (!showMoreActions.value) return
  const target = event.target as Node
  if (moreActionsRef.value && !moreActionsRef.value.contains(target)) {
    showMoreActions.value = false
  }
}

onMounted(async () => {
  hydrateTaskCache()
  await refreshAccounts()
  await loadCurrentTasks()
  startBackgroundTaskPolling()
  document.addEventListener('click', handleMoreActionsClick)
})

const registerLogs = computed(() => {
  const logs = registerTask.value?.logs || []
  if (!registerLogClearOffset.value) return logs
  return logs.slice(registerLogClearOffset.value)
})
const loginLogs = computed(() => {
  const logs = loginTask.value?.logs || []
  if (!loginLogClearOffset.value) return logs
  return logs.slice(loginLogClearOffset.value)
})
const hasTaskData = computed(() =>
  Boolean(automationError.value) ||
  Boolean(registerTask.value) ||
  Boolean(loginTask.value) ||
  registerLogs.value.length > 0 ||
  loginLogs.value.length > 0
)

const scrollTaskLogsToBottom = async () => {
  await nextTick()
  const container = taskLogsRef.value
  if (!container) return
  container.scrollTop = container.scrollHeight
}

watch([registerLogs, loginLogs, isTaskOpen], async () => {
  if (!isTaskOpen.value) return
  await scrollTaskLogsToBottom()
}, { deep: true })
const isTaskRunning = computed(() => {
  const registerStatus = registerTask.value?.status
  const loginStatus = loginTask.value?.status
  return registerStatus === 'running' ||
    registerStatus === 'pending' ||
    loginStatus === 'running' ||
    loginStatus === 'pending'
})
const taskIndicatorClass = computed(() => {
  if (automationError.value) return 'bg-rose-500'
  if (isTaskRunning.value) return 'bg-sky-400'

  const taskSummaries = []
  if (registerTask.value) {
    const success = registerTask.value.success_count ?? 0
    const fail = registerTask.value.fail_count ?? 0
    const total = registerTask.value.count ?? success + fail
    taskSummaries.push({ success, fail, total, status: registerTask.value.status })
  }
  if (loginTask.value) {
    const success = loginTask.value.success_count ?? 0
    const fail = loginTask.value.fail_count ?? 0
    const total = loginTask.value.account_ids?.length ?? success + fail
    taskSummaries.push({ success, fail, total, status: loginTask.value.status })
  }

  if (!taskSummaries.length) return 'bg-muted-foreground'

  const totalSuccess = taskSummaries.reduce((sum, item) => sum + item.success, 0)
  const totalFail = taskSummaries.reduce((sum, item) => sum + item.fail, 0)
  const totalCount = taskSummaries.reduce((sum, item) => sum + (item.total || 0), 0)

  if (totalSuccess > 0 && totalFail > 0) return 'bg-amber-400'
  if (totalFail > 0 && totalSuccess === 0) return 'bg-rose-500'
  if (totalSuccess > 0 && totalFail === 0) return 'bg-emerald-400'

  if (totalCount === 0) {
    const allSuccess = taskSummaries.every(item => item.status === 'success')
    const anyFailed = taskSummaries.some(item => item.status === 'failed')
    if (anyFailed) return 'bg-rose-500'
    if (allSuccess) return 'bg-emerald-400'
  }

  return 'bg-muted-foreground'
})

onBeforeUnmount(() => {
  clearRegisterTimer()
  clearLoginTimer()
  clearBackgroundTaskTimer()
  document.removeEventListener('click', handleMoreActionsClick)
})

const statusLabel = (account: AdminAccount) => {
  if (account.cooldown_reason?.includes('429') && account.cooldown_seconds > 0) {
    return '429限流'
  }
  if (account.cooldown_reason === '错误禁用') {
    return '错误禁用'
  }
  if (account.disabled) {
    return '手动禁用'
  }
  if (account.status === '已过期') {
    return '已过期'
  }
  if (account.status === '即将过期') {
    return '即将过期'
  }
  return '正常'
}

const statusClass = (account: AdminAccount) => {
  const status = statusLabel(account)
  if (status === '429限流' || status === '即将过期') {
    return 'bg-amber-200 text-amber-900'
  }
  if (status === '错误禁用' || status === '已过期') {
    return 'bg-destructive/10 text-destructive'
  }
  if (status === '手动禁用') {
    return 'bg-muted text-muted-foreground'
  }
  return 'bg-emerald-500 text-white'
}

const shouldShowEnable = (account: AdminAccount) => {
  if (account.cooldown_reason?.includes('429') && account.cooldown_seconds > 0) {
    return true
  }
  return account.disabled || account.cooldown_reason === '错误禁用'
}

const displayRemaining = (value: string) => {
  if (value === '已过期') return '过期'
  if (value === '未设置') return '未设置'
  return value
}

const remainingClass = (account: AdminAccount) => {
  if (account.status === '已过期') return 'text-rose-600'
  if (account.status === '即将过期') return 'text-amber-700'
  if (account.status === '未设置') return 'text-muted-foreground'
  return 'text-emerald-600'
}

const formatCooldown = (seconds: number) => {
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} 分钟`
  return `${(seconds / 3600).toFixed(1)} 小时`
}

const cooldownClass = (account: AdminAccount) => {
  if (account.cooldown_seconds > 0) return 'text-amber-700'
  if (account.cooldown_reason === '错误禁用') return 'text-rose-600'
  return 'text-muted-foreground'
}

const rowClass = (account: AdminAccount) => {
  const status = statusLabel(account)
  if (status === '手动禁用' || status === '已过期') {
    return 'bg-muted/70'
  }
  return ''
}

const toggleSelect = (accountId: string) => {
  const next = new Set(selectedIds.value)
  if (next.has(accountId)) {
    next.delete(accountId)
  } else {
    next.add(accountId)
  }
  selectedIds.value = next
}

const toggleSelectAll = () => {
  if (allSelected.value) {
    selectedIds.value = new Set()
    return
  }
  selectedIds.value = new Set(filteredAccounts.value.map(account => account.id))
}

const getConfigId = (acc: AccountConfigItem, index: number) =>
  acc.id || `account_${index + 1}`

const loadConfigList = async () => {
  const response = await accountsApi.getConfig()
  return response.accounts.map((acc, index) => ({
    ...acc,
    id: getConfigId(acc, index),
  }))
}

const formatLogLine = (log: { time: string; level: string; message: string }) =>
  `${log.time} [${log.level}] ${log.message}`

const applyEditTarget = (list: AccountConfigItem[], accountId: string) => {
  let targetIndex = -1
  for (let i = 0; i < list.length; i += 1) {
    if (list[i].id === accountId) {
      targetIndex = i
      break
    }
  }
  if (targetIndex === -1) {
    editError.value = '未找到对应账号配置。'
    return false
  }

  const target = list[targetIndex]
  editForm.value = {
    id: target.id,
    secure_c_ses: target.secure_c_ses,
    csesidx: target.csesidx,
    config_id: target.config_id,
    host_c_oses: target.host_c_oses,
    expires_at: target.expires_at,
  }
  configAccounts.value = list
  editIndex.value = targetIndex
  isEditOpen.value = true
  return true
}

const openEdit = async (accountId: string) => {
  editError.value = ''
  try {
    const list = await loadConfigList()
    applyEditTarget(list, accountId)
  } catch (error: any) {
    editError.value = error.message || '加载账号配置失败'
  }
}

const openConfigPanel = async () => {
  configError.value = ''
  try {
    const response = await accountsApi.getConfig()
    configData.value = Array.isArray(response.accounts) ? response.accounts : []
    configJson.value = JSON.stringify(maskConfig(configData.value), null, 2)
    configMasked.value = true
    isConfigOpen.value = true
  } catch (error: any) {
    configError.value = error.message || '加载账号配置失败'
  }
}

const closeConfigPanel = () => {
  isConfigOpen.value = false
  configError.value = ''
  configMasked.value = false
}

const getConfigFromEditor = () => {
  const parsed = JSON.parse(configJson.value)
  if (!Array.isArray(parsed)) {
    throw new Error('配置格式必须是数组。')
  }
  return parsed as AccountConfigItem[]
}

const maskValue = (value: unknown) => {
  if (typeof value !== 'string') return value
  if (!value) return value
  if (value.length <= 6) return `${value.slice(0, 2)}****`
  return `${value.slice(0, 3)}****`
}

const maskConfig = (list: AccountConfigItem[]) => {
  const fields = new Set([
    'secure_c_ses',
    'csesidx',
    'config_id',
    'host_c_oses',
    'mail_password',
    'mail_refresh_token',
    'mail_client_id',
  ])
  return list.map((item) => {
    const next = { ...item }
    fields.forEach((field) => {
      const value = (next as Record<string, unknown>)[field]
      if (value) {
        ;(next as Record<string, unknown>)[field] = maskValue(value)
      }
    })
    return next
  })
}

const toggleConfigMask = () => {
  configError.value = ''
  if (!configMasked.value) {
    try {
      configData.value = getConfigFromEditor()
    } catch (error: any) {
      configError.value = error.message || 'JSON 格式错误'
      return
    }
    configJson.value = JSON.stringify(maskConfig(configData.value), null, 2)
    configMasked.value = true
    return
  }

  configJson.value = JSON.stringify(configData.value, null, 2)
  configMasked.value = false
}

const saveConfigPanel = async () => {
  configError.value = ''
  try {
    const parsed = getConfigFromEditor()
    await accountsStore.updateConfig(parsed)
    toast.success('配置保存成功')
    closeConfigPanel()
  } catch (error: any) {
    configError.value = error.message || '保存失败'
    toast.error(error.message || '保存失败')
  }
}

const closeEdit = () => {
  isEditOpen.value = false
  editError.value = ''
}

const saveEdit = async () => {
  if (editIndex.value === null) return
  const next = [...configAccounts.value]
  next[editIndex.value] = {
    ...next[editIndex.value],
    id: editForm.value.id,
    secure_c_ses: editForm.value.secure_c_ses,
    csesidx: editForm.value.csesidx,
    config_id: editForm.value.config_id,
    host_c_oses: editForm.value.host_c_oses || undefined,
    expires_at: editForm.value.expires_at || undefined,
  }

  try {
    await accountsStore.updateConfig(next)
    toast.success('账号编辑成功')
    closeEdit()
  } catch (error: any) {
    editError.value = error.message || '保存失败'
    toast.error(error.message || '保存失败')
  }
}

const handleBulkEnable = async () => {
  try {
    await accountsStore.bulkEnable(Array.from(selectedIds.value))
    toast.success('批量启用成功')
    selectedIds.value = new Set()
  } catch (error: any) {
    toast.error(error.message || '批量启用失败')
  }
}

const handleBulkDisable = async () => {
  const confirmed = await confirmDialog.ask({
    title: '批量禁用',
    message: '确定要批量禁用选中的账号吗？',
  })
  if (!confirmed) return
  try {
    await accountsStore.bulkDisable(Array.from(selectedIds.value))
    toast.success('批量禁用成功')
    selectedIds.value = new Set()
  } catch (error: any) {
    toast.error(error.message || '批量禁用失败')
  }
}

const handleBulkDelete = async () => {
  const confirmed = await confirmDialog.ask({
    title: '批量删除',
    message: '确定要批量删除选中的账号吗？',
    confirmText: '删除',
  })
  if (!confirmed) return
  try {
    await accountsStore.bulkDelete(Array.from(selectedIds.value))
    toast.success('批量删除成功')
    selectedIds.value = new Set()
  } catch (error: any) {
    toast.error(error.message || '批量删除失败')
  }
}

const handleEnable = async (accountId: string) => {
  try {
    await accountsStore.enableAccount(accountId)
    toast.success('账号已启用')
  } catch (error: any) {
    toast.error(error.message || '启用失败')
  }
}

const handleDisable = async (accountId: string) => {
  const confirmed = await confirmDialog.ask({
    title: '禁用账号',
    message: '确定要禁用该账号吗？',
  })
  if (!confirmed) return
  try {
    await accountsStore.disableAccount(accountId)
    toast.success('账号已禁用')
  } catch (error: any) {
    toast.error(error.message || '禁用失败')
  }
}

const handleDelete = async (accountId: string) => {
  const confirmed = await confirmDialog.ask({
    title: '删除账号',
    message: '确定要删除该账号吗？',
    confirmText: '删除',
  })
  if (!confirmed) return
  try {
    await accountsStore.deleteAccount(accountId)
    toast.success('账号已删除')
  } catch (error: any) {
    toast.error(error.message || '删除失败')
  }
}

let registerTimer: number | null = null
let loginTimer: number | null = null
let backgroundTaskTimer: number | null = null
let backgroundTaskPending = false

const clearRegisterTimer = () => {
  if (registerTimer !== null) {
    window.clearInterval(registerTimer)
    registerTimer = null
  }
}

const clearLoginTimer = () => {
  if (loginTimer !== null) {
    window.clearInterval(loginTimer)
    loginTimer = null
  }
}

const clearBackgroundTaskTimer = () => {
  if (backgroundTaskTimer !== null) {
    window.clearInterval(backgroundTaskTimer)
    backgroundTaskTimer = null
  }
  backgroundTaskPending = false
}

const formatTaskStatus = (status: string) => {
  if (status === 'pending') return '等待中'
  if (status === 'running') return '执行中'
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  return status
}

const getTaskStatusIndicatorClass = (task: RegisterTask | LoginTask) => {
  const status = task.status
  const success = task.success_count ?? 0
  const fail = task.fail_count ?? 0

  // 执行中或等待中 - 蓝色
  if (status === 'running' || status === 'pending') {
    return 'bg-sky-400'
  }

  // 任务完成后根据成功失败情况判断
  if (status === 'success' || status === 'failed') {
    // 全部成功 - 绿色
    if (success > 0 && fail === 0) {
      return 'bg-emerald-400'
    }
    // 全部失败 - 红色
    if (fail > 0 && success === 0) {
      return 'bg-rose-500'
    }
    // 部分成功部分失败 - 黄色
    if (success > 0 && fail > 0) {
      return 'bg-amber-400'
    }
  }

  // 默认灰色
  return 'bg-muted-foreground'
}

const updateRegisterTask = async (taskId: string) => {
  if (isClearedRegisterTaskId(taskId)) {
    clearRegisterTimer()
    return
  }
  const task = await accountsApi.getRegisterTask(taskId)
  if (isClearedRegisterTaskId(task.id)) {
    clearRegisterTimer()
    return
  }
  syncRegisterTask(task)
  if (task.status !== 'running' && task.status !== 'pending') {
    isRegistering.value = false
    clearRegisterTimer()
    await refreshAccounts()

    // 显示任务完成通知
    const successCount = task.success_count || 0
    const failCount = task.fail_count || 0
    if (successCount > 0 && failCount > 0) {
      toast.success(`注册任务完成：成功 ${successCount}，失败 ${failCount}`)
    } else if (successCount > 0 && failCount === 0) {
      toast.success(`注册任务完成：全部成功 (${successCount})`)
    } else if (failCount > 0 && successCount === 0) {
      toast.error(`注册任务完成：全部失败 (${failCount})`)
    } else {
      toast.error('注册任务失败')
    }
  }
}

const updateLoginTask = async (taskId: string) => {
  if (isClearedLoginTaskId(taskId)) {
    clearLoginTimer()
    return
  }
  const task = await accountsApi.getLoginTask(taskId)
  if (isClearedLoginTaskId(task.id)) {
    clearLoginTimer()
    return
  }
  syncLoginTask(task)
  if (task.status !== 'running' && task.status !== 'pending') {
    isRefreshing.value = false
    clearLoginTimer()
    await refreshAccounts()

    // 显示任务完成通知
    const successCount = task.success_count || 0
    const failCount = task.fail_count || 0
    if (successCount > 0 && failCount > 0) {
      toast.success(`刷新任务完成：成功 ${successCount}，失败 ${failCount}`)
    } else if (successCount > 0 && failCount === 0) {
      toast.success(`刷新任务完成：全部成功 (${successCount})`)
    } else if (failCount > 0 && successCount === 0) {
      toast.error(`刷新任务完成：全部失败 (${failCount})`)
    } else {
      toast.error('刷新任务失败')
    }
  }
}

const startRegisterPolling = (taskId: string) => {
  clearRegisterTimer()
  registerTimer = window.setInterval(() => {
    updateRegisterTask(taskId).catch((error) => {
      automationError.value = error?.message || '注册任务更新失败'
      clearRegisterTimer()
      isRegistering.value = false
    })
  }, 3000)
}

const startLoginPolling = (taskId: string) => {
  clearLoginTimer()
  loginTimer = window.setInterval(() => {
    updateLoginTask(taskId).catch((error) => {
      automationError.value = error?.message || '刷新任务更新失败'
      clearLoginTimer()
      isRefreshing.value = false
    })
  }, 3000)
}

const startBackgroundTaskPolling = () => {
  if (backgroundTaskTimer !== null) return
  backgroundTaskTimer = window.setInterval(async () => {
    if (backgroundTaskPending) return
    if (isTaskOpen.value) return
    if (registerTimer !== null || loginTimer !== null) return
    if (!isRegistering.value && !isRefreshing.value && !registerTask.value && !loginTask.value) return
    backgroundTaskPending = true
    try {
      await loadCurrentTasks()
    } catch (error: any) {
      automationError.value = error?.message || '后台刷新失败'
    } finally {
      backgroundTaskPending = false
    }
  }, 6000)
}

const loadCurrentTasks = async () => {
  try {
    const registerCurrent = await accountsApi.getRegisterCurrent()
    if (registerCurrent && 'id' in registerCurrent && !isClearedRegisterTaskId(registerCurrent.id)) {
      syncRegisterTask(registerCurrent)
      if (registerCurrent.status === 'running' || registerCurrent.status === 'pending') {
        isRegistering.value = true
        startRegisterPolling(registerCurrent.id)
      }
    }
  } catch (error: any) {
    automationError.value = error.message || '加载注册任务失败'
  }

  try {
    const loginCurrent = await accountsApi.getLoginCurrent()
    if (loginCurrent && 'id' in loginCurrent && !isClearedLoginTaskId(loginCurrent.id)) {
      syncLoginTask(loginCurrent)
      if (loginCurrent.status === 'running' || loginCurrent.status === 'pending') {
        isRefreshing.value = true
        startLoginPolling(loginCurrent.id)
      }
    }
  } catch (error: any) {
    automationError.value = error.message || '加载刷新任务失败'
  }
}

const handleRegister = async () => {
  automationError.value = ''
  isRegistering.value = true
  try {
    const count = Number.isFinite(registerCount.value) && registerCount.value > 0
      ? registerCount.value
      : undefined
    const task = await accountsApi.startRegister(count)
    syncRegisterTask(task)
    startRegisterPolling(task.id)
    isRegisterOpen.value = false
    isTaskOpen.value = true
  } catch (error: any) {
    automationError.value = error.message || '启动注册失败'
    isRegistering.value = false
  }
}

const handleRefreshSelected = async () => {
  if (!selectedIds.value.size) return
  automationError.value = ''
  isRefreshing.value = true
  try {
    const task = await accountsApi.startLogin(Array.from(selectedIds.value))
    syncLoginTask(task)
    startLoginPolling(task.id)
    // 自动打开任务状态弹窗
    openTaskModal()
  } catch (error: any) {
    automationError.value = error.message || '启动刷新失败'
    isRefreshing.value = false
  }
}

const handleRefreshExpiring = async () => {
  automationError.value = ''
  isRefreshing.value = true
  try {
    await accountsApi.checkLogin()
    const current = await accountsApi.getLoginCurrent()
    if (current && 'id' in current) {
      syncLoginTask(current)
      startLoginPolling(current.id)
      // 自动打开任务状态弹窗
      openTaskModal()
      return
    }
    isRefreshing.value = false
  } catch (error: any) {
    automationError.value = error.message || '触发刷新失败'
    isRefreshing.value = false
  }
}
</script>

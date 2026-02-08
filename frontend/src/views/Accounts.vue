<template>
  <div class="space-y-8 relative">
    <!-- 全局加载遮罩 -->
    <Teleport to="body">
      <div
        v-if="isOperating"
        class="fixed inset-0 z-[200] flex items-center justify-center bg-background/80 backdrop-blur-sm"
      >
        <div class="flex flex-col items-center gap-4 rounded-2xl border border-border bg-card p-8 shadow-lg">
          <svg class="h-10 w-10 animate-spin text-primary" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <div class="flex flex-col items-center gap-2">
            <p class="text-sm font-medium text-foreground">
              {{ batchProgress ? `处理中 ${batchProgress.current}/${batchProgress.total}` : '操作处理中...' }}
            </p>
            <div v-if="batchProgress" class="w-48 h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                class="h-full bg-primary transition-all duration-300"
                :style="{ width: `${(batchProgress.current / batchProgress.total) * 100}%` }"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

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
          :disabled="isRegistering || isRefreshing"
          @click="openRegisterModal"
        >
          添加账户
        </button>

        <button
          class="relative rounded-full border border-border px-4 py-2 text-sm font-medium transition-colors
                 hover:border-primary hover:text-primary"
          @click="openTaskModal"
        >
          <span class="flex items-center gap-2">
            任务管理
            <template v-if="isTaskRunning">
              <span class="flex items-center gap-1.5 text-xs text-sky-500">
                <span class="relative flex h-2 w-2">
                  <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-500 opacity-75"></span>
                  <span class="relative inline-flex h-2 w-2 rounded-full bg-sky-500"></span>
                </span>
                {{ taskProgressText }}
              </span>
            </template>
          </span>
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
          </button>
          <div
            v-if="showMoreActions"
            class="absolute right-0 z-10 mt-2 w-full space-y-1 rounded-2xl border border-border bg-card p-2 shadow-lg"
          >
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm text-foreground transition-colors
                     hover:bg-accent"
              @click="triggerImportFile(); closeMoreActions()"
            >
              导入文件
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm text-foreground transition-colors
                     hover:bg-accent"
              @click="openExportModal(); closeMoreActions()"
            >
              导出账户
            </button>
            <div class="my-1 border-t border-border/60"></div>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="isRegistering
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="isRegistering"
              @click="handleRefreshExpiring(); closeMoreActions()"
            >
              刷新过期
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount || isRegistering
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="!selectedCount || isRegistering"
              @click="handleRefreshSelected(); closeMoreActions()"
            >
              刷新选中
            </button>
            <div class="my-1 border-t border-border/60"></div>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount || isOperating
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="!selectedCount || isOperating"
              @click="handleBulkEnable(); closeMoreActions()"
            >
              <span v-if="isOperating" class="flex items-center gap-2">
                <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                处理中...
              </span>
              <span v-else>批量启用</span>
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount || isOperating
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-foreground hover:bg-accent'"
              :disabled="!selectedCount || isOperating"
              @click="handleBulkDisable(); closeMoreActions()"
            >
              <span v-if="isOperating" class="flex items-center gap-2">
                <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                处理中...
              </span>
              <span v-else>批量禁用</span>
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
              :class="!selectedCount || isOperating
                ? 'cursor-not-allowed text-muted-foreground'
                : 'text-destructive hover:bg-destructive/10'"
              :disabled="!selectedCount || isOperating"
              @click="handleBulkDelete(); closeMoreActions()"
            >
              <span v-if="isOperating" class="flex items-center gap-2">
                <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                处理中...
              </span>
              <span v-else>批量删除</span>
            </button>
          </div>
        </div>
      </div>

      <div v-if="viewMode === 'card'" class="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="account in paginatedAccounts"
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
            <Checkbox
              :modelValue="selectedIds.has(account.id)"
              @update:modelValue="toggleSelect(account.id)"
              @click.stop
            />
          </div>

          <div class="mt-4 grid grid-cols-2 gap-3 text-xs text-muted-foreground">
            <div>
              <p>状态</p>
              <p class="mt-1 text-sm font-semibold text-foreground">
                <span
                  class="inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs"
                  :class="statusClass(account)"
                >
                  {{ statusLabel(account) }}
                </span>
              </p>
            </div>
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
              <p>配额</p>
              <div class="mt-1">
                <QuotaBadge v-if="account.quota_status" :quota-status="account.quota_status" />
                <span v-else class="text-xs text-muted-foreground">-</span>
              </div>
            </div>
            <div>
              <p>失败数</p>
              <p class="mt-1 text-sm font-semibold text-foreground">{{ account.failure_count }}</p>
            </div>
            <div>
              <p>成功数</p>
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
              <th class="py-3 pr-6">配额</th>
              <th class="py-3 pr-6">失败数</th>
              <th class="py-3 pr-6">成功数</th>
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
              v-for="account in paginatedAccounts"
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
              <td class="py-4 pr-6">
                <QuotaBadge v-if="account.quota_status" :quota-status="account.quota_status" />
                <span v-else class="text-xs text-muted-foreground">-</span>
              </td>
              <td class="py-4 pr-6 text-xs text-muted-foreground">
                {{ account.failure_count }}
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

      <!-- Pagination Controls -->
      <div v-if="filteredAccounts.length > pageSize" class="mt-6 flex items-center justify-between">
        <div class="text-sm text-muted-foreground">
          显示 {{ (currentPage - 1) * pageSize + 1 }}-{{ Math.min(currentPage * pageSize, filteredAccounts.length) }} / 共 {{ filteredAccounts.length }} 个账户
        </div>
        <div class="flex items-center gap-2">
          <button
            class="rounded-full border border-border px-4 py-2 text-sm transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="currentPage === 1"
            @click="currentPage--"
          >
            上一页
          </button>
          <span class="text-sm text-muted-foreground">{{ currentPage }} / {{ totalPages }}</span>
          <button
            class="rounded-full border border-border px-4 py-2 text-sm transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="currentPage === totalPages"
            @click="currentPage++"
          >
            下一页
          </button>
        </div>
      </div>
    </section>
  </div>
  <Teleport to="body">
    <div v-if="isRegisterOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-xl">
        <div class="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <p class="text-sm font-medium text-foreground">添加账户</p>
            <p class="mt-1 text-xs text-muted-foreground">
              {{ addMode === 'register' ? '创建临时邮箱账号并自动注册' : '批量导入账户配置' }}
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
            <label class="block text-xs text-muted-foreground">临时邮箱服务</label>
            <SelectMenu
              v-model="selectedMailProvider"
              :options="mailProviderOptions"
              class="w-full"
            />
            <label class="block text-xs text-muted-foreground">注册数量</label>
            <input
              v-model.number="registerCount"
              type="number"
              min="1"
              class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
            />
          </div>

          <div v-else class="space-y-4">
            <label class="block text-xs text-muted-foreground">批量导入（每行一个）</label>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors
                       hover:border-primary hover:text-primary"
                @click="triggerImportFile"
              >
                上传文件
              </button>
              <span v-if="importFileName" class="text-xs text-muted-foreground">{{ importFileName }}</span>
            </div>
            <textarea
              v-model="importText"
              class="min-h-[140px] w-full rounded-2xl border border-input bg-background px-3 py-2 text-xs font-mono"
              placeholder="duckmail----you@example.com----password&#10;moemail----you@moemail.app----emailId&#10;freemail----you@freemail.local&#10;gptmail----you@example.com&#10;user@outlook.com----loginPassword----clientId----refreshToken"
            ></textarea>
            <div class="rounded-2xl border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <p>支持三种格式：</p>
              <p class="mt-1 font-mono">duckmail----email----password</p>
              <p class="mt-1 font-mono">moemail----email----emailId</p>
              <p class="mt-1 font-mono">freemail----email</p>
              <p class="mt-1 font-mono">gptmail----email</p>
              <p class="mt-1 font-mono">email----password----clientId----refreshToken</p>
              <p class="mt-2">导入后请执行一次"刷新选中"以获取 Cookie。</p>
              <p class="mt-1">注册失败建议关闭无头浏览器再试</p>
            </div>
            <div v-if="importError" class="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-600">
              {{ importError }}
            </div>
          </div>

          <div class="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] leading-relaxed">
            <p class="flex items-center gap-1.5 text-xs font-bold text-rose-600">
              <svg class="h-4 w-4 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
              </svg>
              严禁滥用：禁止将本工具用于商业用途或任何形式的滥用（无论规模大小）
            </p>
            <p class="mt-1 text-muted-foreground">详细声明请查看项目 <a href="https://github.com/Dreamy-rain/gemini-business2api/blob/main/docs/DISCLAIMER.md" target="_blank" class="text-primary hover:underline font-medium">DISCLAIMER.md</a></p>
          </div>
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
              :disabled="isRegistering"
              @click="handleRegister"
            >
              开始注册
            </button>
            <button
              v-else
              class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                     hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="isImporting"
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
            <p class="text-sm font-medium text-foreground">任务管理</p>
            <p class="mt-1 text-xs text-muted-foreground">管理注册与刷新任务</p>
          </div>
          <button
            class="text-xs text-muted-foreground transition-colors hover:text-foreground"
            @click="closeTaskModal"
          >
            关闭
          </button>
        </div>

        <!-- Tab 导航 -->
        <div class="flex border-b border-border/60 px-6">
          <button
            type="button"
            class="relative px-4 py-3 text-sm font-medium transition-colors"
            :class="activeTaskTab === 'current' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'"
            @click="activeTaskTab = 'current'"
          >
            当前任务
            <span
              v-if="activeTaskTab === 'current'"
              class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
            ></span>
          </button>
          <button
            type="button"
            class="relative px-4 py-3 text-sm font-medium transition-colors"
            :class="activeTaskTab === 'scheduled' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'"
            @click="activeTaskTab = 'scheduled'; loadScheduledConfig()"
          >
            定时任务
            <span
              v-if="activeTaskTab === 'scheduled'"
              class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
            ></span>
          </button>
          <button
            type="button"
            class="relative px-4 py-3 text-sm font-medium transition-colors"
            :class="activeTaskTab === 'history' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'"
            @click="activeTaskTab = 'history'"
          >
            历史记录
            <span
              v-if="activeTaskTab === 'history'"
              class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
            ></span>
          </button>
        </div>

        <!-- 当前任务 Tab -->
        <div v-if="activeTaskTab === 'current'" class="flex min-h-0 flex-1 flex-col">
          <!-- 固定任务信息区域 -->
          <div v-if="automationError || registerTask || loginTask" class="px-6 py-4">
            <div v-if="automationError" class="rounded-2xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {{ automationError }}
            </div>

            <div v-if="registerTask || loginTask" class="grid gap-3 text-xs text-muted-foreground">
            <div v-if="registerTask" class="space-y-1">
              <div class="flex items-center justify-between gap-3 font-medium text-foreground">
                <div class="flex items-center gap-2">
                  <span
                    class="h-2.5 w-2.5 rounded-full"
                    :class="getTaskStatusIndicatorClass(registerTask)"
                    aria-hidden="true"
                  ></span>
                  注册任务
                </div>
                <button
                  v-if="registerTask.status === 'running' || registerTask.status === 'pending'"
                  class="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-rose-500 hover:text-rose-600"
                  @click="cancelRegister(registerTask.id)"
                >
                  中断
                </button>
              </div>
              <div class="flex flex-wrap gap-x-4 gap-y-1">
                <span>状态：{{ formatTaskStatus(registerTask) }}</span>
                <span>进度：{{ registerTask.progress }}/{{ registerTask.count }}</span>
                <span>成功：{{ registerTask.success_count }}</span>
                <span>失败：{{ registerTask.fail_count }}</span>
              </div>
            </div>
            <div v-if="loginTask" class="space-y-1">
              <div class="flex items-center justify-between gap-3 font-medium text-foreground">
                <div class="flex items-center gap-2">
                  <span
                    class="h-2.5 w-2.5 rounded-full"
                    :class="getTaskStatusIndicatorClass(loginTask)"
                    aria-hidden="true"
                  ></span>
                  刷新任务
                </div>
                <button
                  v-if="loginTask.status === 'running' || loginTask.status === 'pending'"
                  class="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-rose-500 hover:text-rose-600"
                  @click="cancelLogin(loginTask.id)"
                >
                  中断
                </button>
              </div>
              <div class="flex flex-wrap gap-x-4 gap-y-1">
                <span>状态：{{ formatTaskStatus(loginTask) }}</span>
                <span>进度：{{ loginTask.progress }}/{{ loginTask.account_ids.length }}</span>
                <span>成功：{{ loginTask.success_count }}</span>
                <span>失败：{{ loginTask.fail_count }}</span>
              </div>
            </div>
          </div>
          </div>

          <!-- 日志区域（独立滚动） -->
          <div
            v-if="registerTask || loginTask || registerLogs.length || loginLogs.length"
            class="flex min-h-0 flex-1 flex-col px-6 pb-4"
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
              <div v-if="!registerLogs.length && !loginLogs.length" class="text-xs text-muted-foreground">
                日志已清空，新的日志会继续显示。
              </div>
            </div>
          </div>

          <div
            v-if="!automationError && !registerTask && !loginTask && !registerLogs.length && !loginLogs.length"
            class="flex-1 px-6 py-4"
          >
            <div class="rounded-2xl border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              暂无任务
            </div>
          </div>

          <!-- 固定底部按钮区域 -->
          <div class="flex items-center justify-end gap-2 border-t border-border/60 px-6 py-4">
            <button
              class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!registerLogs.length && !loginLogs.length && !registerTask && !loginTask && !automationError"
              @click="clearTaskLogs"
            >
              清空日志
            </button>
          </div>
        </div>

        <!-- 定时任务 Tab -->
        <div v-if="activeTaskTab === 'scheduled'" class="flex min-h-0 flex-1 flex-col">
          <div class="flex min-h-0 flex-1 flex-col">
              <div class="flex-1 overflow-y-auto px-6 py-4">
                <div class="space-y-4">
                  <div class="space-y-3">
                    <div class="flex items-center justify-between">
                      <div>
                        <p class="text-sm font-medium text-foreground">启用定时刷新</p>
                        <p class="mt-1 text-xs text-muted-foreground">自动检测并刷新即将过期的账号</p>
                      </div>
                      <button
                        type="button"
                        class="relative inline-flex h-5 w-10 items-center rounded-full transition-colors"
                        :class="scheduledRefreshEnabled ? 'bg-primary' : 'bg-muted'"
                        @click="scheduledRefreshEnabled = !scheduledRefreshEnabled"
                      >
                        <span
                          class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                          :class="scheduledRefreshEnabled ? 'translate-x-5' : 'translate-x-1'"
                        ></span>
                      </button>
                    </div>

                    <div class="space-y-2">
                      <label class="block text-xs text-muted-foreground">检测间隔（分钟）</label>
                      <input
                        v-model.number="scheduledRefreshInterval"
                        type="number"
                        min="0"
                        max="720"
                        class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                      />
                      <p class="text-xs text-muted-foreground">
                        范围：0-720 分钟（{{ Math.floor(scheduledRefreshInterval / 60) }} 小时 {{ scheduledRefreshInterval % 60 }} 分钟）
                      </p>
                    </div>

                    <div class="space-y-2">
                      <label class="block text-xs text-muted-foreground">过期刷新窗口（小时）</label>
                      <input
                        v-model.number="refreshWindowHours"
                        type="number"
                        min="1"
                        max="168"
                        class="w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm"
                      />
                      <p class="text-xs text-muted-foreground">
                        当账号距离过期小于等于该值时，会触发自动刷新
                      </p>
                    </div>

                    <div class="rounded-2xl border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
                      <p class="mb-2 font-medium text-foreground">说明</p>
                      <ul class="list-inside list-disc space-y-1">
                        <li>定时任务会在后台自动运行，无需手动触发</li>
                        <li>每次检测会自动刷新即将过期的账号（距离过期 ≤ 过期刷新窗口）</li>
                        <li>修改配置后立即生效，无需重启服务</li>
                        <li>禁用后，定时任务将停止运行</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>

            <!-- 固定底部按钮区域 -->
            <div class="flex items-center justify-end gap-2 border-t border-border/60 px-6 py-4">
              <button
                class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                       hover:border-primary hover:text-primary"
                @click="loadScheduledConfig"
              >
                重置
              </button>
              <button
                class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                       hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="isSavingScheduledConfig"
                @click="saveScheduledConfig"
              >
                保存配置
              </button>
            </div>
          </div>
        </div>

        <!-- 历史记录 Tab -->
        <div v-if="activeTaskTab === 'history'" class="flex min-h-0 flex-1 flex-col">
          <div class="flex-1 overflow-y-auto px-6 py-4">
            <div v-if="isLoadingHistory" class="flex items-center justify-center py-8">
              <svg class="h-6 w-6 animate-spin text-muted-foreground" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
            <div v-else-if="taskHistory.length === 0" class="rounded-2xl border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <p class="font-medium text-foreground mb-2">暂无历史记录</p>
              <p>完成的任务将显示在这里</p>
            </div>
            <div v-else class="space-y-3">
              <div
                v-for="(record, index) in taskHistory"
                :key="index"
                class="rounded-2xl border border-border bg-card px-4 py-3 text-sm"
              >
                <div class="flex items-center justify-between mb-2">
                  <span class="flex items-center gap-2 font-medium text-foreground">
                    <span
                      class="h-2.5 w-2.5 rounded-full"
                      :class="getHistoryStatusIndicatorClass(record)"
                      aria-hidden="true"
                    ></span>
                    {{ record.type === 'login' ? '刷新任务' : '注册任务' }}
                  </span>
                  <span class="text-xs text-muted-foreground">
                    {{ new Date(record.created_at * 1000).toLocaleString('zh-CN') }}
                  </span>
                </div>
                <div class="text-xs text-muted-foreground space-y-1">
                  <div>
                    状态：<span :class="getHistoryStatusTextClass(record)">
                      {{ formatTaskStatus(record) }}
                    </span>
                  </div>
                  <div class="flex flex-wrap gap-x-4 gap-y-1">
                    <span>进度：{{ record.progress }}/{{ getHistoryTotal(record) }}</span>
                    <span>成功：{{ record.success_count }}</span>
                    <span>失败：{{ record.fail_count }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 固定底部按钮区域 -->
          <div class="flex items-center justify-end gap-2 border-t border-border/60 px-6 py-4">
            <button
              class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="taskHistory.length === 0"
              @click="clearTaskHistory"
            >
              清空历史
            </button>
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
  <Teleport to="body">
    <div v-if="isExportOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="flex max-h-[90vh] w-full max-w-md flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-xl">
        <div class="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <p class="text-sm font-medium text-foreground">导出账号配置</p>
            <p class="mt-1 text-xs text-muted-foreground">选择导出范围与格式</p>
          </div>
          <button
            class="text-xs text-muted-foreground transition-colors hover:text-foreground"
            @click="closeExportModal"
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
                :class="exportScope === 'all' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'"
                @click="exportScope = 'all'"
              >
                全部
              </button>
              <button
                type="button"
                class="flex-1 rounded-full px-3 py-2 font-medium transition-colors"
                :class="exportScope === 'selected' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'"
                :disabled="!selectedCount"
                @click="exportScope = 'selected'"
              >
                选中
              </button>
            </div>

            <div class="flex rounded-full border border-border bg-muted/30 p-1 text-xs">
              <button
                type="button"
                class="flex-1 rounded-full px-3 py-2 font-medium transition-colors"
                :class="exportFormat === 'json' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'"
                @click="exportFormat = 'json'"
              >
                JSON
              </button>
              <button
                type="button"
                class="flex-1 rounded-full px-3 py-2 font-medium transition-colors"
                :class="exportFormat === 'txt' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'"
                @click="exportFormat = 'txt'"
              >
                TXT
              </button>
            </div>
            <p class="text-xs text-muted-foreground">
              选中导出仅包含当前已勾选账号（{{ selectedCount }} 个）。
            </p>
          </div>
        </div>
        <div class="border-t border-border/60 px-6 py-4">
          <div class="flex items-center justify-end gap-2">
            <button
              class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors
                     hover:border-primary hover:text-primary"
              @click="closeExportModal"
            >
              取消
            </button>
            <button
              class="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity
                     hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="exportScope === 'selected' && !selectedCount"
              @click="runExport"
            >
              开始导出
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
  <input
    ref="importFileInput"
    type="file"
    class="hidden"
    accept=".txt,.json,application/json,text/plain"
    @change="handleImportFile"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAccountsStore } from '@/stores/accounts'
import { useSettingsStore } from '@/stores/settings'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import QuotaBadge from '@/components/QuotaBadge.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import HelpTip from '@/components/ui/HelpTip.vue'
import { accountsApi, settingsApi } from '@/api'
import { mailProviderOptions, defaultMailProvider } from '@/constants/mailProviders'
import type { AdminAccount, AccountConfigItem, RegisterTask, LoginTask } from '@/types/api'

const accountsStore = useAccountsStore()
const { accounts, isLoading, isOperating, batchProgress } = storeToRefs(accountsStore)
const settingsStore = useSettingsStore()
const { settings } = storeToRefs(settingsStore)
const confirmDialog = useConfirmDialog()
const toast = useToast()

const searchQuery = ref('')
const statusFilter = ref('all')
const selectedIds = ref<Set<string>>(new Set())
const viewMode = ref<'table' | 'card'>('table')
const currentPage = ref(1)
const pageSize = ref(50)
const isEditOpen = ref(false)
const editError = ref('')
const isConfigOpen = ref(false)
const configError = ref('')
const configJson = ref('')
const configMasked = ref(false)
const configData = ref<AccountConfigItem[]>([])
const registerCount = ref(1)
const selectedMailProvider = ref(settings.value?.basic?.temp_mail_provider || defaultMailProvider)
const isRegisterOpen = ref(false)
const addMode = ref<'register' | 'import'>('register')
const importText = ref('')
const importError = ref('')
const isImporting = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)
const importFileName = ref('')
const isExportOpen = ref(false)
const exportScope = ref<'all' | 'selected'>('all')
const exportFormat = ref<'json' | 'txt'>('json')
const isTaskOpen = ref(false)
const activeTaskTab = ref<'current' | 'scheduled' | 'history'>('current')
const showMoreActions = ref(false)
const moreActionsRef = ref<HTMLDivElement | null>(null)
const lastRegisterTaskId = ref<string | null>(null)
const lastLoginTaskId = ref<string | null>(null)
const scheduledRefreshEnabled = ref(false)
const scheduledRefreshInterval = ref(30)
const refreshWindowHours = ref(24)
const isLoadingScheduledConfig = ref(false)
const isSavingScheduledConfig = ref(false)
const cachedSettings = ref<any>(null)  // 缓存配置以避免重复API调用
const taskHistory = ref<any[]>([])  // 任务历史记录
const isLoadingHistory = ref(false)  // 加载历史记录状态
type TaskLogLine = { time: string; level: string; message: string }
const registerLogClearMarker = ref<TaskLogLine | null>(null)
const loginLogClearMarker = ref<TaskLogLine | null>(null)
const registerTask = ref<RegisterTask | null>(null)
const loginTask = ref<LoginTask | null>(null)
const refreshingAccountIds = ref<Set<string>>(new Set())  // 正在刷新的账户ID集合（仅用于显示状态）
const taskLogsRef = ref<HTMLDivElement | null>(null)
const isRegistering = ref(false)
const isRefreshing = ref(false)
const automationError = ref('')
const REGISTER_TASK_CACHE_KEY = 'accounts-register-task-cache'
const LOGIN_TASK_CACHE_KEY = 'accounts-login-task-cache'
const REGISTER_CLEAR_KEY = 'accounts-register-log-clear'
const LOGIN_CLEAR_KEY = 'accounts-login-log-clear'
const REGISTER_DISMISS_KEY = 'accounts-register-task-dismissed'
const LOGIN_DISMISS_KEY = 'accounts-login-task-dismissed'
const REGISTER_CLEARED_KEY = 'accounts-register-task-cleared'
const LOGIN_CLEARED_KEY = 'accounts-login-task-cleared'

type TaskKind = 'register' | 'login'
const TASK_KEYS = {
  register: {
    clearKey: REGISTER_CLEAR_KEY,
    dismissKey: REGISTER_DISMISS_KEY,
    clearedKey: REGISTER_CLEARED_KEY,
  },
  login: {
    clearKey: LOGIN_CLEAR_KEY,
    dismissKey: LOGIN_DISMISS_KEY,
    clearedKey: LOGIN_CLEARED_KEY,
  },
} as const
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

const totalPages = computed(() => Math.ceil(filteredAccounts.value.length / pageSize.value))

const paginatedAccounts = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredAccounts.value.slice(start, end)
})

const selectedCount = computed(() => selectedIds.value.size)
const allSelected = computed(() =>
  filteredAccounts.value.length > 0 && filteredAccounts.value.every(account => selectedIds.value.has(account.id))
)

watch([searchQuery, statusFilter], () => {
  currentPage.value = 1
})

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

const writeCachedTask = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore storage errors
  }
}

const removeCachedTask = (key: string) => {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore storage errors
  }
}

type DismissedTaskMeta = { id?: string; created_at?: number } | null

const readDismissedTaskMeta = (key: string): DismissedTaskMeta => {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    try {
      const parsed = JSON.parse(raw) as Partial<{ id: string; created_at: number }>
      if (parsed && (parsed.id || typeof parsed.created_at === 'number')) {
        return { id: parsed.id, created_at: parsed.created_at }
      }
    } catch {
      // Backward compatibility: plain id string
      return { id: raw }
    }
    return null
  } catch {
    return null
  }
}

const writeDismissedTaskMeta = (key: string, meta: DismissedTaskMeta) => {
  try {
    if (!meta || (!meta.id && typeof meta.created_at !== 'number')) {
      localStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, JSON.stringify(meta))
  } catch {
    // ignore storage errors
  }
}

const readDismissedTaskId = (key: string) => readDismissedTaskMeta(key)?.id || null

const writeDismissedTaskId = (key: string, taskId: string | null) => {
  if (!taskId) {
    writeDismissedTaskMeta(key, null)
    return
  }
  writeDismissedTaskMeta(key, { id: taskId })
}

const isTaskMetaMatch = (task: { id?: string; created_at?: number } | null | undefined, meta: DismissedTaskMeta) => {
  if (!task || !meta) return false
  if (meta.id && task.id && task.id === meta.id) return true
  if (typeof meta.created_at === 'number' && typeof task.created_at === 'number' && task.created_at === meta.created_at) {
    return true
  }
  return false
}

const isTaskDismissed = (task: { id?: string; created_at?: number } | null | undefined, meta: DismissedTaskMeta) =>
  isTaskMetaMatch(task, meta)

const readClearedTaskMeta = (key: string): DismissedTaskMeta => readDismissedTaskMeta(key)
const writeClearedTaskMeta = (key: string, meta: DismissedTaskMeta) => writeDismissedTaskMeta(key, meta)

const isTaskActive = (task: RegisterTask | LoginTask | null | undefined) => {
  const status = task?.status
  return status === 'running' || status === 'pending'
}

const getTaskByKind = (kind: TaskKind) => (kind === 'register' ? registerTask.value : loginTask.value)

const markTaskCleared = (kind: TaskKind, task: RegisterTask | LoginTask) => {
  const key = TASK_KEYS[kind].clearedKey
  writeClearedTaskMeta(key, {
    id: task.id,
    created_at: task.created_at,
  })
}

const setLogClearMarker = (kind: TaskKind, marker: TaskLogLine | null) => {
  if (kind === 'register') {
    registerLogClearMarker.value = marker
  } else {
    loginLogClearMarker.value = marker
  }
}

const clearTaskSnapshot = (kind: TaskKind, persist = true) => {
  if (kind === 'register') {
    syncRegisterTask(null, persist)
  } else {
    syncLoginTask(null, persist)
  }
}

const clearFinishedTask = (kind: TaskKind) => {
  const task = getTaskByKind(kind)
  if (!task || isTaskActive(task)) return
  markTaskCleared(kind, task)
  clearTaskSnapshot(kind, true)
}

const handleTaskIdle = (kind: TaskKind) => {
  // 后端 idle：保留现有任务快照
  cleanupCancelledTasks()
}

const handleTaskNotFound = (kind: TaskKind) => {
  if (kind === 'register') {
    clearRegisterTimer()
    isRegistering.value = false
  } else {
    clearLoginTimer()
    isRefreshing.value = false
  }
}

const handleTaskActive = (kind: TaskKind, task: RegisterTask | LoginTask) => {
  if (kind === 'register') {
    syncRegisterTask(task)
    isRegistering.value = true
    startRegisterPolling(task.id)
  } else {
    syncLoginTask(task)
    isRefreshing.value = true
    startLoginPolling(task.id)
  }
}

const handleTaskInactive = (kind: TaskKind, task: RegisterTask | LoginTask) => {
  if (kind === 'register') {
    syncRegisterTask(task)
  } else {
    syncLoginTask(task)
  }
}

const shouldKeepInactiveTask = (kind: TaskKind, task: RegisterTask | LoginTask) => {
  const dismissedMeta = readDismissedTaskMeta(TASK_KEYS[kind].dismissKey)
  const clearedMeta = readClearedTaskMeta(TASK_KEYS[kind].clearedKey)
  return !isTaskDismissed(task, dismissedMeta) && !isTaskMetaMatch(task, clearedMeta)
}

const loadCurrentTaskByKind = async (kind: TaskKind) => {
  try {
    const current = kind === 'register'
      ? await accountsApi.getRegisterCurrent()
      : await accountsApi.getLoginCurrent()
    if (current && 'id' in current) {
      const isActive = current.status === 'running' || current.status === 'pending'
      if (isActive) {
        handleTaskActive(kind, current)
      } else if (shouldKeepInactiveTask(kind, current)) {
        handleTaskInactive(kind, current)
      }
    } else {
      handleTaskIdle(kind)
    }
  } catch (error: any) {
    if (error?.status === 404 || error?.message === 'Not found') {
      handleTaskNotFound(kind)
    } else {
      automationError.value = error.message || (kind === 'register' ? '加载注册任务失败' : '加载刷新任务失败')
    }
  }
}

const readClearMarker = (key: string): TaskLogLine | null => {
  const raw = localStorage.getItem(key)
  if (!raw) return null

  // Backward compatibility: older versions stored numeric offsets.
  // If we see a number, ignore it so logs still render.
  const asNumber = Number(raw)
  if (Number.isFinite(asNumber)) return null

  try {
    const parsed = JSON.parse(raw) as Partial<TaskLogLine> | null
    if (!parsed || typeof parsed !== 'object') return null
    if (typeof parsed.time !== 'string' || typeof parsed.level !== 'string' || typeof parsed.message !== 'string') {
      return null
    }
    return { time: parsed.time, level: parsed.level, message: parsed.message }
  } catch {
    return null
  }
}

const writeClearMarker = (key: string, value: TaskLogLine | null) => {
  try {
    if (!value) {
      localStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore storage errors
  }
}

const syncRegisterTask = (task: RegisterTask | null, persist = true) => {
  if (!task) {
    registerTask.value = null
    lastRegisterTaskId.value = null
    registerLogClearMarker.value = null
    if (persist) {
      removeCachedTask(REGISTER_TASK_CACHE_KEY)
      writeClearMarker(REGISTER_CLEAR_KEY, null)
    }
    return
  }

  registerTask.value = task
  if (task.id && task.id !== lastRegisterTaskId.value) {
    lastRegisterTaskId.value = task.id
    writeDismissedTaskMeta(REGISTER_DISMISS_KEY, null)
    writeClearedTaskMeta(REGISTER_CLEARED_KEY, null)
    setLogClearMarker('register', null)
    writeClearMarker(REGISTER_CLEAR_KEY, null)
    // 新注册任务启动时，自动清理已结束的刷新任务，避免堆叠显示
    clearFinishedTask('login')
  }
  if (persist) {
    writeCachedTask(REGISTER_TASK_CACHE_KEY, task)
  }
}

const syncLoginTask = (task: LoginTask | null, persist = true) => {
  if (!task) {
    loginTask.value = null
    lastLoginTaskId.value = null
    loginLogClearMarker.value = null
    if (persist) {
      removeCachedTask(LOGIN_TASK_CACHE_KEY)
      writeClearMarker(LOGIN_CLEAR_KEY, null)
    }
    return
  }

  loginTask.value = task
  if (task.id && task.id !== lastLoginTaskId.value) {
    lastLoginTaskId.value = task.id
    writeDismissedTaskMeta(LOGIN_DISMISS_KEY, null)
    writeClearedTaskMeta(LOGIN_CLEARED_KEY, null)
    setLogClearMarker('login', null)
    writeClearMarker(LOGIN_CLEAR_KEY, null)
    // 新刷新任务启动时，自动清理已结束的注册任务，避免堆叠显示
    clearFinishedTask('register')
  }
  if (persist) {
    writeCachedTask(LOGIN_TASK_CACHE_KEY, task)
  }
}

const hydrateTaskCache = () => {
  registerLogClearMarker.value = readClearMarker(REGISTER_CLEAR_KEY)
  loginLogClearMarker.value = readClearMarker(LOGIN_CLEAR_KEY)
  const cachedRegister = readCachedTask<RegisterTask>(REGISTER_TASK_CACHE_KEY)
  if (cachedRegister) {
    const dismissedMeta = readDismissedTaskMeta(TASK_KEYS.register.dismissKey)
    const clearedMeta = readClearedTaskMeta(TASK_KEYS.register.clearedKey)
    if (!isTaskDismissed(cachedRegister, dismissedMeta) && !isTaskMetaMatch(cachedRegister, clearedMeta)) {
      registerTask.value = cachedRegister
      lastRegisterTaskId.value = cachedRegister.id || null
    }
  }
  const cachedLogin = readCachedTask<LoginTask>(LOGIN_TASK_CACHE_KEY)
  if (cachedLogin) {
    const dismissedMeta = readDismissedTaskMeta(TASK_KEYS.login.dismissKey)
    const clearedMeta = readClearedTaskMeta(TASK_KEYS.login.clearedKey)
    if (!isTaskDismissed(cachedLogin, dismissedMeta) && !isTaskMetaMatch(cachedLogin, clearedMeta)) {
      loginTask.value = cachedLogin
      lastLoginTaskId.value = cachedLogin.id || null
    }
  }
}

const cleanupCancelledTasks = () => {
  // Keep completed/cancelled task logs; do not auto-clear.
}

const openRegisterModal = () => {
  isRegisterOpen.value = true
  addMode.value = 'register'
  importText.value = ''
  importError.value = ''
  isImporting.value = false
  importFileName.value = ''
  // 重置为设置中的邮箱服务提供商
  selectedMailProvider.value = settings.value?.basic?.temp_mail_provider || defaultMailProvider
}

const openExportModal = (format: 'json' | 'txt' = 'json') => {
  exportFormat.value = format
  exportScope.value = 'all'
  isExportOpen.value = true
}

const closeExportModal = () => {
  isExportOpen.value = false
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

    if (parts[0].toLowerCase() === 'moemail') {
      if (parts.length < 3 || !parts[1] || !parts[2]) {
        errors.push(`第 ${lineNo} 行格式错误（moemail）`)
        return
      }
      const email = parts[1]
      const emailId = parts[2]  // moemail 的 email_id 作为 password 存储
      items.push({
        id: email,
        secure_c_ses: '',
        csesidx: '',
        config_id: '',
        expires_at: IMPORT_EXPIRES_AT,
        mail_provider: 'moemail',
        mail_address: email,
        mail_password: emailId,
      })
      return
    }

    if (parts[0].toLowerCase() === 'freemail') {
      if (parts.length < 2 || !parts[1]) {
        errors.push(`第 ${lineNo} 行格式错误（freemail）`)
        return
      }
      const email = parts[1]

      // 完整格式：freemail----email----base_url----jwt_token----verify_ssl----domain
      if (parts.length >= 6) {
        items.push({
          id: email,
          secure_c_ses: '',
          csesidx: '',
          config_id: '',
          expires_at: IMPORT_EXPIRES_AT,
          mail_provider: 'freemail',
          mail_address: email,
          mail_password: '',
          mail_base_url: parts[2] || undefined,
          mail_jwt_token: parts[3] || undefined,
          mail_verify_ssl: parts[4] === 'true' || parts[4] === '1',
          mail_domain: parts[5] || undefined,
        })
        return
      }

      // 简化格式：freemail----email
      items.push({
        id: email,
        secure_c_ses: '',
        csesidx: '',
        config_id: '',
        expires_at: IMPORT_EXPIRES_AT,
        mail_provider: 'freemail',
        mail_address: email,
        mail_password: '',
      })
      return
    }

    if (parts[0].toLowerCase() === 'gptmail') {
      if (parts.length < 2 || !parts[1]) {
        errors.push(`第 ${lineNo} 行格式错误（gptmail）`)
        return
      }
      const email = parts[1]
      items.push({
        id: email,
        secure_c_ses: '',
        csesidx: '',
        config_id: '',
        expires_at: IMPORT_EXPIRES_AT,
        mail_provider: 'gptmail',
        mail_address: email,
        mail_password: '',
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

const triggerImportFile = () => {
  importFileInput.value?.click()
}

const handleImportFile = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  importError.value = ''
  importFileName.value = file.name

  try {
    const content = await file.text()
    if (file.name.toLowerCase().endsWith('.json') || file.type.includes('json')) {
      const parsed = JSON.parse(content)
      const importList = Array.isArray(parsed) ? parsed : parsed?.accounts
      if (!Array.isArray(importList)) {
        importError.value = 'JSON 格式错误：需要数组或包含 accounts 字段'
        return
      }
      const existing = await loadConfigList()
      const next = [...existing]
      const indexMap = new Map(next.map((acc, idx) => [acc.id, idx]))
      const importedIds: string[] = []

      importList.forEach((item: any) => {
        const idx = indexMap.get(item.id || '')
        if (idx === undefined) {
          next.push(item)
        } else {
          next[idx] = { ...next[idx], ...item }
        }
        if (item.id) importedIds.push(item.id)
      })

      await accountsStore.updateConfig(next)
      selectedIds.value = new Set(importedIds)
      toast.success(`导入 ${importList.length} 条账号配置`)
      closeRegisterModal()
      return
    }

    importText.value = content
    await handleImport()
  } catch (error: any) {
    importError.value = error.message || '文件解析失败'
  } finally {
    target.value = ''
  }
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

const exportConfig = async (format: 'json' | 'txt', scope: 'all' | 'selected' = 'all') => {
  try {
    const response = await accountsApi.getConfig()
    let list = Array.isArray(response.accounts) ? response.accounts : []
    if (scope === 'selected') {
      const selected = selectedIds.value
      list = list.filter((item) => selected.has(item.id))
    }
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')

    if (format === 'json') {
      const payload = JSON.stringify(list, null, 2)
      downloadText(payload, `accounts-${timestamp}.json`, 'application/json')
      toast.success('导出 JSON 成功')
      return
    }

    const lines = list.map((item) => {
      const provider = (item.mail_provider || '').toLowerCase()
      const email = item.mail_address || item.id || ''
      if (!email) return ''
      if (provider === 'moemail') {
        return `moemail----${email}----${item.mail_password || ''}`
      }
      if (provider === 'freemail') {
        return `freemail----${email}`
      }
      if (provider === 'gptmail') {
        return `gptmail----${email}`
      }
      if (provider === 'duckmail') {
        return `duckmail----${email}----${item.mail_password || ''}`
      }
      if (provider === 'microsoft' || item.mail_client_id || item.mail_refresh_token) {
        return `${email}----${item.mail_password || ''}----${item.mail_client_id || ''}----${item.mail_refresh_token || ''}`
      }
      if (item.mail_password) {
        return `duckmail----${email}----${item.mail_password}`
      }
      return email
    }).filter(Boolean)

    downloadText(lines.join('\n'), `accounts-${timestamp}.txt`, 'text/plain')
    toast.success('导出 TXT 成功')
  } catch (error: any) {
    toast.error(error.message || '导出失败')
  }
}

const runExport = async () => {
  await exportConfig(exportFormat.value, exportScope.value)
  closeExportModal()
}

const downloadText = (content: string, filename: string, mime: string) => {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const refreshTaskSnapshot = async () => {
  try {
    const tasks: Promise<void>[] = []
    const registerId = registerTask.value?.id
    const loginId = loginTask.value?.id

    if (registerId) {
      tasks.push(updateRegisterTask(registerId))
    }
    if (loginId) {
      tasks.push(updateLoginTask(loginId))
    }

    if (!tasks.length) {
      await loadCurrentTasks()
    } else {
      await Promise.all(tasks)
    }

    cleanupCancelledTasks()
  } catch (error: any) {
    automationError.value = error?.message || '任务状态更新失败'
  }
}

const openTaskModal = async () => {
  isTaskOpen.value = true
  activeTaskTab.value = 'current'
  await refreshTaskSnapshot()
}

const fetchTaskHistory = async () => {
  isLoadingHistory.value = true
  try {
    const response = await fetch('/admin/task-history', {
      headers: { 'Content-Type': 'application/json' }
    })
    if (!response.ok) throw new Error('获取历史记录失败')
    const data = await response.json()
    const history = Array.isArray(data.history) ? data.history : []
    const dismissedRegister = readDismissedTaskMeta(REGISTER_DISMISS_KEY)
    const dismissedLogin = readDismissedTaskMeta(LOGIN_DISMISS_KEY)
    taskHistory.value = history.filter((record: any) => {
      const meta = record?.type === 'register' ? dismissedRegister : dismissedLogin
      if (!meta) return true
      const id = typeof record?.id === 'string' ? record.id : String(record?.id || '')
      const createdAt = typeof record?.created_at === 'number' ? record.created_at : undefined
      if (meta.id && id && id === meta.id) return false
      if (typeof meta.created_at === 'number' && typeof createdAt === 'number' && createdAt === meta.created_at) {
        return false
      }
      return true
    })
  } catch (error: any) {
    toast.error(error?.message || '获取历史记录失败')
  } finally {
    isLoadingHistory.value = false
  }
}

const clearTaskHistory = async () => {
  const confirmed = await confirmDialog.ask({
    title: '清空历史记录',
    message: '确定要清空所有任务历史记录吗？',
    confirmText: '清空',
  })
  if (!confirmed) return
  try {
    const response = await fetch('/admin/task-history?confirm=yes', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' }
    })
    if (!response.ok) throw new Error('清空历史记录失败')
    taskHistory.value = []
    toast.success('历史记录已清空')
  } catch (error: any) {
    toast.error(error?.message || '清空历史记录失败')
  }
}

const closeTaskModal = () => {
  isTaskOpen.value = false
  // 关闭弹窗时，确保已中断任务不会被缓存"复活"
  cleanupCancelledTasks()
}

const loadScheduledConfig = async () => {
  isLoadingScheduledConfig.value = true
  try {
    const settings = await settingsApi.get()
    cachedSettings.value = settings  // 缓存配置
    scheduledRefreshEnabled.value = settings.retry.scheduled_refresh_enabled ?? false
    scheduledRefreshInterval.value = settings.retry.scheduled_refresh_interval_minutes ?? 30
    refreshWindowHours.value = settings.basic.refresh_window_hours ?? 24
  } catch (error: any) {
    toast.error(error?.message || '加载定时任务配置失败')
  } finally {
    isLoadingScheduledConfig.value = false
  }
}

const saveScheduledConfig = async () => {
  // 验证检测间隔
  if (isNaN(scheduledRefreshInterval.value) || !Number.isInteger(scheduledRefreshInterval.value)) {
    toast.error('检测间隔必须是有效的整数')
    return
  }
  if (scheduledRefreshInterval.value < 0 || scheduledRefreshInterval.value > 720) {
    toast.error('检测间隔必须在 0-720 分钟之间（0-12 小时）')
    return
  }

  // 验证过期刷新窗口
  if (isNaN(refreshWindowHours.value) || !Number.isInteger(refreshWindowHours.value)) {
    toast.error('过期刷新窗口必须是有效的整数')
    return
  }
  if (refreshWindowHours.value < 1 || refreshWindowHours.value > 168) {
    toast.error('过期刷新窗口必须在 1-168 小时之间')
    return
  }

  isSavingScheduledConfig.value = true
  try {
    // 使用缓存的配置，避免重复API调用
    const settings = cachedSettings.value || await settingsApi.get()
    settings.retry.scheduled_refresh_enabled = scheduledRefreshEnabled.value
    settings.retry.scheduled_refresh_interval_minutes = scheduledRefreshInterval.value
    settings.basic.refresh_window_hours = refreshWindowHours.value
    await settingsApi.update(settings)
    cachedSettings.value = settings  // 更新缓存
    toast.success('定时任务配置已保存')
  } catch (error: any) {
    toast.error(error?.message || '保存定时任务配置失败')
  } finally {
    isSavingScheduledConfig.value = false
  }
}

const clearTaskLogs = async () => {
  const confirmed = await confirmDialog.ask({
    title: '清空当前日志',
    message: '确定要清空当前任务日志吗？',
    confirmText: '清空',
  })
  if (!confirmed) return
  const clearLogsFor = (kind: TaskKind) => {
    const task = getTaskByKind(kind)
    if (!task) return
    if (!isTaskActive(task)) {
      markTaskCleared(kind, task)
      clearTaskSnapshot(kind, true)
      return
    }
    const logs = (task.logs || []) as TaskLogLine[]
    if (!logs.length) return
    const marker = logs[logs.length - 1]
    setLogClearMarker(kind, marker)
    writeClearMarker(TASK_KEYS[kind].clearKey, marker)
  }

  clearLogsFor('register')
  clearLogsFor('login')

  automationError.value = ''
  toast.success('当前日志已清空')
}

const filterLogsAfterMarker = (logs: TaskLogLine[], marker: TaskLogLine | null) => {
  if (!marker) return logs
  for (let i = logs.length - 1; i >= 0; i -= 1) {
    const item = logs[i]
    if (item.time === marker.time && item.level === marker.level && item.message === marker.message) {
      return logs.slice(i + 1)
    }
  }
  // Marker not found (e.g., backend truncates to last N logs) — show current logs so new logs keep appearing.
  return logs
}

const cancelRegister = async (taskId: string) => {
  try {
    await accountsApi.cancelRegisterTask(taskId, 'cancelled_by_user')
    await refreshTaskSnapshot()
    toast.success('已请求中断注册任务')
  } catch (error: any) {
    toast.error(error?.message || '中断注册任务失败')
  }
}

const cancelLogin = async (taskId: string) => {
  try {
    await accountsApi.cancelLoginTask(taskId, 'cancelled_by_user')
    await refreshTaskSnapshot()
    toast.success('已请求中断刷新任务')
  } catch (error: any) {
    toast.error(error?.message || '中断刷新任务失败')
  }
}

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

// 监听标签页切换，自动加载历史记录
watch(activeTaskTab, async (newTab) => {
  if (newTab === 'history') {
    await fetchTaskHistory()
  } else if (newTab === 'scheduled') {
    await loadScheduledConfig()
  }
})

onMounted(async () => {
  hydrateTaskCache()
  await refreshAccounts()
  await loadCurrentTasks()
  startBackgroundTaskPolling()
  document.addEventListener('click', handleMoreActionsClick)
})

const registerLogs = computed(() => {
  const logs = registerTask.value?.logs || []
  return filterLogsAfterMarker(logs as TaskLogLine[], registerLogClearMarker.value)
})
const loginLogs = computed(() => {
  const logs = loginTask.value?.logs || []
  return filterLogsAfterMarker(logs as TaskLogLine[], loginLogClearMarker.value)
})
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

const taskProgressText = computed(() => {
  const register = registerTask.value
  const login = loginTask.value
  const registerActive = register?.status === 'running' || register?.status === 'pending'
  const loginActive = login?.status === 'running' || login?.status === 'pending'

  if (registerActive && loginActive) {
    return `注册 ${register.progress}/${register.count} | 刷新 ${login.progress}/${login.account_ids.length}`
  }
  if (registerActive) {
    return `注册 ${register.progress}/${register.count}`
  }
  if (loginActive) {
    return `刷新 ${login.progress}/${login.account_ids.length}`
  }
  return ''
})

onBeforeUnmount(() => {
  clearRegisterTimer()
  clearLoginTimer()
  clearBackgroundTaskTimer()
  document.removeEventListener('click', handleMoreActionsClick)
})

const statusLabel = (account: AdminAccount) => {
  // 检查是否正在刷新
  if (refreshingAccountIds.value.has(account.id)) {
    return '刷新中'
  }
  if (account.cooldown_reason?.includes('429') && account.cooldown_seconds > 0) {
    return '429限流'
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
  if (status === '刷新中') {
    return 'bg-sky-500 text-white'
  }
  if (status === '429限流' || status === '即将过期') {
    return 'bg-amber-200 text-amber-900'
  }
  if (status === '已过期') {
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
  return account.disabled
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

const formatOpErrors = (errors: string[]) => {
  if (!errors.length) return ''
  const sample = errors[0]
  return `失败 ${errors.length} 个${sample ? `，示例：${sample}` : ''}`
}

const handleOpResult = (result: { ok: boolean; errors: string[] }, successMessage: string, failMessage: string) => {
  if (result.ok) {
    toast.success(successMessage)
    return true
  }
  const detail = formatOpErrors(result.errors)
  toast.error(detail ? `${failMessage}（${detail}）` : failMessage)
  return false
}

const handleBulkEnable = async () => {
  if (isOperating.value) return
  try {
    const result = await accountsStore.bulkEnable(Array.from(selectedIds.value))
    if (handleOpResult(result, '批量启用成功', '批量启用失败')) {
      selectedIds.value = new Set()
    }
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
  if (isOperating.value) return
  try {
    const result = await accountsStore.bulkDisable(Array.from(selectedIds.value))
    if (handleOpResult(result, '批量禁用成功', '批量禁用失败')) {
      selectedIds.value = new Set()
    }
  } catch (error: any) {
    toast.error(error.message || '批量禁用失败')
  }
}

const handleBulkDelete = async () => {
  if (isOperating.value) return
  const confirmed = await confirmDialog.ask({
    title: '批量删除',
    message: '确定要批量删除选中的账号吗？',
    confirmText: '删除',
  })
  if (!confirmed) return
  try {
    const result = await accountsStore.bulkDelete(Array.from(selectedIds.value))
    if (handleOpResult(result, '批量删除成功', '批量删除失败')) {
      selectedIds.value = new Set()
    }
  } catch (error: any) {
    toast.error(error.message || '批量删除失败')
  }
}

const handleEnable = async (accountId: string) => {
  if (isOperating.value) return
  try {
    const result = await accountsStore.enableAccount(accountId)
    handleOpResult(result, '账号已启用', '启用失败')
  } catch (error: any) {
    toast.error(error.message || '启用失败')
  }
}

const handleDisable = async (accountId: string) => {
  if (isOperating.value) return
  const confirmed = await confirmDialog.ask({
    title: '禁用账号',
    message: '确定要禁用该账号吗？',
  })
  if (!confirmed) return
  try {
    const result = await accountsStore.disableAccount(accountId)
    handleOpResult(result, '账号已禁用', '禁用失败')
  } catch (error: any) {
    toast.error(error.message || '禁用失败')
  }
}

const handleDelete = async (accountId: string) => {
  if (isOperating.value) return
  const confirmed = await confirmDialog.ask({
    title: '删除账号',
    message: '确定要删除该账号吗？',
    confirmText: '删除',
  })
  if (!confirmed) return
  try {
    const result = await accountsStore.deleteAccount(accountId)
    handleOpResult(result, '账号已删除', '删除失败')
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

const getTaskResultType = (
  status: string,
  success: number,
  fail: number,
  total?: number,
) => {
  if (status === 'pending' || status === 'running' || status === 'cancelled') return status
  const s = Number.isFinite(success) ? success : 0
  const f = Number.isFinite(fail) ? fail : 0
  const t = Number.isFinite(total) ? total : s + f
  if (s > 0 && f > 0) return 'partial'
  if (s > 0 && f === 0) return 'success'
  if (f > 0 && s === 0) return 'failed'
  if (t === 0) return 'none'
  return 'none'
}

const formatTaskStatus = (task: any) => {
  const status = task?.status || ''
  const success = task?.success_count ?? 0
  const fail = task?.fail_count ?? 0
  const total = Number.isFinite(task?.total) ? task.total : undefined
  const result = getTaskResultType(status, success, fail, total)
  if (result === 'pending') return '等待中'
  if (result === 'running') return '执行中'
  if (result === 'cancelled') return '已中断'
  if (result === 'success') return '已完成（全部成功）'
  if (result === 'failed') return '已完成（全部失败）'
  if (result === 'partial') return '已完成（部分失败）'
  return '已完成'
}

const getHistoryTotal = (record: any) => {
  const total = Number.isFinite(record?.total) ? record.total : undefined
  if (typeof total === 'number') return total
  const progress = Number.isFinite(record?.progress) ? record.progress : 0
  return progress
}

const getHistoryStatusTextClass = (record: any) => {
  const status = record?.status
  const success = record?.success_count ?? 0
  const fail = record?.fail_count ?? 0
  const total = getHistoryTotal(record)
  const result = getTaskResultType(status, success, fail, total)
  if (result === 'running' || result === 'pending') return 'text-sky-600'
  if (result === 'success') return 'text-emerald-600'
  if (result === 'failed') return 'text-rose-600'
  if (result === 'partial') return 'text-amber-600'
  if (result === 'cancelled') return 'text-muted-foreground'
  return 'text-muted-foreground'
}

const getHistoryStatusIndicatorClass = (record: any) => {
  const status = record?.status
  const success = record?.success_count ?? 0
  const fail = record?.fail_count ?? 0
  const total = getHistoryTotal(record)
  const result = getTaskResultType(status, success, fail, total)
  if (result === 'running' || result === 'pending') return 'bg-sky-400'
  if (result === 'success') return 'bg-emerald-400'
  if (result === 'failed') return 'bg-rose-500'
  if (result === 'partial') return 'bg-amber-400'
  return 'bg-muted-foreground'
}

const getTaskStatusIndicatorClass = (task: RegisterTask | LoginTask) => {
  const status = task.status
  const success = task.success_count ?? 0
  const fail = task.fail_count ?? 0
  const total = 'count' in task ? task.count : task.account_ids?.length
  const result = getTaskResultType(status, success, fail, total)
  if (result === 'running' || result === 'pending') return 'bg-sky-400'
  if (result === 'success') return 'bg-emerald-400'
  if (result === 'failed') return 'bg-rose-500'
  if (result === 'partial') return 'bg-amber-400'
  return 'bg-muted-foreground'
}

const updateRegisterTask = async (taskId: string) => {
  let task: RegisterTask
  try {
    task = await accountsApi.getRegisterTask(taskId)
  } catch (error: any) {
    // 任务已不存在（被清理/过期/后端重启）：静默清理，避免弹窗显示 "Not found"
    if (error?.status === 404 || error?.message === 'Not found') {
      clearRegisterTimer()
      isRegistering.value = false
      return
    }
    throw error
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

    await fetchTaskHistory()
    return
  }
}

const updateLoginTask = async (taskId: string) => {
  let task: LoginTask
  try {
    task = await accountsApi.getLoginTask(taskId)
  } catch (error: any) {
    // 任务已不存在（被清理/过期/后端重启）：静默清理，避免弹窗显示 "Not found"
    if (error?.status === 404 || error?.message === 'Not found') {
      clearLoginTimer()
      isRefreshing.value = false
      refreshingAccountIds.value = new Set()  // 清空刷新状态
      return
    }
    throw error
  }
  syncLoginTask(task)

  // 更新正在刷新的账户列表
  if (task.status === 'running' || task.status === 'pending') {
    refreshingAccountIds.value = new Set(task.account_ids || [])
  } else {
    refreshingAccountIds.value = new Set()  // 任务完成，清空刷新状态
  }

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

    await fetchTaskHistory()
    return
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
  await loadCurrentTaskByKind('register')
  await loadCurrentTaskByKind('login')
}

const handleRegister = async () => {
  automationError.value = ''
  isRegistering.value = true
  try {
    const count = Number.isFinite(registerCount.value) && registerCount.value > 0
      ? registerCount.value
      : undefined
    const task = await accountsApi.startRegister(count, undefined, selectedMailProvider.value)
    syncRegisterTask(task)
    startRegisterPolling(task.id)
    isRegisterOpen.value = false
    isTaskOpen.value = true
  } catch (error: any) {
    automationError.value = error.message || '启动注册失败'
    isRegistering.value = false
  }
}

// 统一的刷新函数 - 所有刷新入口都调用这个
const startRefresh = async (accountIds: string[]) => {
  if (!accountIds.length) return
  automationError.value = ''
  isRefreshing.value = true
  try {
    const task = await accountsApi.startLogin(accountIds)
    syncLoginTask(task)
    // 更新正在刷新的账户列表
    refreshingAccountIds.value = new Set(task.account_ids || [])
    startLoginPolling(task.id)
    // 自动打开任务状态弹窗
    openTaskModal()
  } catch (error: any) {
    automationError.value = error.message || '启动刷新失败'
    toast.error(error.message || '启动刷新失败')
    isRefreshing.value = false
  }
}

const handleRefreshSelected = async () => {
  if (!selectedIds.value.size) return
  await startRefresh(Array.from(selectedIds.value))
}

const handleRefreshExpiring = async () => {
  automationError.value = ''
  isRefreshing.value = true
  try {
    const taskOrIdle = await accountsApi.checkLogin()
    if (taskOrIdle && 'id' in taskOrIdle) {
      syncLoginTask(taskOrIdle)
      // 更新正在刷新的账户列表
      refreshingAccountIds.value = new Set(taskOrIdle.account_ids || [])
      startLoginPolling(taskOrIdle.id)
      // 自动打开任务状态弹窗
      openTaskModal()
      return
    }
    // 没有新任务时，尝试读取当前任务（可能已有 running/pending）
    const current = await accountsApi.getLoginCurrent()
    if (current && 'id' in current) {
      syncLoginTask(current)
      // 更新正在刷新的账户列表
      refreshingAccountIds.value = new Set(current.account_ids || [])
      startLoginPolling(current.id)
      openTaskModal()
      return
    }
    isRefreshing.value = false
  } catch (error: any) {
    automationError.value = error.message || '触发刷新失败'
    toast.error(error.message || '触发刷新失败')
    isRefreshing.value = false
  }
}
</script>

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

    <section class="ui-panel space-y-5">
      <div class="flex flex-wrap items-center gap-2.5">
        <Input
          :model-value="searchQuery"
          type="text"
          placeholder="搜索账号 ID"
          block
          root-class="min-w-[11rem] flex-1 md:w-80 md:flex-none"
          @update:model-value="searchQuery = $event.trim()"
        />
        <div class="w-[140px] shrink-0">
          <SelectMenu v-model="statusFilter" :options="statusOptions" />
        </div>
      </div>

      <div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div class="flex flex-wrap items-center gap-2.5">
          <Button
            size="sm"
            variant="outline"
            root-class="shrink-0 whitespace-nowrap"
            :disabled="isLoading"
            @click="refreshAccounts"
          >
            刷新列表
          </Button>
          <Button
            size="sm"
            variant="primary"
            root-class="shrink-0 whitespace-nowrap"
            :disabled="isRegistering || isRefreshing"
            @click="openRegisterModal"
          >
            添加账户
          </Button>
          <Button
            size="sm"
            variant="outline"
            root-class="shrink-0 whitespace-nowrap"
            @click="openConfigPanel"
          >
            账户配置
          </Button>
          <Button
            size="sm"
            variant="outline"
            root-class="relative shrink-0 whitespace-nowrap"
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
          </Button>
          <div class="w-[140px] shrink-0">
            <button
              ref="moreActionsTriggerRef"
              type="button"
              class="ui-input-sm flex w-full items-center justify-between gap-2 text-foreground hover:border-primary"
              :class="showMoreActions ? 'border-primary' : ''"
              @click="toggleMoreActions"
            >
              <span class="truncate">更多操作</span>
              <svg aria-hidden="true" viewBox="0 0 20 20" class="h-4 w-4 shrink-0" fill="currentColor">
                <path d="M5 7l5 6 5-6H5z" />
              </svg>
            </button>
          </div>
          <Teleport to="body">
            <div
              v-if="showMoreActions"
              ref="moreActionsMenuRef"
              class="ui-floating-panel fixed z-[120] space-y-1"
              :style="moreActionsMenuStyle"
            >
              <button
                type="button"
                class="ui-menu-item"
                @click="triggerImportFile(); closeMoreActions()"
              >
                导入文件
              </button>
              <button
                type="button"
                class="ui-menu-item"
                @click="openExportModal(); closeMoreActions()"
              >
                导出账户
              </button>
              <div class="my-1 border-t border-border/60"></div>
              <button
                type="button"
                class="ui-menu-item transition-colors"
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
                class="ui-menu-item transition-colors"
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
                class="ui-menu-item transition-colors"
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
                class="ui-menu-item transition-colors"
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
                class="ui-menu-item transition-colors"
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
          </Teleport>
        </div>

        <div class="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <Checkbox :modelValue="allSelected" @update:modelValue="toggleSelectAll">
            全选当前结果
          </Checkbox>
          <span class="rounded-full border border-border bg-muted/30 px-3 py-1.5">
            账号总数 {{ filteredAccounts.length }}
          </span>
          <span class="rounded-full border border-border bg-muted/30 px-3 py-1.5">
            已选 {{ selectedCount }}
          </span>
          <div class="flex items-center gap-2">
            <button
              class="flex h-8 w-8 items-center justify-center rounded-full border transition-colors"
              :class="viewMode === 'table'
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground'"
              @click="viewMode = 'table'"
              title="列表视图"
              aria-label="列表视图"
            >
              <svg viewBox="0 0 20 20" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
                <path d="M4 5.5h12" />
                <path d="M4 10h12" />
                <path d="M4 14.5h12" />
              </svg>
            </button>
            <button
              class="flex h-8 w-8 items-center justify-center rounded-full border transition-colors"
              :class="viewMode === 'card'
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground'"
              @click="viewMode = 'card'"
              title="卡片视图"
              aria-label="卡片视图"
            >
              <svg viewBox="0 0 20 20" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3.5" y="3.5" width="5.5" height="5.5" rx="1" />
                <rect x="11" y="3.5" width="5.5" height="5.5" rx="1" />
                <rect x="3.5" y="11" width="5.5" height="5.5" rx="1" />
                <rect x="11" y="11" width="5.5" height="5.5" rx="1" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div v-if="viewMode === 'card'" class="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="account in paginatedAccounts"
          :key="account.id"
          class="ui-card"
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
              <p class="mt-1 flex flex-wrap items-center gap-1.5 text-sm font-semibold text-foreground">
                <span
                  class="inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs"
                  :class="statusClass(account)"
                >
                  {{ statusLabel(account) }}
                </span>
                <span
                  v-if="account.trial_days_remaining != null"
                  class="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs font-medium"
                  :class="trialBadgeClass(account.trial_days_remaining)"
                >
                  <svg class="h-3 w-3 shrink-0" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                    <path d="M5 1a1 1 0 0 1 1 1v.5h4V2a1 1 0 0 1 2 0v.5h1A1.5 1.5 0 0 1 14.5 4v9A1.5 1.5 0 0 1 13 14.5H3A1.5 1.5 0 0 1 1.5 13V4A1.5 1.5 0 0 1 3 2.5h1V2a1 1 0 0 1 1-1zm-2 4v1.5h10V5H3zm0 3v5h10V8H3z"/>
                  </svg>
                  {{ account.trial_days_remaining }}天
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
            <Button
              size="xs"
              variant="outline"
              @click.stop="openEdit(account.id)"
            >
              编辑
            </Button>
            <Button
              v-if="shouldShowEnable(account)"
              size="xs"
              variant="outline"
              @click.stop
              @click="handleEnable(account.id)"
            >
              启用
            </Button>
            <Button
              v-else
              size="xs"
              variant="outline"
              @click.stop
              @click="handleDisable(account.id)"
            >
              禁用
            </Button>
            <Button
              size="xs"
              variant="danger"
              @click.stop
              @click="handleDelete(account.id)"
            >
              删除
            </Button>
          </div>
        </div>
        <div v-if="!filteredAccounts.length && !isLoading" class="rounded-2xl border border-border bg-background p-4 text-center text-xs text-muted-foreground">
          暂无账号数据，请检查后台配置。
        </div>
      </div>

      <div v-else class="scrollbar-slim relative mt-6 overflow-x-auto">
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
                <div class="flex flex-wrap items-center gap-1.5">
                  <span
                    class="inline-flex items-center rounded-full border border-border px-3 py-1 text-xs"
                    :class="statusClass(account)"
                  >
                    {{ statusLabel(account) }}
                  </span>
                  <span
                    v-if="account.trial_days_remaining != null"
                    class="inline-flex items-center gap-1 rounded-full border border-border px-2 py-1 text-xs font-medium"
                    :class="trialBadgeClass(account.trial_days_remaining)"
                  >
                    <svg class="h-3 w-3 shrink-0" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                      <path d="M5 1a1 1 0 0 1 1 1v.5h4V2a1 1 0 0 1 2 0v.5h1A1.5 1.5 0 0 1 14.5 4v9A1.5 1.5 0 0 1 13 14.5H3A1.5 1.5 0 0 1 1.5 13V4A1.5 1.5 0 0 1 3 2.5h1V2a1 1 0 0 1 1-1zm-2 4v1.5h10V5H3zm0 3v5h10V8H3z"/>
                    </svg>
                    {{ account.trial_days_remaining }}天
                  </span>
                </div>
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
                  <Button
                    size="xs"
                    variant="outline"
                    @click.stop="openEdit(account.id)"
                  >
                    编辑
                  </Button>
                  <Button
                    v-if="shouldShowEnable(account)"
                    size="xs"
                    variant="outline"
                    @click.stop="handleEnable(account.id)"
                  >
                    启用
                  </Button>
                  <Button
                    v-else
                    size="xs"
                    variant="outline"
                    @click.stop="handleDisable(account.id)"
                  >
                    禁用
                  </Button>
                  <Button
                    size="xs"
                    variant="danger"
                    @click.stop="handleDelete(account.id)"
                  >
                    删除
                  </Button>
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
          <Button
            size="sm"
            variant="outline"
            :disabled="currentPage === 1"
            @click="currentPage--"
          >
            上一页
          </Button>
          <span class="text-sm text-muted-foreground">{{ currentPage }} / {{ totalPages }}</span>
          <Button
            size="sm"
            variant="outline"
            :disabled="currentPage === totalPages"
            @click="currentPage++"
          >
            下一页
          </Button>
        </div>
      </div>
    </section>
  </div>
  <Teleport to="body">
    <div v-if="isRegisterOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="ui-surface flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden">
        <div class="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <p class="text-sm font-medium text-foreground">添加账户</p>
            <p class="mt-1 text-xs text-muted-foreground">
              {{ addMode === 'register' ? '创建临时邮箱账号并自动注册' : '批量导入账户配置' }}
            </p>
          </div>
          <Button
            size="xs"
            variant="outline"
            root-class="min-w-14 justify-center text-muted-foreground"
            @click="closeRegisterModal"
          >
            关闭
          </Button>
        </div>

        <div class="scrollbar-slim flex-1 overflow-y-auto px-6 py-4">
          <div class="space-y-4 text-sm">
          <div class="ui-segmented text-xs">
            <button
              type="button"
              class="ui-segmented-btn flex-1 justify-center px-3 py-2"
              :class="addMode === 'register' ? 'ui-segmented-btn-active' : ''"
              @click="addMode = 'register'"
            >
              自动注册
            </button>
            <button
              type="button"
              class="ui-segmented-btn flex-1 justify-center px-3 py-2"
              :class="addMode === 'import' ? 'ui-segmented-btn-active' : ''"
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
              width="full"
            />
            <label class="block text-xs text-muted-foreground">注册数量</label>
            <Input
              v-model="registerCountInput"
              type="number"
              block
            />
            <p class="text-xs text-muted-foreground">
              注册前请确认邮箱已配置，<a href="https://github.com/Dreamy-rain/gemini-business2api?tab=readme-ov-file#-%E9%82%AE%E7%AE%B1%E6%8F%90%E4%BE%9B%E5%95%86%E9%85%8D%E7%BD%AE" target="_blank" class="text-primary hover:underline font-medium">查看邮箱配置文档</a>
            </p>
            <p class="text-xs text-muted-foreground">
              遇到注册失败、收不到验证码或刷新异常？<a href="https://github.com/Dreamy-rain/gemini-business2api/issues/46" target="_blank" class="text-primary hover:underline font-medium">查看常见问题与解决方案</a>
            </p>
          </div>

          <div v-else class="space-y-4">
            <label class="block text-xs text-muted-foreground">批量导入（每行一个）</label>
            <div class="flex items-center gap-2">
              <Button
                type="button"
                size="xs"
                variant="outline"
                root-class="text-muted-foreground"
                @click="triggerImportFile"
              >
                上传文件
              </Button>
              <span v-if="importFileName" class="text-xs text-muted-foreground">{{ importFileName }}</span>
            </div>
            <textarea
              v-model="importText"
              class="ui-textarea-sm min-h-[140px] font-mono text-xs"
              placeholder="duckmail----you@example.com----password&#10;moemail----you@moemail.app----emailId&#10;freemail----you@freemail.local&#10;gptmail----you@example.com&#10;cfmail----you@example.com----jwtToken&#10;user@outlook.com----loginPassword----clientId----refreshToken"
            ></textarea>
            <div class="ui-card-sm bg-muted/30 text-xs text-muted-foreground">
              <p>支持三种格式：</p>
              <p class="mt-1 font-mono">duckmail----email----password</p>
              <p class="mt-1 font-mono">moemail----email----emailId</p>
              <p class="mt-1 font-mono">freemail----email</p>
              <p class="mt-1 font-mono">gptmail----email</p>
              <p class="mt-1 font-mono">cfmail----email----jwtToken</p>
              <p class="mt-1 font-mono">email----password----clientId----refreshToken</p>
              <p class="mt-2">导入后请执行一次"刷新选中"以获取 Cookie。</p>
              <p class="mt-1">注册失败可先切换为 normal 或 silent 再重试</p>
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
            <Button
              size="sm"
              variant="outline"
              root-class="text-muted-foreground"
              @click="closeRegisterModal"
            >
              取消
            </Button>
            <Button
              v-if="addMode === 'register'"
              size="sm"
              variant="primary"
              :disabled="isRegistering"
              @click="handleRegister"
            >
              开始注册
            </Button>
            <Button
              v-else
              size="sm"
              variant="primary"
              :disabled="isImporting"
              @click="handleImport"
            >
              导入并保存
            </Button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="isTaskOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="ui-surface flex h-[80vh] w-full max-w-2xl flex-col overflow-hidden">
        <div class="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <p class="text-sm font-medium text-foreground">任务管理</p>
            <p class="mt-1 text-xs text-muted-foreground">管理注册与刷新任务</p>
          </div>
          <Button
            size="xs"
            variant="outline"
            root-class="min-w-14 justify-center text-muted-foreground"
            @click="closeTaskModal"
          >
            关闭
          </Button>
        </div>

        <!-- Tab 导航 -->
        <div class="border-b border-border/60 px-6 py-3">
          <div class="ui-segmented w-full max-w-md">
            <button
              type="button"
              class="ui-segmented-btn flex-1 justify-center"
              :class="activeTaskTab === 'current' ? 'ui-segmented-btn-active' : ''"
              @click="activeTaskTab = 'current'"
            >
              当前任务
            </button>
            <button
              type="button"
              class="ui-segmented-btn flex-1 justify-center"
              :class="activeTaskTab === 'scheduled' ? 'ui-segmented-btn-active' : ''"
              @click="activeTaskTab = 'scheduled'; loadScheduledConfig()"
            >
              定时任务
            </button>
            <button
              type="button"
              class="ui-segmented-btn flex-1 justify-center"
              :class="activeTaskTab === 'history' ? 'ui-segmented-btn-active' : ''"
              @click="activeTaskTab = 'history'"
            >
              历史记录
            </button>
          </div>
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
                <Button
                  v-if="registerTask.status === 'running' || registerTask.status === 'pending'"
                  size="xs"
                  variant="outline"
                  root-class="text-muted-foreground hover:border-rose-500 hover:text-rose-600"
                  @click="cancelRegister(registerTask.id)"
                >
                  中断
                </Button>
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
                <Button
                  v-if="loginTask.status === 'running' || loginTask.status === 'pending'"
                  size="xs"
                  variant="outline"
                  root-class="text-muted-foreground hover:border-rose-500 hover:text-rose-600"
                  @click="cancelLogin(loginTask.id)"
                >
                  中断
                </Button>
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
            <div class="mb-2 flex items-center justify-between gap-3">
              <p class="text-[11px] text-muted-foreground">
                {{ taskLogMode === 'summary' ? '摘要模式仅保留关键事件（开始、结束、失败、告警）。' : '详情模式显示全部日志。' }}
              </p>
              <Button
                type="button"
                size="xs"
                :variant="taskLogMode === 'summary' ? 'primary' : 'outline'"
                :root-class="taskLogMode === 'summary' ? '' : 'text-muted-foreground'"
                @click="toggleTaskLogMode"
              >
                {{ taskLogMode === 'summary' ? '摘要模式' : '详情模式' }}
              </Button>
            </div>
            <div
              ref="taskLogsRef"
              class="scrollbar-slim flex-1 overflow-y-auto ui-card-sm bg-muted/30 p-3"
            >
              <div v-if="visibleRegisterLogs.length" class="space-y-2">
                <p class="text-xs font-semibold text-foreground">注册日志</p>
                <div class="space-y-1 text-[11px] text-muted-foreground">
                  <div v-for="(log, index) in visibleRegisterLogs" :key="`reg-${index}`" class="font-mono">
                    {{ formatLogLine(log) }}
                  </div>
                </div>
              </div>
              <div v-if="visibleLoginLogs.length" class="mt-4 space-y-2">
                <p class="text-xs font-semibold text-foreground">刷新日志</p>
                <div class="space-y-1 text-[11px] text-muted-foreground">
                  <div v-for="(log, index) in visibleLoginLogs" :key="`login-${index}`" class="font-mono">
                    {{ formatLogLine(log) }}
                  </div>
                </div>
              </div>
              <div v-if="!visibleRegisterLogs.length && !visibleLoginLogs.length" class="text-xs text-muted-foreground">
                {{ registerLogs.length || loginLogs.length ? '摘要模式下暂无关键日志，可切换到详情模式查看全部日志。' : '日志已清空，新的日志会继续显示。' }}
              </div>
            </div>
          </div>

          <div
            v-if="!automationError && !registerTask && !loginTask && !registerLogs.length && !loginLogs.length"
            class="flex-1 px-6 py-4"
          >
            <div class="ui-card-sm bg-muted/30 text-xs text-muted-foreground">
              暂无任务
            </div>
          </div>

          <!-- 固定底部按钮区域 -->
          <div class="flex items-center justify-end gap-2 border-t border-border/60 px-6 py-4">
            <Button
              size="sm"
              variant="outline"
              root-class="text-muted-foreground"
              :disabled="!registerLogs.length && !loginLogs.length && !registerTask && !loginTask && !automationError"
              @click="clearTaskLogs"
            >
              清空日志
            </Button>
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
                        <p class="mt-1 text-xs text-muted-foreground">自动检测并一次性刷新即将过期的账号</p>
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
                      <label class="block text-xs text-muted-foreground">刷新时间</label>
                      <Input
                        v-model="scheduledRefreshCron"
                        type="text"
                        block
                        placeholder="08:00,20:00"
                      />
                      <p class="text-xs text-muted-foreground">
                        支持两种格式，任选其一：<br>
                        <b>① 每天定时</b>：填写时间点，如 <code>08:00,20:00</code> 表示每天 8 点和 20 点各刷新一次，多个时间用逗号分隔<br>
                        <b>② 固定间隔</b>：填写 <code>*/分钟数</code>，如 <code>*/120</code> 表示每隔 2 小时刷新一次
                      </p>
                    </div>

                    <div class="space-y-2">
                      <label class="block text-xs text-muted-foreground">冷却时间(小时)</label>
                      <Input
                        v-model="refreshCooldownHoursInput"
                        type="number"
                        block
                      />
                    </div>

                    <div class="space-y-2">
                      <label class="block text-xs text-muted-foreground">验证码重发次数</label>
                      <Input
                        v-model="verificationCodeResendCountInput"
                        type="number"
                        block
                      />
                      <p class="text-xs text-muted-foreground">
                        验证码首次等待超时后，额外尝试重发的次数（默认 2，0 表示不重发）
                      </p>
                    </div>

                    <div class="space-y-2">
                      <label class="block text-xs text-muted-foreground">过期刷新窗口（小时）</label>
                      <Input
                        v-model="refreshWindowHoursInput"
                        type="number"
                        block
                      />
                      <p class="text-xs text-muted-foreground">
                        当账号距离过期小于等于该值时，会触发自动刷新
                      </p>
                    </div>

                    <div class="ui-card-sm bg-muted/20 px-4 py-3">
                      <div>
                        <p class="text-sm font-medium text-foreground">浏览器模式</p>
                        <p class="mt-1 text-xs text-muted-foreground">normal 正常窗口；silent 静默最小化（有头但尽量不抢焦点）；headless 无头</p>
                      </div>
                      <div class="ui-segmented">
                        <button
                          type="button"
                          class="ui-segmented-btn flex-1 justify-center"
                          :class="browserMode === 'normal' ? 'ui-segmented-btn-active text-primary' : ''"
                          @click="browserMode = 'normal'"
                        >
                          normal
                        </button>
                        <button
                          type="button"
                          class="ui-segmented-btn flex-1 justify-center"
                          :class="browserMode === 'silent' ? 'ui-segmented-btn-active text-primary' : ''"
                          @click="browserMode = 'silent'"
                        >
                          silent
                        </button>
                        <button
                          type="button"
                          class="ui-segmented-btn flex-1 justify-center"
                          :class="browserMode === 'headless' ? 'ui-segmented-btn-active text-primary' : ''"
                          @click="browserMode = 'headless'"
                        >
                          headless
                        </button>
                      </div>
                    </div>
                    <div class="ui-card-sm bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
                      <p class="mb-2 font-medium text-foreground">说明</p>
                      <ul class="list-inside list-disc space-y-1">
                        <li>同一时间只会执行一个刷新任务，新触发会复用当前任务</li>
                        <li>到达触发时间后，会一次性处理本轮所有符合条件的账号</li>
                        <li>同一账号刷新成功后，在冷却时间内不会被再次选中</li>
                        <li>修改配置后立即生效，无需重启服务</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>

            <!-- 固定底部按钮区域 -->
            <div class="flex items-center justify-end gap-2 border-t border-border/60 px-6 py-4">
              <Button
                size="sm"
                variant="outline"
                root-class="text-muted-foreground"
                @click="loadScheduledConfig"
              >
                重置
              </Button>
              <Button
                size="sm"
                variant="primary"
                :disabled="isSavingScheduledConfig"
                @click="saveScheduledConfig"
              >
                保存配置
              </Button>
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
            <div v-else-if="taskHistory.length === 0" class="ui-card-sm bg-muted/30 text-xs text-muted-foreground">
              <p class="font-medium text-foreground mb-2">暂无历史记录</p>
              <p>完成的任务将显示在这里</p>
            </div>
            <div v-else class="space-y-3">
              <div
                v-for="(record, index) in taskHistory"
                :key="index"
                class="ui-card-sm text-sm"
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
            <Button
              size="sm"
              variant="outline"
              root-class="text-muted-foreground"
              :disabled="taskHistory.length === 0"
              @click="clearTaskHistory"
            >
              清空历史
            </Button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
  <Teleport to="body">
    <div v-if="isEditOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="ui-overlay-panel w-full max-w-lg">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium text-foreground">编辑账号</p>
          <Button
            size="xs"
            variant="outline"
            root-class="min-w-14 justify-center text-muted-foreground"
            @click="closeEdit"
          >
            关闭
          </Button>
        </div>

        <div v-if="editError" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {{ editError }}
        </div>

        <div class="mt-4 space-y-3 text-sm">
          <label class="block text-xs text-muted-foreground">账号 ID</label>
          <Input
            v-model="editForm.id"
            type="text"
            block
            disabled
          />

          <label class="block text-xs text-muted-foreground">secure_c_ses</label>
          <textarea
            v-model="editForm.secure_c_ses"
            class="ui-textarea-sm"
            rows="3"
          ></textarea>

          <label class="block text-xs text-muted-foreground">csesidx</label>
          <Input
            v-model="editForm.csesidx"
            type="text"
            block
          />

          <label class="block text-xs text-muted-foreground">config_id</label>
          <Input
            v-model="editForm.config_id"
            type="text"
            block
          />

          <label class="block text-xs text-muted-foreground">host_c_oses</label>
          <Input
            v-model="editForm.host_c_oses"
            type="text"
            block
          />

          <label class="block text-xs text-muted-foreground">expires_at</label>
          <Input
            v-model="editForm.expires_at"
            type="text"
            block
            placeholder="2025-12-23 10:59:21"
          />
        </div>

        <div class="mt-6 flex items-center justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            root-class="text-muted-foreground"
            @click="closeEdit"
          >
            取消
          </Button>
          <Button
            size="sm"
            variant="primary"
            @click="saveEdit"
          >
            保存
          </Button>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="isConfigOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="ui-overlay-panel w-full max-w-3xl">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium text-foreground">账户配置（JSON）</p>
          <div class="flex items-center gap-2">
            <Button
              size="xs"
              variant="primary"
              @click="toggleConfigMask"
            >
              {{ configMasked ? '显示原文' : '脱敏显示' }}
            </Button>
            <Button
              size="xs"
              variant="outline"
              root-class="min-w-14 justify-center text-muted-foreground"
              @click="closeConfigPanel"
            >
              关闭
            </Button>
          </div>
        </div>

        <div v-if="configError" class="mt-4 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {{ configError }}
        </div>

        <div class="mt-4">
          <textarea
            v-model="configJson"
            class="ui-textarea-sm h-96 font-mono text-xs"
            spellcheck="false"
            :readonly="configMasked"
          ></textarea>
        </div>

        <div class="mt-6 flex items-center justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            root-class="text-muted-foreground"
            @click="closeConfigPanel"
          >
            取消
          </Button>
          <Button
            size="sm"
            variant="primary"
            @click="saveConfigPanel"
            :disabled="configMasked"
          >
            保存
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
  <Teleport to="body">
    <div v-if="isExportOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 px-4">
      <div class="ui-surface flex max-h-[90vh] w-full max-w-md flex-col overflow-hidden">
        <div class="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <p class="text-sm font-medium text-foreground">导出账号配置</p>
            <p class="mt-1 text-xs text-muted-foreground">选择导出范围与格式</p>
          </div>
          <Button
            size="xs"
            variant="outline"
            root-class="min-w-14 justify-center text-muted-foreground"
            @click="closeExportModal"
          >
            关闭
          </Button>
        </div>
        <div class="scrollbar-slim flex-1 overflow-y-auto px-6 py-4">
          <div class="space-y-4 text-sm">
            <div class="ui-segmented text-xs">
              <button
                type="button"
                class="ui-segmented-btn flex-1 justify-center px-3 py-2"
                :class="exportScope === 'all' ? 'ui-segmented-btn-active' : ''"
                @click="exportScope = 'all'"
              >
                全部
              </button>
              <button
                type="button"
                class="ui-segmented-btn flex-1 justify-center px-3 py-2"
                :class="exportScope === 'selected' ? 'ui-segmented-btn-active' : ''"
                :disabled="!selectedCount"
                @click="exportScope = 'selected'"
              >
                选中
              </button>
            </div>

            <div class="ui-segmented text-xs">
              <button
                type="button"
                class="ui-segmented-btn flex-1 justify-center px-3 py-2"
                :class="exportFormat === 'json' ? 'ui-segmented-btn-active' : ''"
                @click="exportFormat = 'json'"
              >
                JSON
              </button>
              <button
                type="button"
                class="ui-segmented-btn flex-1 justify-center px-3 py-2"
                :class="exportFormat === 'txt' ? 'ui-segmented-btn-active' : ''"
                @click="exportFormat = 'txt'"
              >
                TXT
              </button>
            </div>
            <p class="text-xs text-muted-foreground">
              选中导出仅包含当前已勾选账号（{{ selectedCount }} 个）。
            </p>
            <p class="text-xs text-muted-foreground">
              <template v-if="exportFormat === 'json'">
                JSON 格式包含完整数据（Cookie、Token、过期时间等），导入后无需重新刷新。
              </template>
              <template v-else>
                TXT 格式仅导出邮箱和密码，导入后需要重新刷新获取 Cookie。
              </template>
            </p>
          </div>
        </div>
        <div class="border-t border-border/60 px-6 py-4">
          <div class="flex items-center justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              root-class="text-muted-foreground"
              @click="closeExportModal"
            >
              取消
            </Button>
            <Button
              size="sm"
              variant="primary"
              :disabled="exportScope === 'selected' && !selectedCount"
              @click="runExport"
            >
              开始导出
            </Button>
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
import QuotaBadge from '@/components/QuotaBadge.vue'
import {
  Button,
  Checkbox,
  ConfirmDialog,
  HelpTip,
  Input,
  SelectMenu,
} from 'nanocat-ui'
import { accountsApi, settingsApi } from '@/api'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
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
const viewMode = ref<'table' | 'card'>((localStorage.getItem('accounts_view_mode') as 'table' | 'card') || 'table')
watch(viewMode, (val) => localStorage.setItem('accounts_view_mode', val))

const clampInteger = (value: number, min: number, max: number = Number.MAX_SAFE_INTEGER) =>
  Math.max(min, Math.min(max, Math.round(value)))

const createNumberInputBinding = (
  getter: () => number,
  setter: (value: number) => void,
  normalize: (value: number) => number = (value) => value
) => computed({
  get: () => String(getter()),
  set: (raw: string | number) => {
    const parsed = typeof raw === 'number' ? raw : Number(String(raw).trim())
    if (Number.isFinite(parsed)) {
      setter(normalize(parsed))
    }
  }
})

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
const moreActionsTriggerRef = ref<HTMLButtonElement | null>(null)
const moreActionsMenuRef = ref<HTMLDivElement | null>(null)
const moreActionsMenuPosition = ref({ top: 0, left: 0, width: 176 })
const lastRegisterTaskId = ref<string | null>(null)
const lastLoginTaskId = ref<string | null>(null)
const scheduledRefreshEnabled = ref(false)
const scheduledRefreshCron = ref('08:00,20:00')
const refreshCooldownHours = ref(12)
const verificationCodeResendCount = ref(2)
const refreshWindowHours = ref(24)
const registerCountInput = createNumberInputBinding(
  () => registerCount.value,
  (value) => { registerCount.value = value },
  (value) => clampInteger(value, 1)
)
const refreshCooldownHoursInput = createNumberInputBinding(
  () => refreshCooldownHours.value,
  (value) => { refreshCooldownHours.value = value },
  (value) => clampInteger(value, 1, 48)
)
const verificationCodeResendCountInput = createNumberInputBinding(
  () => verificationCodeResendCount.value,
  (value) => { verificationCodeResendCount.value = value },
  (value) => clampInteger(value, 0, 5)
)
const refreshWindowHoursInput = createNumberInputBinding(
  () => refreshWindowHours.value,
  (value) => { refreshWindowHours.value = value },
  (value) => clampInteger(value, 1, 168)
)
const browserMode = ref<'normal' | 'silent' | 'headless'>('normal')
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
const queuedRefreshAccountIds = ref<Set<string>>(new Set())  // 刷新任务中尚未处理的账户ID集合（仅用于显示状态）
const taskLogsRef = ref<HTMLDivElement | null>(null)
const isRegistering = ref(false)
const isRefreshing = ref(false)
const automationError = ref('')
const REGISTER_CLEAR_KEY = 'accounts-register-log-clear'
const LOGIN_CLEAR_KEY = 'accounts-login-log-clear'
const TASK_LOG_MODE_KEY = 'accounts-task-log-mode'
type TaskLogMode = 'summary' | 'detail'
const taskLogMode = ref<TaskLogMode>(localStorage.getItem(TASK_LOG_MODE_KEY) === 'detail' ? 'detail' : 'summary')
watch(taskLogMode, (mode) => localStorage.setItem(TASK_LOG_MODE_KEY, mode))

type TaskKind = 'register' | 'login'
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
  { label: '刷新中', value: '刷新中' },
  { label: '排队中', value: '排队中' },
  { label: '正常', value: '正常' },
  { label: '即将过期', value: '即将过期' },
  { label: '已过期', value: '已过期' },
  { label: '手动禁用', value: '手动禁用' },
  { label: '403 禁用', value: '403 禁用' },
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
const moreActionsMenuStyle = computed(() => ({
  top: `${moreActionsMenuPosition.value.top}px`,
  left: `${moreActionsMenuPosition.value.left}px`,
  width: `${moreActionsMenuPosition.value.width}px`,
}))

watch([searchQuery, statusFilter], () => {
  currentPage.value = 1
})

const refreshAccounts = async () => {
  await accountsStore.loadAccounts()
  selectedIds.value = new Set()
  showMoreActions.value = false
}

const isTaskActive = (task: RegisterTask | LoginTask | null | undefined) => {
  const status = task?.status
  return status === 'running' || status === 'pending'
}

const getTaskByKind = (kind: TaskKind) => (kind === 'register' ? registerTask.value : loginTask.value)

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

const handleTaskIdle = (kind: TaskKind) => {
  // 后端返回 idle 时：
  // - 运行中任务：收敛为终态，避免前端卡在“执行中”且保留日志
  // - 已完成任务：保留快照和日志，直到手动清空或被新任务替换
  if (kind === 'register') {
    clearRegisterTimer()
    isRegistering.value = false
    const current = registerTask.value
    if (current && isTaskActive(current)) {
      // 避免竞态导致日志被清空：收敛为终态并保留已有日志
      syncRegisterTask({ ...current, status: 'cancelled' } as RegisterTask)
    }
    return
  }
  clearLoginTimer()
  isRefreshing.value = false
  refreshingAccountIds.value = new Set()
  queuedRefreshAccountIds.value = new Set()
  const current = loginTask.value
  if (current && isTaskActive(current)) {
    // 避免竞态导致日志被清空：收敛为终态并保留已有日志
    syncLoginTask({ ...current, status: 'cancelled' } as LoginTask)
  }
}

const handleTaskNotFound = (kind: TaskKind) => {
  // 与 idle 同策略：仅清理运行态，保留已完成日志
  if (kind === 'register') {
    clearRegisterTimer()
    isRegistering.value = false
    const current = registerTask.value
    if (current && isTaskActive(current)) {
      syncRegisterTask({ ...current, status: 'cancelled' } as RegisterTask)
    }
  } else {
    clearLoginTimer()
    isRefreshing.value = false
    refreshingAccountIds.value = new Set()
    queuedRefreshAccountIds.value = new Set()
    const current = loginTask.value
    if (current && isTaskActive(current)) {
      syncLoginTask({ ...current, status: 'cancelled' } as LoginTask)
    }
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
  void kind
  // 统一以后端状态为准，不再依赖本地“dismiss/clear”元数据
  return !!task
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
  void persist
  if (!task) {
    registerTask.value = null
    lastRegisterTaskId.value = null
    registerLogClearMarker.value = null
    writeClearMarker(REGISTER_CLEAR_KEY, null)
    return
  }

  registerTask.value = task
  if (task.id && task.id !== lastRegisterTaskId.value) {
    lastRegisterTaskId.value = task.id
    setLogClearMarker('register', null)
    writeClearMarker(REGISTER_CLEAR_KEY, null)
  }
}

const syncLoginTask = (task: LoginTask | null, persist = true) => {
  void persist
  if (!task) {
    loginTask.value = null
    lastLoginTaskId.value = null
    loginLogClearMarker.value = null
    refreshingAccountIds.value = new Set()
    queuedRefreshAccountIds.value = new Set()
    writeClearMarker(LOGIN_CLEAR_KEY, null)
    return
  }

  loginTask.value = task
  if (task.id && task.id !== lastLoginTaskId.value) {
    lastLoginTaskId.value = task.id
    setLogClearMarker('login', null)
    writeClearMarker(LOGIN_CLEAR_KEY, null)
  }
  const { refreshingIds, queuedIds } = getLoginRefreshDisplayState(task)
  refreshingAccountIds.value = refreshingIds
  queuedRefreshAccountIds.value = queuedIds
}

const getLoginRefreshDisplayState = (task: LoginTask | null) => {
  const empty = {
    refreshingIds: new Set<string>(),
    queuedIds: new Set<string>(),
  }
  if (!task) return empty

  const ids = Array.isArray(task.account_ids) ? task.account_ids : []
  if (!ids.length) return empty

  if (task.status === 'pending') {
    return {
      refreshingIds: new Set<string>(),
      queuedIds: new Set<string>(ids),
    }
  }

  if (task.status !== 'running') {
    return empty
  }

  const progress = Number.isFinite(task.progress) ? Math.floor(Number(task.progress)) : 0
  if (progress < 0 || progress >= ids.length) {
    return empty
  }

  return {
    // 后端 progress 表示“已完成数量”，running 时当前处理下标即 progress
    refreshingIds: new Set<string>([ids[progress]]),
    queuedIds: new Set<string>(ids.slice(progress + 1)),
  }
}

const hydrateTaskCache = () => {
  // 统一以后端状态为准，任务状态不走本地快照恢复
  registerLogClearMarker.value = readClearMarker(REGISTER_CLEAR_KEY)
  loginLogClearMarker.value = readClearMarker(LOGIN_CLEAR_KEY)
  registerTask.value = null
  loginTask.value = null
  lastRegisterTaskId.value = null
  lastLoginTaskId.value = null
  refreshingAccountIds.value = new Set()
  queuedRefreshAccountIds.value = new Set()
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

    if (parts[0].toLowerCase() === 'cfmail') {
      if (parts.length < 2 || !parts[1]) {
        errors.push(`第 ${lineNo} 行格式错误（cfmail）`)
        return
      }
      const email = parts[1]
      const jwt = parts[2] || ''
      items.push({
        id: email,
        secure_c_ses: '',
        csesidx: '',
        config_id: '',
        expires_at: IMPORT_EXPIRES_AT,
        mail_provider: 'cfmail',
        mail_address: email,
        mail_password: jwt,
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

      // Check if imported accounts need refresh (no valid cookies)
      const needRefresh = importList.some((item: any) => !item.secure_c_ses)
      if (needRefresh && importedIds.length > 0) {
        closeRegisterModal()
        const confirmed = await confirmDialog.ask({
          title: '导入成功',
          message: `已导入 ${importedIds.length} 个账户。检测到部分账户缺少 Cookie，是否立即刷新？`,
          confirmText: '立即刷新',
          cancelText: '稍后手动刷新',
        })
        if (confirmed) {
          await handleRefreshSelected()
        }
      } else {
        closeRegisterModal()
      }
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
      if (provider === 'cfmail') {
        return `cfmail----${email}----${item.mail_password || ''}`
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
    taskHistory.value = Array.isArray(data.history) ? data.history : []
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
}

const loadScheduledConfig = async () => {
  isLoadingScheduledConfig.value = true
  try {
    const settings = await settingsApi.get()
    cachedSettings.value = settings  // 缓存配置
    scheduledRefreshEnabled.value = settings.retry.scheduled_refresh_enabled ?? false
    scheduledRefreshCron.value = settings.retry.scheduled_refresh_cron ?? '08:00,20:00'
    refreshCooldownHours.value = settings.retry.refresh_cooldown_hours ?? 12
    verificationCodeResendCount.value = settings.retry.verification_code_resend_count ?? 2
    refreshWindowHours.value = settings.basic.refresh_window_hours ?? 24
    browserMode.value =
      settings.basic.browser_mode === 'normal' ||
      settings.basic.browser_mode === 'silent' ||
      settings.basic.browser_mode === 'headless'
        ? settings.basic.browser_mode
        : ((settings.basic.browser_headless ?? false) ? 'headless' : 'normal')
  } catch (error: any) {
    toast.error(error?.message || '加载定时任务配置失败')
  } finally {
    isLoadingScheduledConfig.value = false
  }
}

const normalizeScheduledCronInput = (value: string) => {
  const raw = (value || '').trim()
  if (!raw) {
    throw new Error('刷新时间不能为空')
  }

  if (raw.startsWith('*/')) {
    const minutes = Number(raw.slice(2))
    if (!Number.isInteger(minutes) || minutes < 5) {
      throw new Error('间隔模式格式错误，应为 */分钟数，且最小 5 分钟')
    }
    return `*/${minutes}`
  }

  const times = raw
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
  if (!times.length) {
    throw new Error('每日模式至少提供一个时间点')
  }

  const normalized: string[] = []
  for (const time of times) {
    const parts = time.split(':')
    if (parts.length !== 2) {
      throw new Error(`时间格式错误: ${time}`)
    }
    const hour = Number(parts[0])
    const minute = Number(parts[1])
    if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      throw new Error(`时间超出范围: ${time}`)
    }
    const normalizedTime = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
    if (!normalized.includes(normalizedTime)) {
      normalized.push(normalizedTime)
    }
  }
  normalized.sort()
  return normalized.join(',')
}

const saveScheduledConfig = async () => {
  // 验证冷却时间
  if (isNaN(refreshCooldownHours.value) || refreshCooldownHours.value < 1 || refreshCooldownHours.value > 48) {
    toast.error('冷却时间必须在 1-48 小时之间')
    return
  }

  // 验证验证码重发次数
  if (isNaN(verificationCodeResendCount.value) || !Number.isInteger(verificationCodeResendCount.value)) {
    toast.error('验证码重发次数必须是有效的整数')
    return
  }
  if (verificationCodeResendCount.value < 0 || verificationCodeResendCount.value > 5) {
    toast.error('验证码重发次数必须在 0-5 之间')
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

  if (browserMode.value !== 'normal' && browserMode.value !== 'silent' && browserMode.value !== 'headless') {
    toast.error('浏览器模式必须是 normal / silent / headless')
    return
  }
  isSavingScheduledConfig.value = true
  try {
    const normalizedCron = normalizeScheduledCronInput(scheduledRefreshCron.value)
    // 使用缓存的配置，避免重复API调用
    const settings = cachedSettings.value || await settingsApi.get()
    settings.retry.scheduled_refresh_enabled = scheduledRefreshEnabled.value
    settings.retry.scheduled_refresh_cron = normalizedCron
    settings.retry.refresh_cooldown_hours = refreshCooldownHours.value
    settings.retry.verification_code_resend_count = verificationCodeResendCount.value
    settings.basic.refresh_window_hours = refreshWindowHours.value
    settings.basic.browser_mode = browserMode.value
    settings.basic.browser_headless = browserMode.value === 'headless'
    await settingsApi.update(settings)
    cachedSettings.value = settings  // 更新缓存
    scheduledRefreshCron.value = normalizedCron
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
      clearTaskSnapshot(kind, true)
      return
    }
    const logs = (task.logs || []) as TaskLogLine[]
    if (!logs.length) return
    const marker = logs[logs.length - 1]
    setLogClearMarker(kind, marker)
    writeClearMarker(kind === 'register' ? REGISTER_CLEAR_KEY : LOGIN_CLEAR_KEY, marker)
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

const TASK_LOG_SUMMARY_KEYWORDS = [
  '开始',
  '启动',
  '创建',
  '完成',
  '成功',
  '失败',
  '中断',
  '取消',
  '异常',
  '错误',
  '告警',
  'warning',
  'error',
  'critical',
  'timeout',
  '超时',
  '403',
  '429',
  '验证码',
  'send code',
  'task started',
  'task finished',
  'task completed',
  'task cancelled',
  '切换',
  '重试',
  'retry',
  '跳过',
  'skip',
]

const messageHasTaskSummaryKeyword = (message: string) => {
  const lower = message.toLowerCase()
  return TASK_LOG_SUMMARY_KEYWORDS.some(keyword => lower.includes(keyword))
}

const isTaskSummaryLog = (log: TaskLogLine) => {
  const level = log.level.toUpperCase()
  if (level === 'ERROR' || level === 'WARNING' || level === 'CRITICAL') return true
  return messageHasTaskSummaryKeyword(log.message)
}

const buildVisibleTaskLogs = (logs: TaskLogLine[]) => {
  if (taskLogMode.value === 'detail') return logs
  if (!logs.length) return logs

  const picked: TaskLogLine[] = [logs[0]]
  for (let i = 1; i < logs.length - 1; i += 1) {
    if (isTaskSummaryLog(logs[i])) {
      picked.push(logs[i])
    }
  }
  if (logs.length > 1) {
    picked.push(logs[logs.length - 1])
  }

  const deduped: TaskLogLine[] = []
  const seen = new Set<string>()
  for (const item of picked) {
    const key = `${item.time}|${item.level}|${item.message}`
    if (seen.has(key)) continue
    seen.add(key)
    deduped.push(item)
  }
  return deduped
}

const toggleTaskLogMode = () => {
  taskLogMode.value = taskLogMode.value === 'summary' ? 'detail' : 'summary'
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

const updateMoreActionsMenuPosition = () => {
  if (!moreActionsTriggerRef.value) return
  const rect = moreActionsTriggerRef.value.getBoundingClientRect()
  const spacing = 8
  const padding = 8
  const menuWidth = rect.width
  const menuHeight = moreActionsMenuRef.value?.offsetHeight || 240

  let left = rect.left
  let top = rect.bottom + spacing

  const maxLeft = window.innerWidth - menuWidth - padding
  const maxTop = window.innerHeight - menuHeight - padding

  left = Math.min(Math.max(left, padding), Math.max(padding, maxLeft))
  top = Math.min(Math.max(top, padding), Math.max(padding, maxTop))

  moreActionsMenuPosition.value = { top, left, width: menuWidth }
}

const openMoreActions = async () => {
  showMoreActions.value = true
  await nextTick()
  updateMoreActionsMenuPosition()
  requestAnimationFrame(updateMoreActionsMenuPosition)
}

const closeMoreActions = () => {
  showMoreActions.value = false
}

const toggleMoreActions = () => {
  if (showMoreActions.value) {
    closeMoreActions()
    return
  }
  void openMoreActions()
}

const handleMoreActionsClick = (event: MouseEvent) => {
  if (!showMoreActions.value) return
  const target = event.target as Node
  if (moreActionsTriggerRef.value?.contains(target)) return
  if (moreActionsMenuRef.value?.contains(target)) return
  closeMoreActions()
}

const handleMoreActionsViewportChange = () => {
  if (!showMoreActions.value) return
  updateMoreActionsMenuPosition()
}

const handleMoreActionsKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    closeMoreActions()
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
  // 任务状态统一以后端为准，不做本地任务快照恢复
  hydrateTaskCache()
  await refreshAccounts()
  await loadCurrentTasks()
  startBackgroundTaskPolling()
  document.addEventListener('click', handleMoreActionsClick)
  document.addEventListener('keydown', handleMoreActionsKeydown)
  window.addEventListener('resize', handleMoreActionsViewportChange)
  window.addEventListener('scroll', handleMoreActionsViewportChange, true)
})

const registerLogs = computed(() => {
  const logs = registerTask.value?.logs || []
  return filterLogsAfterMarker(logs as TaskLogLine[], registerLogClearMarker.value)
})
const loginLogs = computed(() => {
  const logs = loginTask.value?.logs || []
  return filterLogsAfterMarker(logs as TaskLogLine[], loginLogClearMarker.value)
})
const visibleRegisterLogs = computed(() => buildVisibleTaskLogs(registerLogs.value))
const visibleLoginLogs = computed(() => buildVisibleTaskLogs(loginLogs.value))
const scrollTaskLogsToBottom = async () => {
  await nextTick()
  const container = taskLogsRef.value
  if (!container) return
  container.scrollTop = container.scrollHeight
}

watch([visibleRegisterLogs, visibleLoginLogs, isTaskOpen, taskLogMode], async () => {
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
  document.removeEventListener('keydown', handleMoreActionsKeydown)
  window.removeEventListener('resize', handleMoreActionsViewportChange)
  window.removeEventListener('scroll', handleMoreActionsViewportChange, true)
})

const statusLabel = (account: AdminAccount) => {
  // 检查是否正在刷新
  if (refreshingAccountIds.value.has(account.id)) {
    return '刷新中'
  }
  if (queuedRefreshAccountIds.value.has(account.id)) {
    return '排队中'
  }
  if (account.cooldown_reason?.includes('429') && account.cooldown_seconds > 0) {
    return '429限流'
  }
  if (account.disabled) {
    if (account.disabled_reason?.includes('403')) {
      return '403 禁用'
    }
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
  if (status === '排队中') {
    return 'bg-sky-100 text-sky-700'
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
  if (status === '403 禁用') {
    return 'bg-rose-600 text-white'
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

const trialBadgeClass = (days: number | null | undefined) => {
  if (days == null) return ''
  if (days > 7) return 'bg-emerald-500 text-white'
  if (days >= 3) return 'bg-amber-500 text-white'
  return 'bg-rose-500 text-white'
}

const rowClass = (account: AdminAccount) => {
  const status = statusLabel(account)
  if (status === '手动禁用' || status === '已过期' || status === '403 禁用') {
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
      const current = registerTask.value
      if (current?.id === taskId && isTaskActive(current)) {
        // 后端已不存在该任务，前端将其收敛为终态，保留已有日志便于排查
        syncRegisterTask({ ...current, status: 'cancelled' } as RegisterTask)
      }
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
      queuedRefreshAccountIds.value = new Set()
      const current = loginTask.value
      if (current?.id === taskId && isTaskActive(current)) {
        // 后端已不存在该任务，前端将其收敛为终态，保留已有日志便于排查
        syncLoginTask({ ...current, status: 'cancelled' } as LoginTask)
      }
      return
    }
    throw error
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
    startLoginPolling(task.id)
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
      startLoginPolling(taskOrIdle.id)
      return
    }
    // 没有新任务时，尝试读取当前任务（可能已有 running/pending）
    const current = await accountsApi.getLoginCurrent()
    if (current && 'id' in current) {
      syncLoginTask(current)
      startLoginPolling(current.id)
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




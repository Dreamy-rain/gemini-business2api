import apiClient from './client'
import type {
  AccountsConfigResponse,
  AccountsListResponse,
  AccountConfigItem,
  RegisterTask,
  LoginTask,
  ScheduledRefreshStatesResponse,
} from '@/types/api'

export const accountsApi = {
  // 获取账户列表
  list: () =>
    apiClient.get<never, AccountsListResponse>('/admin/accounts'),

  // 获取账户配置
  getConfig: () =>
    apiClient.get<never, AccountsConfigResponse>('/admin/accounts-config'),

  // 更新账户配置
  updateConfig: (accounts: AccountConfigItem[]) =>
    apiClient.put('/admin/accounts-config', accounts),

  // 删除账户
  delete: (accountId: string) =>
    apiClient.delete(`/admin/accounts/${accountId}`),

  // 禁用账户
  disable: (accountId: string) =>
    apiClient.put(`/admin/accounts/${accountId}/disable`),

  // 启用账户
  enable: (accountId: string) =>
    apiClient.put(`/admin/accounts/${accountId}/enable`),

  // 批量启用账户（最多50个）
  bulkEnable: (accountIds: string[]) =>
    apiClient.put<never, { status: string; success_count: number; errors: string[] }>(
      '/admin/accounts/bulk-enable',
      accountIds
    ),

  // 批量禁用账户（最多50个）
  bulkDisable: (accountIds: string[]) =>
    apiClient.put<never, { status: string; success_count: number; errors: string[] }>(
      '/admin/accounts/bulk-disable',
      accountIds
    ),
  // 批量删除账户（最多50个）
  bulkDelete: (accountIds: string[]) =>
    apiClient.put<never, { status: string; success_count: number; errors: string[] }>(
      '/admin/accounts/bulk-delete',
      accountIds
    ),

  startRegister: (count?: number, domain?: string, mail_provider?: string) =>
    apiClient.post<never, RegisterTask>('/admin/register/start', { count, domain, mail_provider }),

  getRegisterTask: (taskId: string) =>
    apiClient.get<never, RegisterTask>(`/admin/register/task/${taskId}`),

  getRegisterCurrent: () =>
    apiClient.get<never, RegisterTask | { status: string }>('/admin/register/current'),

  cancelRegisterTask: (taskId: string, reason?: string) =>
    apiClient.post<{ reason?: string }, RegisterTask>(`/admin/register/cancel/${taskId}`, reason ? { reason } : {}),

  startLogin: (accountIds: string[]) =>
    apiClient.post<never, LoginTask>('/admin/login/start', accountIds),

  getLoginTask: (taskId: string) =>
    apiClient.get<never, LoginTask>(`/admin/login/task/${taskId}`),

  getLoginCurrent: () =>
    apiClient.get<never, LoginTask | { status: string }>('/admin/login/current'),

  cancelLoginTask: (taskId: string, reason?: string) =>
    apiClient.post<{ reason?: string }, LoginTask>(`/admin/login/cancel/${taskId}`, reason ? { reason } : {}),

  checkLogin: () =>
    apiClient.post<never, LoginTask | { status: string }>('/admin/login/check'),

  // 暂停自动刷新
  pauseAutoRefresh: () =>
    apiClient.post<never, { status: string; message: string }>('/admin/auto-refresh/pause'),

  // 恢复自动刷新
  resumeAutoRefresh: () =>
    apiClient.post<never, { status: string; message: string }>('/admin/auto-refresh/resume'),

  // 获取自动刷新状态
  getAutoRefreshStatus: () =>
    apiClient.get<never, { paused: boolean; status: string }>('/admin/auto-refresh/status'),

  // 获取“高级自动刷新调度”状态（用于面板可视化）
  getScheduledRefreshStates: () =>
    apiClient.get<never, ScheduledRefreshStatesResponse>('/admin/scheduled-refresh/states'),
}

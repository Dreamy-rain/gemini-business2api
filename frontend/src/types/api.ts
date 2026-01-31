// API 类型定义

export interface QuotaStatus {
  available: boolean
  remaining_seconds?: number
  reason?: string  // 受限原因（如"对话配额受限"）
}

export interface AccountQuotaStatus {
  quotas: {
    text: QuotaStatus
    images: QuotaStatus
    videos: QuotaStatus
  }
  limited_count: number
  total_count: number
  is_expired: boolean
}

export interface AdminAccount {
  id: string
  status: string
  expires_at: string
  remaining_hours: number | null
  remaining_display: string
  is_available: boolean
  error_count: number
  failure_count: number
  disabled: boolean
  cooldown_seconds: number
  cooldown_reason: string | null
  conversation_count: number
  quota_status: AccountQuotaStatus
}

export interface AccountsListResponse {
  total: number
  accounts: AdminAccount[]
}

export interface AccountConfigItem {
  id: string
  secure_c_ses: string
  csesidx: string
  config_id: string
  host_c_oses?: string
  expires_at?: string
  mail_provider?: string
  mail_address?: string
  mail_password?: string
  mail_client_id?: string
  mail_refresh_token?: string
  mail_tenant?: string
}

export interface AccountsConfigResponse {
  accounts: AccountConfigItem[]
}

export interface Stats {
  total_accounts: number
  active_accounts: number
  failed_accounts: number
  rate_limited_accounts: number
  expired_accounts: number
  total_requests: number
  total_visitors: number
  requests_per_hour: number
}

export type TempMailProvider = 'duckmail' | 'moemail' | 'freemail' | 'gptmail'

export interface Settings {
  basic: {
    api_key?: string
    base_url?: string
    proxy_for_auth?: string
    proxy_for_chat?: string
    duckmail_base_url?: string
    duckmail_api_key?: string
    duckmail_verify_ssl?: boolean
    temp_mail_provider?: TempMailProvider
    moemail_base_url?: string
    moemail_api_key?: string
    moemail_domain?: string
    freemail_base_url?: string
    freemail_jwt_token?: string
    freemail_verify_ssl?: boolean
    freemail_domain?: string
    mail_proxy_enabled?: boolean
    gptmail_base_url?: string
    gptmail_api_key?: string
    gptmail_verify_ssl?: boolean
    browser_engine?: string
    browser_headless?: boolean
    refresh_window_hours?: number
    register_default_count?: number
    register_domain?: string
  }
  retry: {
    max_new_session_tries: number
    max_request_retries: number
    max_account_switch_tries: number
    account_failure_threshold: number
    text_rate_limit_cooldown_seconds: number
    images_rate_limit_cooldown_seconds: number
    videos_rate_limit_cooldown_seconds: number
    session_cache_ttl_seconds: number
    auto_refresh_accounts_seconds: number
    scheduled_refresh_enabled?: boolean
    scheduled_refresh_interval_minutes?: number
    /**
     * 是否启用“高级自动刷新调度”（默认关闭）。
     *
     * 功能说明：
     * - 仅影响“后台自动定时触发”的刷新：防堆叠、公平调度、失败退避；
     * - 不影响管理面板的手动刷新语义（手动仍会立即执行）。
     */
    scheduled_refresh_advanced_enabled?: boolean
    /**
     * 高级调度：单轮最多入队的账号数量。
     *
     * 说明：
     * - 后端内部会确保每轮至少有固定的最小批次（例如 5 个）以保证进展；
     * - 该值过小会被后端最小批次覆盖。
     */
    scheduled_refresh_max_batch_size?: number
  }
  public_display: {
    logo_url?: string
    chat_url?: string
  }
  image_generation: {
    enabled: boolean
    supported_models: string[]
    output_format?: 'base64' | 'url'
  }
  session: {
    expire_hours: number
  }
}

/**
 * 单个账号的“高级自动刷新调度状态”展示数据。
 *
 * 说明：
 * - 该结构来自后端 `/admin/scheduled-refresh/states`；
 * - 不包含任何敏感字段，仅用于管理面板可视化与排查。
 */
export interface ScheduledRefreshStateItem {
  /** 账号 ID */
  id: string
  /** 是否已存在调度状态（历史为空时为 false） */
  has_state: boolean
  /** 上次尝试刷新时间戳（秒） */
  last_attempt_at: number
  /** 上次尝试刷新（北京时间字符串） */
  last_attempt_at_beijing: string
  /** 上次成功刷新时间戳（秒） */
  last_success_at: number
  /** 上次成功刷新（北京时间字符串） */
  last_success_at_beijing: string
  /** 平均刷新耗时（秒，滑动平均；历史为空时可能为 0） */
  avg_refresh_duration_seconds: number
  /** 连续失败次数（成功会清零） */
  consecutive_failures: number
  /** 退避到期时间戳（秒；0 表示未退避） */
  next_eligible_at: number
  /** 退避到期时间（北京时间字符串） */
  next_eligible_at_beijing: string
  /** 是否处于退避中 */
  in_backoff: boolean
  /** 距离可再次参与自动调度的剩余秒数（不在退避则为 0） */
  backoff_remaining_seconds: number
  /** 最近一次错误原因（截断） */
  last_error: string
}

/**
 * 后端“高级自动刷新调度状态”汇总响应。
 */
export interface ScheduledRefreshStatesResponse {
  /** 服务端当前时间戳（秒） */
  now: number
  /** 服务端当前时间（北京时间字符串） */
  now_beijing: string
  /** 调度相关配置回显（便于面板对照） */
  config: {
    scheduled_refresh_enabled: boolean
    scheduled_refresh_interval_minutes: number
    scheduled_refresh_advanced_enabled: boolean
    scheduled_refresh_max_batch_size: number
    scheduled_refresh_min_batch_size: number
  }
  /** 账号条目数量 */
  total: number
  /** 每个账号的调度状态 */
  items: ScheduledRefreshStateItem[]
}

export interface LogEntry {
  time: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | 'DEBUG'
  message: string
}

export interface LogsResponse {
  total: number
  limit: number
  logs: LogEntry[]
}

export interface AdminLogStats {
  memory: {
    total: number
    by_level: Record<string, number>
    capacity: number
  }
  errors: {
    count: number
    recent: LogEntry[]
  }
  chat_count: number
}

export interface AdminLogsResponse extends LogsResponse {
  filters?: {
    level?: string | null
    search?: string | null
    start_time?: string | null
    end_time?: string | null
  }
  stats: AdminLogStats
}

export type PublicLogStatus = 'success' | 'error' | 'timeout' | 'in_progress'

export interface PublicLogEvent {
  time: string
  type: 'start' | 'select' | 'retry' | 'switch' | 'complete'
  status?: 'success' | 'error' | 'timeout'
  content: string
}

export interface PublicLogGroup {
  request_id: string
  start_time: string
  status: PublicLogStatus
  events: PublicLogEvent[]
}

export interface PublicLogsResponse {
  total: number
  logs: PublicLogGroup[]
  error?: string
}

export interface AdminStatsTrend {
  labels: string[]
  total_requests: number[]
  failed_requests: number[]
  rate_limited_requests: number[]
  model_requests?: Record<string, number[]>
}

export interface AdminStats {
  total_accounts: number
  active_accounts: number
  failed_accounts: number
  rate_limited_accounts: number
  idle_accounts: number
  success_count?: number
  failed_count?: number
  trend: AdminStatsTrend
}

export interface PublicStats {
  total_visitors: number
  total_requests: number
  requests_per_minute: number
  load_status: 'low' | 'medium' | 'high'
  load_color: string
}

export interface PublicDisplay {
  logo_url?: string
  chat_url?: string
}

export interface UptimeHeartbeat {
  time: string
  success: boolean
  latency_ms?: number | null
  status_code?: number | null
  level?: 'up' | 'down' | 'warn'
}

export interface UptimeService {
  name: string
  status: 'up' | 'down' | 'warn' | 'unknown'
  uptime: number
  total: number
  success: number
  heartbeats: UptimeHeartbeat[]
}

export interface UptimeResponse {
  services: Record<string, UptimeService>
  updated_at: string
}

export interface LoginRequest {
  password: string
}

export interface LoginResponse {
  success: boolean
  message?: string
}

export type AutomationStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export interface RegisterTask {
  id: string
  count: number
  domain?: string | null
  status: AutomationStatus
  progress: number
  success_count: number
  fail_count: number
  created_at: number
  finished_at?: number | null
  results: Array<Record<string, any>>
  error?: string | null
  logs?: Array<{ time: string; level: string; message: string }>
  cancel_requested?: boolean
  cancel_reason?: string | null
}

export interface LoginTask {
  id: string
  account_ids: string[]
  status: AutomationStatus
  progress: number
  success_count: number
  fail_count: number
  created_at: number
  finished_at?: number | null
  results: Array<Record<string, any>>
  error?: string | null
  logs?: Array<{ time: string; level: string; message: string }>
  cancel_requested?: boolean
  cancel_reason?: string | null
}

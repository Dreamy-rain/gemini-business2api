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
    gptmail_domain?: string
    browser_engine?: string
    browser_headless?: boolean
    refresh_window_hours?: number
    register_default_count?: number
    register_domain?: string
  }
  retry: {
    max_account_switch_tries: number
    account_failure_threshold: number
    text_rate_limit_cooldown_seconds: number
    images_rate_limit_cooldown_seconds: number
    videos_rate_limit_cooldown_seconds: number
    session_cache_ttl_seconds: number
    auto_refresh_accounts_seconds: number
    scheduled_refresh_enabled?: boolean
    scheduled_refresh_interval_minutes?: number
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
  model_ttfb_times?: Record<string, number[]>
  model_total_times?: Record<string, number[]>
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

// API 类型定义

export interface AdminAccount {
  id: string
  status: string
  expires_at: string
  remaining_hours: number | null
  remaining_display: string
  is_available: boolean
  error_count: number
  disabled: boolean
  cooldown_seconds: number
  cooldown_reason: string | null
  conversation_count: number
}

export interface AccountsListResponse {
  total: number
  accounts: AdminAccount[]
}

export interface AccountConfigItem {
  id?: string
  secure_c_ses: string
  csesidx: string
  config_id: string
  host_c_oses?: string
  expires_at?: string
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

export interface Settings {
  basic: {
    api_key?: string
    base_url?: string
    proxy?: string
  }
  retry: {
    max_new_session_tries: number
    max_request_retries: number
    max_account_switch_tries: number
    account_failure_threshold: number
    rate_limit_cooldown_seconds: number
    session_cache_ttl_seconds: number
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
}

export interface AdminStats {
  total_accounts: number
  active_accounts: number
  failed_accounts: number
  rate_limited_accounts: number
  idle_accounts: number
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

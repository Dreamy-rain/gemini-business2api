"""
统一配置管理系统

优先级规则：
1. 安全配置：仅环境变量（ADMIN_KEY, SESSION_SECRET_KEY）
2. 业务配置：YAML 配置文件 > 默认值

配置分类：
- 安全配置：仅从环境变量读取，不可热更新（ADMIN_KEY, SESSION_SECRET_KEY）
- 业务配置：仅从 YAML 读取，支持热更新（API_KEY, BASE_URL, PROXY, 重试策略等）
"""

import os
import time
import yaml
import secrets
from enum import Enum
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

from core import storage
from core.outbound_proxy import OutboundProxyConfig, normalize_proxy_url

# 加载 .env 文件
load_dotenv()

def _parse_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "y", "on"):
            return True
        if lowered in ("0", "false", "no", "n", "off"):
            return False
    return default


def _parse_int(value, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if value is None:
        return default
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default
    try:
        return int(value)
    except Exception:
        return default


# ==================== 配置模型定义 ====================

class ApiKeyMode(str, Enum):
    MEMORY = "memory"
    FAST = "fast"


class ApiKeyConfig(BaseModel):
    """API 密钥配置"""
    key: str = Field(..., description="API密钥")
    mode: ApiKeyMode = Field(default=ApiKeyMode.MEMORY, description="模式：memory(深度记忆) | fast(流浪模式)")
    remark: str = Field(default="", description="备注")
    created_at: int = Field(default_factory=lambda: int(time.time()), description="创建时间")


class BasicConfig(BaseModel):
    """基础配置"""
    api_key: str = Field(default="", description="API访问密钥（兼容旧版，默认为 memory 模式）")
    api_keys: List[ApiKeyConfig] = Field(default=[], description="多API密钥配置方案")
    
    base_url: str = Field(default="", description="服务器URL（留空则自动检测）")
    proxy: str = Field(default="", description="代理地址")
    proxy_for_auth: str = Field(default="", description="账户操作代理地址（注册/登录/刷新，留空则不使用代理）")
    proxy_for_chat: str = Field(default="", description="对话操作代理地址（JWT/会话/消息，留空则不使用代理）")
    outbound_proxy: OutboundProxyConfig = Field(default_factory=OutboundProxyConfig, description="出站代理（结构化配置）")
    
    # Mail Providers
    temp_mail_provider: str = Field(default="duckmail", description="临时邮箱服务提供商")
    
    duckmail_base_url: str = Field(default="https://api.duckmail.sbs", description="DuckMail API地址")
    duckmail_api_key: str = Field(default="", description="DuckMail API key")
    duckmail_verify_ssl: bool = Field(default=True, description="DuckMail SSL校验")
    
    gptmail_base_url: str = Field(default="https://mail.chatgpt.org.uk", description="GPTMail API地址")
    gptmail_api_key: str = Field(default="", description="GPTMail API key")
    gptmail_verify_ssl: bool = Field(default=True, description="GPTMail SSL校验")
    gptmail_domain: str = Field(default="", description="GPTMail 邮箱域名（可选，留空则随机选择）")

    # FreeMail Config
    freemail_base_url: str = Field(default="http://your-freemail-server.com", description="Freemail API地址")
    freemail_jwt_token: str = Field(default="", description="Freemail JWT Token")
    freemail_verify_ssl: bool = Field(default=True, description="Freemail SSL校验")
    freemail_domain: str = Field(default="", description="Freemail 邮箱域名（可选，留空则随机选择）")
    
    # Moemail Config
    moemail_base_url: str = Field(default="https://moemail.app", description="Moemail API地址")
    moemail_api_key: str = Field(default="", description="Moemail API Key")
    moemail_domain: str = Field(default="", description="Moemail 域名")

    mail_proxy_enabled: bool = Field(default=False, description="是否启用临时邮箱代理（使用账户操作代理）")
    
    browser_engine: str = Field(default="dp", description="浏览器引擎：uc 或 dp")
    browser_headless: bool = Field(default=False, description="自动化浏览器无头模式")
    refresh_window_hours: int = Field(default=1, ge=0, le=24, description="过期刷新窗口（小时）")
    register_default_count: int = Field(default=1, ge=1, description="默认注册数量")
    register_domain: str = Field(default="", description="默认注册域名（推荐）")


class ImageGenerationConfig(BaseModel):
    """图片生成配置"""
    enabled: bool = Field(default=True, description="是否启用图片生成")
    supported_models: List[str] = Field(
        default=["gemini-3-pro-preview"],
        description="支持图片生成的模型列表"
    )
    output_format: str = Field(default="base64", description="图片输出格式：base64 或 url")


class VideoGenerationConfig(BaseModel):
    """视频生成配置"""
    output_format: str = Field(default="html", description="视频输出格式：html/url/markdown")

    @validator("output_format")
    def validate_output_format(cls, v):
        allowed = ["html", "url", "markdown"]
        if v not in allowed:
            raise ValueError(f"output_format 必须是 {allowed} 之一")
        return v


class RetryConfig(BaseModel):
    """重试策略配置"""
    max_new_session_tries: int = Field(default=5, ge=1, le=20, description="新会话尝试账户数")
    max_request_retries: int = Field(default=3, ge=1, le=10, description="请求失败重试次数")
    max_account_switch_tries: int = Field(default=5, ge=1, le=20, description="账户切换尝试次数")
    account_failure_threshold: int = Field(default=3, ge=1, le=10, description="账户失败阈值")
    rate_limit_cooldown_seconds: int = Field(default=3600, ge=3600, le=43200, description="429冷却时间（秒）")
    session_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400, description="会话缓存时间（秒，0表示禁用缓存）")
    auto_refresh_accounts_seconds: int = Field(default=600, ge=0, le=3600, description="自动刷新账号间隔（秒，0禁用）")


class PublicDisplayConfig(BaseModel):
    """公开展示配置"""
    logo_url: str = Field(default="", description="Logo URL")
    chat_url: str = Field(default="", description="开始对话链接")


class SessionConfig(BaseModel):
    """Session配置"""
    expire_hours: int = Field(default=24, ge=1, le=168, description="Session过期时间（小时）")


class SecurityConfig(BaseModel):
    """安全配置（仅从环境变量读取，不可热更新）"""
    admin_key: str = Field(default="", description="管理员密钥（必需）")
    session_secret_key: str = Field(..., description="Session密钥")


class AppConfig(BaseModel):
    """应用配置（统一管理）"""
    # 安全配置（仅从环境变量）
    security: SecurityConfig

    # 业务配置（环境变量 > YAML > 默认值）
    basic: BasicConfig
    image_generation: ImageGenerationConfig
    video_generation: VideoGenerationConfig = Field(default_factory=VideoGenerationConfig)
    retry: RetryConfig
    public_display: PublicDisplayConfig
    session: SessionConfig


# ==================== 配置管理器 ====================

class ConfigManager:
    """配置管理器（单例）"""

    def __init__(self, yaml_path: str = None):
        # 自动检测环境并设置默认路径
        if yaml_path is None:
            if os.path.exists("/data"):
                yaml_path = "/data/settings.yaml"  # HF Pro 持久化
            else:
                yaml_path = "data/settings.yaml"  # 本地存储
        self.yaml_path = Path(yaml_path)
        self._config: Optional[AppConfig] = None
        self.load()

    def load(self):
        """
        加载配置

        优先级规则：
        1. 安全配置（ADMIN_KEY, SESSION_SECRET_KEY）：仅从环境变量读取
        2. 其他配置：YAML > 默认值
        """
        # 1. 加载 YAML 配置
        yaml_data = self._load_yaml()

        # [新增] 数据库模式下，自动合并本地文件中的新 API Key
        if storage.is_database_enabled() and self.yaml_path.exists():
            try:
                with open(self.yaml_path, 'r', encoding='utf-8') as f:
                    file_data = yaml.safe_load(f) or {}
                
                if self._merge_api_keys_from_file(yaml_data, file_data):
                    print(f"[CONFIG] 检测到本地配置文件包含新 API Key，已自动同步到数据库")
                    self.save_yaml(yaml_data)
            except Exception as e:
                print(f"[WARN] 配置自动同步失败: {e}")

        # 2. 加载安全配置（仅从环境变量，不允许 Web 修改）
        security_config = SecurityConfig(
            admin_key=os.getenv("ADMIN_KEY", ""),
            session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret())
        )

        # 3. 加载基础配置（YAML > 默认值）
        basic_data = yaml_data.get("basic", {})
        refresh_window_raw = basic_data.get("refresh_window_hours", 1)
        register_default_raw = basic_data.get("register_default_count", 1)
        register_domain_raw = basic_data.get("register_domain", "")
        duckmail_api_key_raw = basic_data.get("duckmail_api_key", "")
        gptmail_api_key_raw = basic_data.get("gptmail_api_key", "")

        outbound_data = basic_data.get("outbound_proxy", {})
        if not isinstance(outbound_data, dict):
            outbound_data = {}
        outbound_proxy_config = OutboundProxyConfig(
            enabled=_parse_bool(outbound_data.get("enabled"), False),
            protocol=str(outbound_data.get("protocol") or "http").strip().lower(),
            host=str(outbound_data.get("host") or "").strip(),
            port=_parse_int(outbound_data.get("port"), 0),
            username=str(outbound_data.get("username") or ""),
            password_enc=str(outbound_data.get("password_enc") or ""),
            no_proxy=str(outbound_data.get("no_proxy") or ""),
            direct_fallback=_parse_bool(outbound_data.get("direct_fallback"), True),
        )

        # 兼容旧配置：如果存在新配置字段则直接使用，否则保持为空
        proxy_for_auth = basic_data.get("proxy_for_auth", "")
        proxy_for_chat = basic_data.get("proxy_for_chat", "")

        basic_config = BasicConfig(
            api_key=basic_data.get("api_key") or "",
            api_keys=basic_data.get("api_keys", []),  # Added field
            base_url=basic_data.get("base_url") or "",
            proxy=normalize_proxy_url(str(basic_data.get("proxy") or "")),
            proxy_for_auth=str(proxy_for_auth or "").strip(),
            proxy_for_chat=str(proxy_for_chat or "").strip(),
            outbound_proxy=outbound_proxy_config,
            
            temp_mail_provider=str(basic_data.get("temp_mail_provider") or "duckmail").strip(),
            
            duckmail_base_url=basic_data.get("duckmail_base_url") or "https://api.duckmail.sbs",
            duckmail_api_key=str(duckmail_api_key_raw or "").strip(),
            duckmail_verify_ssl=_parse_bool(basic_data.get("duckmail_verify_ssl"), True),
            
            gptmail_base_url=basic_data.get("gptmail_base_url") or "https://mail.chatgpt.org.uk",
            gptmail_api_key=str(gptmail_api_key_raw or "").strip(),
            gptmail_verify_ssl=_parse_bool(basic_data.get("gptmail_verify_ssl"), True),
            gptmail_domain=str(basic_data.get("gptmail_domain") or "").strip(),
            
            freemail_base_url=basic_data.get("freemail_base_url") or "http://your-freemail-server.com",
            freemail_jwt_token=str(basic_data.get("freemail_jwt_token") or "").strip(),
            freemail_verify_ssl=_parse_bool(basic_data.get("freemail_verify_ssl"), True),
            freemail_domain=str(basic_data.get("freemail_domain") or "").strip(),
            
            moemail_base_url=basic_data.get("moemail_base_url") or "https://moemail.app",
            moemail_api_key=str(basic_data.get("moemail_api_key") or "").strip(),
            moemail_domain=str(basic_data.get("moemail_domain") or "").strip(),
            
            mail_proxy_enabled=_parse_bool(basic_data.get("mail_proxy_enabled"), False),
            
            browser_engine=basic_data.get("browser_engine") or "dp",
            browser_headless=_parse_bool(basic_data.get("browser_headless"), False),
            refresh_window_hours=_parse_int(refresh_window_raw, 1),
            register_default_count=_parse_int(register_default_raw, 1),
            register_domain=str(register_domain_raw or "").strip(),
        )

        # [新增] 环境区分：如果设置了 LOCAL_IGNORE_PROXY，强制忽略账户和邮箱代理
        local_ignore = _parse_bool(os.getenv("LOCAL_IGNORE_PROXY"), False)
        if local_ignore:
            print("[CONFIG] 🚀 检测到 LOCAL_IGNORE_PROXY=1，已强制忽略账户/邮箱代理设置")
            basic_config.proxy_for_auth = ""
            basic_config.mail_proxy_enabled = False

        # 4. 加载其他配置（从 YAML）
        image_generation_config = ImageGenerationConfig(
            **yaml_data.get("image_generation", {})
        )

        # 加载视频生成配置
        video_generation_config = VideoGenerationConfig(
            **yaml_data.get("video_generation", {})
        )

        # 加载重试配置，自动修正不在 1-12 小时范围内的值
        retry_data = yaml_data.get("retry", {})
        if "rate_limit_cooldown_seconds" in retry_data:
            value = retry_data["rate_limit_cooldown_seconds"]
            if value < 3600 or value > 43200:  # 不在 1-12 小时范围，默认 1 小时
                retry_data["rate_limit_cooldown_seconds"] = 3600

        retry_config = RetryConfig(**retry_data)

        public_display_config = PublicDisplayConfig(
            **yaml_data.get("public_display", {})
        )

        session_config = SessionConfig(
            **yaml_data.get("session", {})
        )

        # 5. 构建完整配置
        self._config = AppConfig(
            security=security_config,
            basic=basic_config,
            image_generation=image_generation_config,
            video_generation=video_generation_config,
            retry=retry_config,
            public_display=public_display_config,
            session=session_config
        )

    def _load_yaml(self) -> dict:
        """加载 YAML 文件"""
        if storage.is_database_enabled():
            try:
                data = storage.load_settings_sync()
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"[WARN] 加载数据库设置失败: {e}，使用本地配置")
        if self.yaml_path.exists():
            try:
                with open(self.yaml_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"[WARN] 加载配置文件失败: {e}，使用默认配置")
        return {}

    def _merge_api_keys_from_file(self, config_data: dict, file_data: dict) -> bool:
        """
        将 file_data 中的新 API Key 合并到 config_data (DB配置) 中
        返回是否发生了变更
        """
        changed = False
        
        # 确保基本结构存在
        basic_config = config_data.get("basic", {})
        if "basic" not in config_data:
            config_data["basic"] = basic_config
            changed = True
            
        existing_keys = basic_config.get("api_keys", [])
        if "api_keys" not in basic_config:
            basic_config["api_keys"] = existing_keys
            # 注意：即便这里初始化为空列表，但不一定视为change，取决于是否有新key加入
        
        # 构建现有 Key 的集合（用于快速查重）
        existing_key_values = {k.get("key") for k in existing_keys if isinstance(k, dict) and "key" in k}
        
        # 遍历文件的配置
        file_basic = file_data.get("basic", {})
        file_keys = file_basic.get("api_keys", [])
        
        for item in file_keys:
            if not isinstance(item, dict):
                continue
            
            key_val = item.get("key")
            if key_val and key_val not in existing_key_values:
                # 发现新 Key，添加并标记变更
                # 补充默认字段（与 Config Model 保持一致）
                new_entry = {
                    "key": key_val,
                    "mode": item.get("mode", "memory"),
                    "remark": item.get("remark", "") or "Auto-synced from static config",
                    "created_at": item.get("created_at", int(time.time()))
                }
                existing_keys.append(new_entry)
                existing_key_values.add(key_val) # 防止重复添加
                changed = True
                print(f"[CONFIG] 同步新 Key: {key_val[:8]}... (Mode: {new_entry['mode']})")
                
        return changed

    def _generate_secret(self) -> str:
        """生成随机密钥"""
        return secrets.token_urlsafe(32)

    def save_yaml(self, data: dict):
        """保存 YAML 配置"""
        if storage.is_database_enabled():
            try:
                saved = storage.save_settings_sync(data)
                if saved:
                    return
            except Exception as e:
                print(f"[WARN] 保存数据库设置失败: {e}，降级到本地文件")
        self.yaml_path.parent.mkdir(exist_ok=True)
        with open(self.yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def reload(self):
        """重新加载配置（热更新）"""
        self.load()

    @property
    def config(self) -> AppConfig:
        """获取配置"""
        return self._config

    # ==================== 便捷访问属性 ====================

    @property
    def api_key(self) -> str:
        """API访问密钥"""
        return self._config.basic.api_key

    @property
    def admin_key(self) -> str:
        """管理员密钥"""
        return self._config.security.admin_key

    @property
    def session_secret_key(self) -> str:
        """Session密钥"""
        return self._config.security.session_secret_key

    @property
    def proxy_for_auth(self) -> str:
        """账户操作代理地址"""
        return self._config.basic.proxy_for_auth

    @property
    def proxy_for_chat(self) -> str:
        """对话操作代理地址"""
        return self._config.basic.proxy_for_chat

    @property
    def base_url(self) -> str:
        """服务器URL"""
        return self._config.basic.base_url

    @property
    def logo_url(self) -> str:
        """Logo URL"""
        return self._config.public_display.logo_url

    @property
    def chat_url(self) -> str:
        """开始对话链接"""
        return self._config.public_display.chat_url

    @property
    def image_generation_enabled(self) -> bool:
        """是否启用图片生成"""
        return self._config.image_generation.enabled

    @property
    def image_generation_models(self) -> List[str]:
        """支持图片生成的模型列表"""
        return self._config.image_generation.supported_models

    @property
    def image_output_format(self) -> str:
        """图片输出格式"""
        return self._config.image_generation.output_format

    @property
    def video_output_format(self) -> str:
        """视频输出格式"""
        return self._config.video_generation.output_format

    @property
    def session_expire_hours(self) -> int:
        """Session过期时间（小时）"""
        return self._config.session.expire_hours

    @property
    def max_new_session_tries(self) -> int:
        """新会话尝试账户数"""
        return self._config.retry.max_new_session_tries

    @property
    def max_request_retries(self) -> int:
        """请求失败重试次数"""
        return self._config.retry.max_request_retries

    @property
    def max_account_switch_tries(self) -> int:
        """账户切换尝试次数"""
        return self._config.retry.max_account_switch_tries

    @property
    def account_failure_threshold(self) -> int:
        """账户失败阈值"""
        return self._config.retry.account_failure_threshold

    @property
    def rate_limit_cooldown_seconds(self) -> int:
        """429冷却时间（秒）"""
        return self._config.retry.rate_limit_cooldown_seconds

    @property
    def session_cache_ttl_seconds(self) -> int:
        """会话缓存时间（秒）"""
        return self._config.retry.session_cache_ttl_seconds

    @property
    def auto_refresh_accounts_seconds(self) -> int:
        """自动刷新账号间隔（秒，0禁用）"""
        return self._config.retry.auto_refresh_accounts_seconds


# ==================== 全局配置管理器 ====================

config_manager = ConfigManager()

# 注意：不要直接引用 config_manager.config，因为 reload() 后引用会失效
# 应该始终通过 config_manager.config 访问配置
def get_config() -> AppConfig:
    """获取当前配置（支持热更新）"""
    return config_manager.config

# 为了向后兼容，保留 config 变量，但使用属性访问
class _ConfigProxy:
    """配置代理，确保始终访问最新配置"""
    @property
    def basic(self):
        return config_manager.config.basic

    @property
    def security(self):
        return config_manager.config.security

    @property
    def image_generation(self):
        return config_manager.config.image_generation

    @property
    def video_generation(self):
        return config_manager.config.video_generation

    @property
    def retry(self):
        return config_manager.config.retry

    @property
    def public_display(self):
        return config_manager.config.public_display

    @property
    def session(self):
        return config_manager.config.session

config = _ConfigProxy()

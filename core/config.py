"""
统一配置管理系统

优先级规则：
1. 安全配置：仅环境变量（ADMIN_KEY, SESSION_SECRET_KEY）
2. 业务配置：数据库 > 默认值

配置分类：
- 安全配置：仅从环境变量读取，不可热更新（ADMIN_KEY, SESSION_SECRET_KEY）
- 业务配置：仅从数据库读取，支持热更新（API_KEY, BASE_URL, PROXY, 重试策略等）
"""

import os
import shutil
import yaml
import secrets
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

from core import storage

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


# ==================== 配置模型定义 ====================

class BasicConfig(BaseModel):
    """基础配置"""
    api_key: str = Field(default="", description="API访问密钥（留空则公开访问，多个密钥用逗号分隔）")
    base_url: str = Field(default="", description="服务器URL（留空则自动检测）")
    proxy_for_auth: str = Field(default="", description="账户操作代理地址（注册/登录/刷新，留空则不使用代理）")
    proxy_for_chat: str = Field(default="", description="对话操作代理地址（JWT/会话/消息，留空则不使用代理）")
    duckmail_base_url: str = Field(default="https://api.duckmail.sbs", description="DuckMail API地址")
    duckmail_api_key: str = Field(default="", description="DuckMail API key")
    duckmail_verify_ssl: bool = Field(default=True, description="DuckMail SSL校验")
    temp_mail_provider: str = Field(default="moemail", description="临时邮箱提供商: moemail/duckmail/freemail/gptmail")
    moemail_base_url: str = Field(default="https://moemail.nanohajimi.mom", description="Moemail API地址")
    moemail_api_key: str = Field(default="", description="Moemail API key")
    moemail_domain: str = Field(default="", description="Moemail 邮箱域名（可选，留空则随机选择）")
    freemail_base_url: str = Field(default="http://your-freemail-server.com", description="Freemail API地址")
    freemail_jwt_token: str = Field(default="", description="Freemail JWT Token")
    freemail_verify_ssl: bool = Field(default=True, description="Freemail SSL校验")
    freemail_domain: str = Field(default="", description="Freemail 邮箱域名（可选，留空则随机选择）")
    mail_proxy_enabled: bool = Field(default=False, description="是否启用临时邮箱代理（使用账户操作代理）")
    gptmail_base_url: str = Field(default="https://mail.chatgpt.org.uk", description="GPTMail API地址")
    gptmail_api_key: str = Field(default="gpt-test", description="GPTMail API key")
    gptmail_verify_ssl: bool = Field(default=True, description="GPTMail SSL校验")
    gptmail_domain: str = Field(default="", description="GPTMail 邮箱域名（可选，留空则随机选择）")
    browser_engine: str = Field(default="dp", description="浏览器引擎")
    browser_headless: bool = Field(default=False, description="自动化浏览器无头模式")
    refresh_window_hours: int = Field(default=1, ge=0, le=24, description="过期刷新窗口（小时）")
    register_default_count: int = Field(default=1, ge=1, description="默认注册数量")
    register_domain: str = Field(default="", description="DuckMail 域名（推荐）")


class ImageGenerationConfig(BaseModel):
    """图片生成配置"""
    enabled: bool = Field(default=False, description="是否启用图片生成")
    supported_models: List[str] = Field(
        default=[],
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
    max_account_switch_tries: int = Field(default=5, ge=1, le=20, description="账户切换尝试次数")
    rate_limit_cooldown_seconds: int = Field(default=7200, ge=3600, le=43200, description="429冷却时间（秒）")
    text_rate_limit_cooldown_seconds: int = Field(default=7200, ge=3600, le=86400, description="对话配额冷却（秒）")
    images_rate_limit_cooldown_seconds: int = Field(default=14400, ge=3600, le=86400, description="绘图配额冷却（秒）")
    videos_rate_limit_cooldown_seconds: int = Field(default=14400, ge=3600, le=86400, description="视频配额冷却（秒）")
    session_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400, description="会话缓存时间（秒，0表示禁用缓存）")
    auto_refresh_accounts_seconds: int = Field(default=60, ge=0, le=600, description="自动刷新账号间隔（秒，0禁用）")
    # 定时刷新配置
    scheduled_refresh_enabled: bool = Field(default=False, description="是否启用定时刷新任务")
    scheduled_refresh_interval_minutes: int = Field(default=30, ge=0, le=720, description="定时刷新检测间隔（分钟，0-12小时）")

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

    # 业务配置（环境变量 > 数据库 > 默认值）
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
            yaml_path = ""
        self.yaml_path = Path(yaml_path)
        self._config: Optional[AppConfig] = None
        self.load()

    def load(self):
        """
        加载配置

        优先级规则：
        1. 安全配置（ADMIN_KEY, SESSION_SECRET_KEY）：仅从环境变量读取
        2. 业务配置：数据库 > 默认值
        """
        # 1. 从数据库加载配置
        yaml_data = self._load_yaml()

        # 2. 加载安全配置（仅从环境变量，不允许 Web 修改）
        security_config = SecurityConfig(
            admin_key=os.getenv("ADMIN_KEY", ""),
            session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret())
        )

        # 3. 加载基础配置（数据库 > 默认值）
        basic_data = yaml_data.get("basic", {})
        refresh_window_raw = basic_data.get("refresh_window_hours", 1)
        register_default_raw = basic_data.get("register_default_count", 1)
        register_domain_raw = basic_data.get("register_domain", "")
        duckmail_api_key_raw = basic_data.get("duckmail_api_key", "")

        # 兼容旧配置：如果存在旧的 proxy 字段，迁移到新字段
        old_proxy = basic_data.get("proxy", "")
        old_proxy_for_auth_bool = basic_data.get("proxy_for_auth")
        old_proxy_for_chat_bool = basic_data.get("proxy_for_chat")

        # 新配置优先，如果没有新配置则从旧配置迁移
        proxy_for_auth = basic_data.get("proxy_for_auth", "")
        proxy_for_chat = basic_data.get("proxy_for_chat", "")

        # 如果新配置为空且存在旧配置，则迁移
        if not proxy_for_auth and old_proxy:
            # 如果旧配置中 proxy_for_auth 是布尔值且为 True，则使用旧的 proxy
            if isinstance(old_proxy_for_auth_bool, bool) and old_proxy_for_auth_bool:
                proxy_for_auth = old_proxy

        if not proxy_for_chat and old_proxy:
            # 如果旧配置中 proxy_for_chat 是布尔值且为 True，则使用旧的 proxy
            if isinstance(old_proxy_for_chat_bool, bool) and old_proxy_for_chat_bool:
                proxy_for_chat = old_proxy

        basic_config = BasicConfig(
            api_key=basic_data.get("api_key") or "",
            base_url=basic_data.get("base_url") or "",
            proxy_for_auth=str(proxy_for_auth or "").strip(),
            proxy_for_chat=str(proxy_for_chat or "").strip(),
            duckmail_base_url=basic_data.get("duckmail_base_url") or "https://api.duckmail.sbs",
            duckmail_api_key=str(duckmail_api_key_raw or "").strip(),
            duckmail_verify_ssl=_parse_bool(basic_data.get("duckmail_verify_ssl"), True),
            temp_mail_provider=basic_data.get("temp_mail_provider") or "moemail",
            moemail_base_url=basic_data.get("moemail_base_url") or "https://moemail.nanohajimi.mom",
            moemail_api_key=str(basic_data.get("moemail_api_key") or "").strip(),
            moemail_domain=str(basic_data.get("moemail_domain") or "").strip(),
            freemail_base_url=basic_data.get("freemail_base_url") or "http://your-freemail-server.com",
            freemail_jwt_token=str(basic_data.get("freemail_jwt_token") or "").strip(),
            freemail_verify_ssl=_parse_bool(basic_data.get("freemail_verify_ssl"), True),
            freemail_domain=str(basic_data.get("freemail_domain") or "").strip(),
            mail_proxy_enabled=_parse_bool(basic_data.get("mail_proxy_enabled"), False),
            gptmail_base_url=str(basic_data.get("gptmail_base_url") or "https://mail.chatgpt.org.uk").strip(),
            gptmail_api_key=str(basic_data.get("gptmail_api_key") or "").strip(),
            gptmail_verify_ssl=_parse_bool(basic_data.get("gptmail_verify_ssl"), True),
            gptmail_domain=str(basic_data.get("gptmail_domain") or "").strip(),
            browser_engine=basic_data.get("browser_engine") or "dp",
            browser_headless=_parse_bool(basic_data.get("browser_headless"), False),
            refresh_window_hours=int(refresh_window_raw),
            register_default_count=int(register_default_raw),
            register_domain=str(register_domain_raw or "").strip(),
        )

        # 4. 加载其他配置（从数据库，带容错处理）
        try:
            image_generation_config = ImageGenerationConfig(
                **yaml_data.get("image_generation", {})
            )
        except Exception as e:
            print(f"[WARN] 图片生成配置加载失败，使用默认值: {e}")
            image_generation_config = ImageGenerationConfig()

        # 加载视频生成配置
        try:
            video_generation_config = VideoGenerationConfig(
                **yaml_data.get("video_generation", {})
            )
        except Exception as e:
            print(f"[WARN] 视频生成配置加载失败，使用默认值: {e}")
            video_generation_config = VideoGenerationConfig()

        # 加载重试配置（Pydantic 会自动验证范围）
        try:
            retry_config = RetryConfig(**yaml_data.get("retry", {}))
        except Exception as e:
            print(f"[WARN] 重试配置加载失败，使用默认值: {e}")
            retry_config = RetryConfig()

        try:
            public_display_config = PublicDisplayConfig(
                **yaml_data.get("public_display", {})
            )
        except Exception as e:
            print(f"[WARN] 公开展示配置加载失败，使用默认值: {e}")
            public_display_config = PublicDisplayConfig()

        try:
            session_config = SessionConfig(
                **yaml_data.get("session", {})
            )
        except Exception as e:
            print(f"[WARN] Session配置加载失败，使用默认值: {e}")
            session_config = SessionConfig()

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
        """从数据库加载配置（允许空配置）。"""
        if storage.is_database_enabled():
            try:
                data = storage.load_settings_sync()

                # 允许空库启动：None 可能是空配置或连接异常
                if data is None:
                    print("[WARN] 未读取到 settings（可能为空库或连接异常），将使用默认配置启动")
                    return {}

                if isinstance(data, dict):
                    return data

                return {}
            except RuntimeError:
                # 重新抛出 RuntimeError
                raise
            except Exception as e:
                print(f"[ERROR] 数据库加载失败: {e}")
                raise RuntimeError(f"数据库加载失败: {e}")

        print("[ERROR] 未启用数据库")
        raise RuntimeError("未配置 DATABASE_URL，应用无法启动")

    def _generate_secret(self) -> str:
        """生成随机密钥"""
        return secrets.token_urlsafe(32)

    def save_yaml(self, data: dict):
        """保存配置到数据库（先验证再保存）"""
        if not storage.is_database_enabled():
            raise RuntimeError("Database is not enabled")

        # 先验证数据是否符合 Pydantic 模型要求
        try:
            # 构建临时配置进行验证
            security_config = SecurityConfig(
                admin_key=os.getenv("ADMIN_KEY", ""),
                session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret())
            )

            basic_data = data.get("basic", {})
            basic_config = BasicConfig(**basic_data)

            image_generation_config = ImageGenerationConfig(
                **data.get("image_generation", {})
            )

            video_generation_config = VideoGenerationConfig(
                **data.get("video_generation", {})
            )

            retry_config = RetryConfig(**data.get("retry", {}))

            public_display_config = PublicDisplayConfig(
                **data.get("public_display", {})
            )

            session_config = SessionConfig(
                **data.get("session", {})
            )

            # 验证通过，构建完整配置
            test_config = AppConfig(
                security=security_config,
                basic=basic_config,
                image_generation=image_generation_config,
                video_generation=video_generation_config,
                retry=retry_config,
                public_display=public_display_config,
                session=session_config
            )
        except Exception as e:
            # 验证失败，不保存到数据库
            raise ValueError(f"配置验证失败: {str(e)}")

        # 验证通过后才保存到数据库
        try:
            saved = storage.save_settings_sync(data)
            if saved:
                return
        except Exception as e:
            print(f"[WARN] 数据库保存失败: {e}")
        raise RuntimeError("Database write failed")

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
    def max_account_switch_tries(self) -> int:
        """账户切换尝试次数"""
        return self._config.retry.max_account_switch_tries

    @property
    def rate_limit_cooldown_seconds(self) -> int:
        # 429 cooldown (seconds)
        if hasattr(self._config.retry, 'text_rate_limit_cooldown_seconds'):
            return self._config.retry.text_rate_limit_cooldown_seconds
        return self._config.retry.rate_limit_cooldown_seconds

    @property
    def text_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.text_rate_limit_cooldown_seconds

    @property
    def images_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.images_rate_limit_cooldown_seconds

    @property
    def videos_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.videos_rate_limit_cooldown_seconds

    @property
    def session_cache_ttl_seconds(self) -> int:
        # Session cache TTL (seconds)
        return self._config.retry.session_cache_ttl_seconds

    @property
    def auto_refresh_accounts_seconds(self) -> int:
        # Auto refresh accounts interval (seconds)
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

"""
统一配置管理系统

优先级规则：
1. 环境变量（最高优先级）
2. YAML 配置文件
3. 默认值（最低优先级）

配置分类：
- 安全配置：仅从环境变量读取，不可热更新（ADMIN_KEY, PATH_PREFIX, SESSION_SECRET_KEY）
- 业务配置：环境变量 > YAML，支持热更新（API_KEY, PROXY, 重试策略等）
"""

import os
import yaml
import secrets
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


# ==================== 配置模型定义 ====================

class BasicConfig(BaseModel):
    """基础配置"""
    api_key: str = Field(default="", description="API访问密钥（留空则公开访问）")
    base_url: str = Field(default="", description="服务器URL（留空则自动检测）")
    proxy: str = Field(default="", description="代理地址")


class ImageGenerationConfig(BaseModel):
    """图片生成配置"""
    enabled: bool = Field(default=True, description="是否启用图片生成")
    supported_models: List[str] = Field(
        default=["gemini-3-pro-preview"],
        description="支持图片生成的模型列表"
    )


class RetryConfig(BaseModel):
    """重试策略配置"""
    max_new_session_tries: int = Field(default=5, ge=1, le=20, description="新会话尝试账户数")
    max_request_retries: int = Field(default=3, ge=1, le=10, description="请求失败重试次数")
    max_account_switch_tries: int = Field(default=5, ge=1, le=20, description="账户切换尝试次数")
    account_failure_threshold: int = Field(default=3, ge=1, le=10, description="账户失败阈值")
    rate_limit_cooldown_seconds: int = Field(default=600, ge=60, le=3600, description="429冷却时间（秒）")
    session_cache_ttl_seconds: int = Field(default=3600, ge=300, le=86400, description="会话缓存时间（秒）")


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
    path_prefix: str = Field(default="", description="路径前缀（隐藏管理端点）")
    session_secret_key: str = Field(..., description="Session密钥")


class AppConfig(BaseModel):
    """应用配置（统一管理）"""
    # 安全配置（仅从环境变量）
    security: SecurityConfig

    # 业务配置（环境变量 > YAML > 默认值）
    basic: BasicConfig
    image_generation: ImageGenerationConfig
    retry: RetryConfig
    public_display: PublicDisplayConfig
    session: SessionConfig


# ==================== 配置管理器 ====================

class ConfigManager:
    """配置管理器（单例）"""

    def __init__(self, yaml_path: str = "data/settings.yaml"):
        self.yaml_path = Path(yaml_path)
        self._config: Optional[AppConfig] = None
        self.load()

    def load(self):
        """
        加载配置

        优先级规则：
        1. 安全配置（ADMIN_KEY, PATH_PREFIX, SESSION_SECRET_KEY）：仅从环境变量读取
        2. 其他配置：YAML > 环境变量 > 默认值
        """
        # 1. 加载 YAML 配置
        yaml_data = self._load_yaml()

        # 2. 加载安全配置（仅从环境变量，不允许 Web 修改）
        security_config = SecurityConfig(
            admin_key=os.getenv("ADMIN_KEY", ""),
            path_prefix=os.getenv("PATH_PREFIX", ""),
            session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret())
        )

        # 3. 加载基础配置（YAML > 环境变量 > 默认值）
        basic_data = yaml_data.get("basic", {})
        basic_config = BasicConfig(
            api_key=basic_data.get("api_key") or os.getenv("API_KEY", ""),
            base_url=basic_data.get("base_url") or os.getenv("BASE_URL", ""),
            proxy=basic_data.get("proxy") or os.getenv("PROXY", "")
        )

        # 4. 加载其他配置（从 YAML）
        image_generation_config = ImageGenerationConfig(
            **yaml_data.get("image_generation", {})
        )

        retry_config = RetryConfig(
            **yaml_data.get("retry", {})
        )

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
            retry=retry_config,
            public_display=public_display_config,
            session=session_config
        )

    def _load_yaml(self) -> dict:
        """加载 YAML 文件"""
        if self.yaml_path.exists():
            try:
                with open(self.yaml_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"[WARN] 加载配置文件失败: {e}，使用默认配置")
        return {}

    def _generate_secret(self) -> str:
        """生成随机密钥"""
        return secrets.token_urlsafe(32)

    def save_yaml(self, data: dict):
        """保存 YAML 配置"""
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
    def path_prefix(self) -> str:
        """路径前缀"""
        return self._config.security.path_prefix

    @property
    def session_secret_key(self) -> str:
        """Session密钥"""
        return self._config.security.session_secret_key

    @property
    def proxy(self) -> str:
        """代理地址"""
        return self._config.basic.proxy

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
    def retry(self):
        return config_manager.config.retry

    @property
    def public_display(self):
        return config_manager.config.public_display

    @property
    def session(self):
        return config_manager.config.session

config = _ConfigProxy()

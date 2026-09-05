"""
配置管理模块 — 读取YAML配置文件，全局可访问

术语讲解：
- 配置文件：把可变的参数放在单独文件里，改参数不用动代码
- YAML：一种人能看懂的配置格式，用缩进表示层级
- 单例模式：整个程序只有一个配置实例
"""

import os
import yaml
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 项目根目录（根据这个文件的位置推算）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 默认配置文件路径
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "settings.yaml")


class Config:
    """
    配置管理类（单例模式）

    使用方法：
        config = Config()
        db_path = config.get("database.path")
        threshold = config.get("thresholds.hundred_orders", 100)
    """

    _instance: Optional["Config"] = None

    def __new__(cls, config_path: str = None):
        """单例模式：确保整个程序只有一个Config实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str = None):
        if self._initialized:
            return
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: Dict[str, Any] = {}
        self.load()
        self._initialized = True

    def load(self) -> None:
        """加载配置文件"""
        if not os.path.exists(self._config_path):
            logger.warning(f"配置文件不存在: {self._config_path}，使用默认配置")
            self._config = self._default_config()
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"配置文件加载成功: {self._config_path}")
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}，使用默认配置")
            self._config = self._default_config()

    def reload(self) -> None:
        """重新加载配置（热更新）"""
        self.load()
        logger.info("配置已重新加载")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持点号路径

        Args:
            key: 配置键，支持点号分隔，如 "database.path"
            default: 默认值，如果键不存在返回此值

        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """
        设置配置值（运行时修改，不写入文件）

        Args:
            key: 配置键，支持点号分隔
            value: 要设置的值
        """
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def get_all(self) -> Dict[str, Any]:
        """获取全部配置"""
        return self._config.copy()

    def _default_config(self) -> Dict[str, Any]:
        """默认配置（配置文件不存在时使用）"""
        return {
            "database": {"path": "data/ecommerce.db", "echo_sql": False},
            "thresholds": {"hundred_orders": 100, "thousand_orders": 1000},
            "stop_test_rules": {
                "by_cost": {"enabled": True, "max_cost": 300, "min_orders": 0},
                "by_duration": {"enabled": True, "max_hours": 72, "min_orders": 0},
            },
            "order_trigger": {"min_orders": 1},
            "logging": {"level": "INFO", "file_path": "logs/app.log"},
            "agent": {"model": "qwen3-max", "temperature": 0.1},
            "api": {"host": "0.0.0.0", "port": 8000},
        }


def get_config(config_path: str = None) -> Config:
    """获取全局配置实例"""
    return Config(config_path)

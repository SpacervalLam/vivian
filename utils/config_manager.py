import os
import platform
import re
from typing import Any, Dict

import yaml
from loguru import logger


class ConfigManager:
    """配置管理器，支持YAML格式和环境变量"""

    def __init__(self, config_file: str = "config.yaml"):
        self.app_dir = self._get_user_data_dir()
        os.makedirs(self.app_dir, exist_ok=True)
        self.config_file = os.path.join(self.app_dir, config_file)
        self.default_config = self._get_default_config()
        self.config = self.default_config.copy()
        self._load_config()

    def _get_user_data_dir(self) -> str:
        """获取用户数据目录"""
        app_name = "Vivian"
        system = platform.system()
        if system == "Windows":
            return os.path.join(os.environ.get("APPDATA", ""), app_name)
        elif system == "Darwin":
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", app_name)
        else:
            return os.path.join(os.path.expanduser("~"), ".config", app_name)

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "base": {
                "model_path": os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "Vivian",
                    "Vivian.model3.json",
                ),
                "language": "zh-CN",
            },
            "window": {
                "width": 800,
                "height": 800,
                "title": "薇薇安桌宠",
                "max_size": [10000, 10000],
            },
            "live2d_render": {
                "smooth_speed": 0.1,
                "angle_range": 30.0,
                "eye_smooth_speed": 0.25,
                "mouth_smooth_speed": 0.005,
                "breath_interval": 150,
                "blink_interval": 500,
            },
            "ai": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": None,
                "endpoint": None,
                "temperature": 0.7,
                "max_tokens": 2000,
                "use_proxy": False,
                "proxy_type": "http",
                "proxy_host": "",
                "proxy_port": None,
                "proxy_auth": False,
                "proxy_username": "",
                "proxy_password": "",
                "local_model_path": "",
                "local_model_n_ctx": 2048,
                "local_model_n_threads": 4,
                "local_model_n_gpu_layers": 0,
                "enable_disk_cache": False,
                "cache_dir": None,
                "enable_local_proactive": True,
            },
            "memory": {
                "max_short_term_memory": 20,
                "memory_importance_threshold": 0.7,
                "enable_semantic_memory": True,
                "embedding_model_path": "",
                "retrieval_strategy": "auto",
                "vector_store_type": "chroma",
                "enable_expiration": True,
                "expiration_interval": 10,
            },
            "new_architecture": {
                "enabled": False,
                "enable_message_system": False,
                "enable_permission_system": False,
                "enable_query_engine": False,
                "enable_tool_system": False,
                "enable_task_system": False,
            },
            "langchain": {
                "enabled": True,
                "enable_name_cooldown": True,
                "enable_topic_detection": True,
                "cooldown_turns": 4,
                "max_history_length": 10,
            },
            "environment": {
                "monitor_interval": 5,
                "enable_window_monitor": True,
                "enable_clipboard_monitor": False,
            },
            "prompt": {
                "use_modular": True,
                "modules": {
                    "new_session_rules": True,
                    "identity": True,
                    "address_rules": True,
                    "conversation_rhythm": True,
                    "context": True,
                    "memory": True,
                    "history": True,
                    "tools": True,
                    "output_format": True,
                    "few_shot_examples": True,
                },
            },
        }

    def _load_config(self) -> None:
        """从本地文件加载配置"""
        if not os.path.exists(self.config_file):
            logger.warning(f"配置文件不存在: {self.config_file}，将使用默认配置并保存")
            self._save_config()
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                logger.warning(f"配置文件为空，将使用默认配置")
                self._save_config()
                return

            content = self._replace_env_vars(content)
            user_config = yaml.safe_load(content)

            if user_config:
                self._merge_config(self.config, user_config)
                logger.info(f"已从 {self.config_file} 加载配置")
            else:
                logger.warning(f"配置文件解析为空，将使用默认配置")
                self._save_config()

        except yaml.YAMLError as e:
            logger.error(f"解析配置文件失败: {e}，将使用默认配置")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，将使用默认配置")

    def _replace_env_vars(self, content: str) -> str:
        """替换配置中的环境变量"""
        pattern = re.compile(r"\$\{([^}]+)\}")
        def replacer(match):
            env_var = match.group(1)
            return os.getenv(env_var, match.group(0))
        return pattern.sub(replacer, content)

    def _merge_config(self, base: Dict[str, Any], update: Dict[str, Any]) -> None:
        """递归合并配置"""
        for key, value in update.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def _save_config(self) -> None:
        """保存配置到本地文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            temp_file = self.config_file + ".tmp"
            yaml_content = yaml.dump(self.config, allow_unicode=True, default_flow_style=False, sort_keys=False)
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(yaml_content)
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
            os.rename(temp_file, self.config_file)
            logger.info(f"配置已保存到: {self.config_file}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key_path.split(".")
        value = self.config
        try:
            for key in keys:
                value = value[key]
            return value
        except KeyError:
            return default

    def set(self, key_path: str, value: Any) -> None:
        """设置配置值并保存"""
        keys = key_path.split(".")
        config = self.config
        for key in keys[:-1]:
            if key not in config or not isinstance(config[key], dict):
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
        self._save_config()

    def set_many(self, config_dict: dict) -> None:
        """批量设置配置并保存"""
        for key, value in config_dict.items():
            keys = key.split(".")
            d = self.config
            for k in keys[:-1]:
                if k not in d:
                    d[k] = {}
                elif not isinstance(d[k], dict):
                    d[k] = {}
                d = d[k]
            d[keys[-1]] = value
        self._save_config()

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self.config.copy()

    def validate(self) -> bool:
        """验证配置"""
        try:
            model_path = self.get("base.model_path")
            if not os.path.exists(model_path):
                logger.warning(f"Live2D模型路径不存在: {model_path}")
            return True
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False

    def save(self) -> None:
        """保存当前配置到文件"""
        self._save_config()

    def reload(self) -> None:
        """重新加载配置"""
        self.config = self.default_config.copy()
        self._load_config()
        self.validate()


config_manager = ConfigManager()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = config_manager.get("base.model_path")
WINDOW_WIDTH = config_manager.get("window.width")
WINDOW_HEIGHT = config_manager.get("window.height")
WINDOW_TITLE = config_manager.get("window.title")
LIVE2D_RENDER_CONFIG = config_manager.get("live2d_render")
AI_CONFIG = config_manager.get("ai")

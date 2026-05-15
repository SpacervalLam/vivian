import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger


class ResourceLoader:
    """资源加载器"""

    MOTION_EXTENSIONS = {".motion3.json", ".mtn"}
    EXPRESSION_EXTENSIONS = {".exp3.json"}
    TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    MODEL_EXTENSIONS = {".model3.json"}
    PHYSICS_EXTENSIONS = {".physics3.json"}
    CDI_EXTENSIONS = {".cdi3.json"}
    VTUBE_EXTENSIONS = {".vtube.json"}
    CANVAS_EXTENSIONS = {".can3"}
    PINNED_EXTENSIONS = {".json"}

    def __init__(self, base_dir: str, model_dir: str = "Vivian"):
        self.base_dir = Path(base_dir)
        self.model_dir = self.base_dir / model_dir
        self._resources: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> Dict[str, Any]:
        """加载完整资源"""
        logger.debug(f"[ResourceLoader] load() 方法被调用")
        if not self.model_dir.exists():
            logger.warning(f"[ResourceLoader] 模型目录不存在: {self.model_dir}")
            return self._resources

        self._scan_directory(load_all=True)
        self._loaded = True
        logger.info(f"[ResourceLoader] 完整资源加载完成: Motions={len(self._resources.get('motions', {}))}, Expressions={len(self._resources.get('expressions', {}))}, Textures={len(self._resources.get('textures', {}))}, Presets={len(self._resources.get('presets', {}))}")

        return self._resources

    def load_critical(self) -> Dict[str, Any]:
        """仅加载关键资源"""
        logger.debug(f"[ResourceLoader] load_critical() 方法被调用")
        if not self.model_dir.exists():
            logger.warning(f"[ResourceLoader] 模型目录不存在: {self.model_dir}")
            return self._resources

        self._scan_directory(load_all=False)
        self._loaded = False
        logger.debug(f"[ResourceLoader] 关键资源加载完成: Textures={len(self._resources.get('textures', {}))}, Presets={len(self._resources.get('presets', {}))}")

        return self._resources

    def load_background(self) -> Dict[str, Any]:
        """后台加载完整资源"""
        logger.debug(f"[ResourceLoader] load_background() 方法被调用")
        if not self.model_dir.exists():
            logger.warning(f"[ResourceLoader] 模型目录不存在: {self.model_dir}")
            return self._resources

        self._scan_directory(load_all=True)
        self._loaded = True
        logger.info(f"[ResourceLoader] 完整资源加载完成: Motions={len(self._resources.get('motions', {}))}, Expressions={len(self._resources.get('expressions', {}))}, Textures={len(self._resources.get('textures', {}))}, Presets={len(self._resources.get('presets', {}))}")

        return self._resources

    def reload(self) -> Dict[str, Any]:
        """重新加载资源"""
        self._resources = {}
        self._loaded = False
        return self.load()

    def _scan_directory(self, load_all: bool = True):
        """扫描目录并加载资源"""
        motions: Dict[str, Dict[str, Any]] = self._resources.get("motions", {})
        expressions: Dict[str, Dict[str, Any]] = self._resources.get("expressions", {})
        textures: List[Dict[str, Any]] = self._resources.get("textures", [])
        presets: Dict[str, Dict[str, Any]] = self._resources.get("presets", {})

        logger.debug(f"[ResourceLoader] 开始扫描目录: {self.model_dir}, load_all: {load_all}")

        critical_extensions = {
            *self.TEXTURE_EXTENSIONS,
            *self.MODEL_EXTENSIONS,
            *self.PHYSICS_EXTENSIONS,
            *self.CDI_EXTENSIONS,
        }

        for file_path in self.model_dir.iterdir():
            if file_path.is_file():
                file_name = str(file_path.name)
                if file_name.endswith(".exp3.json"):
                    ext = ".exp3.json"
                elif file_name.endswith(".motion3.json"):
                    ext = ".motion3.json"
                else:
                    ext = file_path.suffix.lower()
                relative_path = str(file_path.relative_to(self.model_dir))

                if ext in critical_extensions:
                    if ext in self.TEXTURE_EXTENSIONS:
                        if "texture_0" in file_path.name:
                            if not any(t["name"] == file_path.name for t in textures):
                                textures.append(
                                    {
                                        "path": str(file_path),
                                        "name": file_path.name,
                                        "relative_path": relative_path,
                                        "index": self._extract_texture_index(
                                            file_path.name
                                        ),
                                    }
                                )
                                logger.debug(f"[ResourceLoader] 加载纹理: {file_path.name}")

                    elif ext in self.MODEL_EXTENSIONS and "model" not in presets:
                        presets["model"] = {
                            "path": str(file_path),
                            "name": file_path.stem,
                            "relative_path": relative_path,
                            "type": "model",
                        }
                        logger.debug(f"[ResourceLoader] 加载模型: {file_path.stem}")

                    elif ext in self.PHYSICS_EXTENSIONS and "physics" not in presets:
                        presets["physics"] = {
                            "path": str(file_path),
                            "name": file_path.stem,
                            "relative_path": relative_path,
                            "type": "physics",
                        }
                        logger.debug(f"[ResourceLoader] 加载物理配置: {file_path.stem}")

                    elif ext in self.CDI_EXTENSIONS and "cdi" not in presets:
                        presets["cdi"] = {
                            "path": str(file_path),
                            "name": file_path.stem,
                            "relative_path": relative_path,
                            "type": "cdi",
                        }
                        logger.debug(f"[ResourceLoader] 加载CDI配置: {file_path.stem}")

                elif load_all:
                    if ext in self.MOTION_EXTENSIONS:
                        base_name = file_path.name.replace(".motion3.json", "").replace(
                            ".mtn", ""
                        )
                        if base_name not in motions:
                            motion_info = self._parse_motion_file(file_path)
                            motions[base_name] = {
                                "path": str(file_path),
                                "name": base_name,
                                "relative_path": relative_path,
                                "extension": ext,
                                **motion_info,
                            }
                            logger.debug(f"[ResourceLoader] 加载动作: {base_name}")

                    elif ext in self.EXPRESSION_EXTENSIONS:
                        base_name = file_path.name.replace(".exp3.json", "")
                        if base_name not in expressions:
                            expression_info = self._parse_expression_file(file_path)
                            expressions[base_name] = {
                                "path": str(file_path),
                                "name": base_name,
                                "relative_path": relative_path,
                                "extension": ext,
                                **expression_info,
                            }
                            logger.debug(f"[ResourceLoader] 加载表情: {base_name}")

                    elif ext in self.VTUBE_EXTENSIONS and "vtube" not in presets:
                        presets["vtube"] = {
                            "path": str(file_path),
                            "name": file_path.stem,
                            "relative_path": relative_path,
                            "type": "vtube",
                        }
                        logger.debug(f"[ResourceLoader] 加载VTube配置: {file_path.stem}")

                    elif ext in self.CANVAS_EXTENSIONS and "canvas" not in presets:
                        presets["canvas"] = {
                            "path": str(file_path),
                            "name": file_path.stem,
                            "relative_path": relative_path,
                            "type": "canvas",
                        }
                        logger.debug(f"[ResourceLoader] 加载Canvas配置: {file_path.stem}")

        textures.sort(key=lambda x: x.get("index", 0))

        self._resources = {
            "motions": motions,
            "expressions": expressions,
            "textures": textures,
            "presets": presets,
        }

    def _parse_motion_file(self, file_path: Path) -> Dict[str, Any]:
        """解析动作文件"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                meta = data.get("Meta", {})
                return {
                    "duration": meta.get("Duration", 0),
                    "fps": meta.get("Fps", 30),
                    "loop": meta.get("Loop", True),
                    "total_frames": meta.get("TotalFrameCount", 0),
                    "curve_count": len(data.get("Curves", [])),
                }
        except Exception as e:
            logger.warning(f"[ResourceLoader] 解析动作文件失败: {file_path}, 错误: {e}")
            return {"duration": 0, "fps": 30, "loop": True, "total_frames": 0}

    def _parse_expression_file(self, file_path: Path) -> Dict[str, Any]:
        """解析表情文件"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "expression_id": data.get("ExpressionName", file_path.stem),
                    "parameter_count": len(data.get("Parameters", [])),
                }
        except Exception as e:
            logger.warning(f"[ResourceLoader] 解析表情文件失败: {file_path}, 错误: {e}")
            return {"expression_id": file_path.stem, "parameter_count": 0}

    def _extract_texture_index(self, filename: str) -> int:
        """提取纹理索引"""
        try:
            if "texture_" in filename:
                return int(filename.replace("texture_", "").replace(".png", ""))
            return 0
        except ValueError:
            return 0

    def get_motion(self, name: str) -> Optional[Dict[str, Any]]:
        """获取动作信息"""
        return self._resources.get("motions", {}).get(name)

    def get_expression(self, name: str) -> Optional[Dict[str, Any]]:
        """获取表情信息"""
        return self._resources.get("expressions", {}).get(name)

    def get_preset(self, preset_type: str) -> Optional[Dict[str, Any]]:
        """获取预设配置"""
        return self._resources.get("presets", {}).get(preset_type)

    def get_all_motions(self) -> Dict[str, Dict[str, Any]]:
        """获取所有动作"""
        return self._resources.get("motions", {})

    def get_all_expressions(self) -> Dict[str, Dict[str, Any]]:
        """获取所有表情"""
        return self._resources.get("expressions", {})

    def get_random_motion(self) -> Optional[Dict[str, Any]]:
        """随机获取动作"""
        motions = self._resources.get("motions", {})
        if motions:
            import random
            return random.choice(list(motions.values()))
        return None

    def get_random_expression(self) -> Optional[Dict[str, Any]]:
        """随机获取表情"""
        expressions = self._resources.get("expressions", {})
        if expressions:
            import random
            return random.choice(list(expressions.values()))
        return None

    def list_motion_names(self) -> List[str]:
        """列出所有动作名称"""
        return list(self._resources.get("motions", {}).keys())

    def list_expression_names(self) -> List[str]:
        """列出所有表情名称"""
        return list(self._resources.get("expressions", {}).keys())

    @property
    def is_loaded(self) -> bool:
        """是否已加载"""
        return self._loaded

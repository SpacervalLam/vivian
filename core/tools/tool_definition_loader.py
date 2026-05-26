"""
工具定义加载器 - Tool Definition Loader

核心功能：
1. 从 Markdown 文件解析工具定义
2. 支持动态加载和热更新
3. 提供工具定义的验证和规范化

Markdown 格式规范：
```markdown
## 工具名称
**描述**: 工具的详细描述
**类型**: action | query | data (可选，默认action)
**参数**:
- 参数名1 (类型): 描述 [必需]
- 参数名2 (类型): 描述 [可选，默认值]
**示例**:
```json
{"tool": "工具名称", "arguments": {"参数名1": "值"}}
```
**返回**: 返回值描述
"""

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


class ToolDefinition:
    """工具定义数据结构"""
    
    def __init__(self):
        self.name: str = ""
        self.description: str = ""
        self.type: str = "action"  # action, query, data
        self.parameters: List[Dict[str, Any]] = []
        self.example: str = ""
        self.returns: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "parameters": self.parameters,
            "example": self.example,
            "returns": self.returns
        }
    
    def to_json_schema(self) -> Dict[str, Any]:
        """转换为 JSON Schema 格式"""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop_type = self._map_type(param.get("type", "string"))
            properties[param["name"]] = {
                "type": prop_type,
                "description": param.get("description", "")
            }
            if param.get("required", False):
                required.append(param["name"])
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    def _map_type(self, type_str: str) -> str:
        """映射类型字符串到 JSON Schema 类型"""
        type_map = {
            "str": "string",
            "string": "string",
            "int": "integer",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "bool": "boolean",
            "boolean": "boolean",
            "list": "array",
            "array": "array",
            "dict": "object",
            "object": "object",
            "any": "string"
        }
        return type_map.get(type_str.lower(), "string")


class ToolDefinitionLoader:
    """
    从 Markdown 文件加载工具定义
    
    支持的 Markdown 格式：
    ## tool_name
    **Description**: Tool description
    **Type**: action | query | data
    **Parameters**:
    - param_name (type): description [required|optional, default=value]
    **Example**:
    ```json
    {"tool": "tool_name", "arguments": {...}}
    ```
    **Returns**: Return value description
    """
    
    def __init__(self):
        self.definitions: Dict[str, ToolDefinition] = {}
        self.last_load_time: float = 0.0
    
    def load_from_file(self, file_path: str) -> bool:
        """
        从 Markdown 文件加载工具定义
        
        Args:
            file_path: Markdown 文件路径
        
        Returns:
            是否加载成功
        """
        if not os.path.exists(file_path):
            logger.warning(f"[ToolLoader] 文件不存在: {file_path}")
            return False
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            tools = self._parse_markdown(content)
            
            if tools:
                self.definitions = {t.name: t for t in tools}
                self.last_load_time = os.path.getmtime(file_path)
                logger.info(f"[ToolLoader] 成功加载 {len(tools)} 个工具定义")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"[ToolLoader] 加载文件失败: {e}")
            return False
    
    def load_from_directory(self, dir_path: str, pattern: str = "*.md") -> int:
        """
        从目录加载所有 Markdown 工具定义文件
        
        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式
        
        Returns:
            成功加载的工具数量
        """
        if not os.path.isdir(dir_path):
            logger.warning(f"[ToolLoader] 目录不存在: {dir_path}")
            return 0
        
        file_pattern = os.path.join(dir_path, pattern)
        files = glob.glob(file_pattern)
        
        # 收集所有文件中的工具定义，避免覆盖
        all_tools = []
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                tools = self._parse_markdown(content)
                all_tools.extend(tools)
                logger.debug(f"[ToolLoader] 从 {file_path} 加载了 {len(tools)} 个工具")
            except Exception as e:
                logger.error(f"[ToolLoader] 加载文件失败 {file_path}: {e}")
        
        # 追加工具定义（不覆盖已存在的）
        new_definitions = {t.name: t for t in all_tools}
        self.definitions.update(new_definitions)
        total_loaded = len(all_tools)
        
        if total_loaded > 0:
            logger.info(f"[ToolLoader] 成功从目录加载 {total_loaded} 个工具定义")
        
        return total_loaded
    
    def _parse_markdown(self, content: str) -> List[ToolDefinition]:
        """
        解析 Markdown 内容提取工具定义
        
        Args:
            content: Markdown 文本内容
        
        Returns:
            工具定义列表
        """
        tools = []
        
        # 匹配工具定义块：## tool_name 开始，到下一个 ## 或文件结束
        tool_pattern = r'##\s*([^\n]+)\n(.*?)(?=\n##\s|$)'
        matches = re.findall(tool_pattern, content, re.DOTALL)
        
        for name, body in matches:
            tool = self._parse_tool_block(name.strip(), body.strip())
            if tool:
                tools.append(tool)
        
        return tools
    
    def _parse_tool_block(self, name: str, body: str) -> Optional[ToolDefinition]:
        """
        解析单个工具定义块
        
        Args:
            name: 工具名称
            body: 工具定义内容
        
        Returns:
            工具定义对象
        """
        tool = ToolDefinition()
        tool.name = name
        
        # 解析描述
        desc_match = re.search(r'\*\*Description\*\*:\s*(.+?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if desc_match:
            tool.description = desc_match.group(1).strip()
        
        # 解析类型
        type_match = re.search(r'\*\*Type\*\*:\s*(\w+)', body)
        if type_match:
            tool.type = type_match.group(1).strip()
        
        # 解析参数
        params_section = re.search(r'\*\*Parameters\*\*:\s*\n((?:- .+\n?)+)', body)
        if params_section:
            tool.parameters = self._parse_parameters(params_section.group(1))
        
        # 解析示例
        example_match = re.search(r'\*\*Example\*\*:\s*\n```(?:json)?\s*([^`]+)```', body, re.DOTALL)
        if example_match:
            tool.example = example_match.group(1).strip()
        
        # 解析返回值
        returns_match = re.search(r'\*\*Returns\*\*:\s*(.+)', body)
        if returns_match:
            tool.returns = returns_match.group(1).strip()
        
        # 验证必需字段
        if not tool.description:
            logger.warning(f"[ToolLoader] 工具 {name} 缺少描述")
            return None
        
        return tool
    
    def _parse_parameters(self, params_text: str) -> List[Dict[str, Any]]:
        """
        解析参数列表
        
        参数格式：
        - param_name (type): description [required|optional, default=value]
        
        Args:
            params_text: 参数文本
        
        Returns:
            参数定义列表
        """
        params = []
        
        # 匹配每个参数行
        param_pattern = r'- ([^\s]+)\s*\(([^)]+)\):\s*(.+)'
        matches = re.findall(param_pattern, params_text)
        
        for name, param_type, rest in matches:
            param = {
                "name": name.strip(),
                "type": param_type.strip(),
                "description": "",
                "required": True,
                "default": None
            }
            
            # 解析描述和可选标记
            # 格式：description [required|optional, default=value]
            parts = rest.split('[')
            param["description"] = parts[0].strip()
            
            if len(parts) > 1:
                options = parts[1].rstrip(']').strip()
                if "optional" in options.lower():
                    param["required"] = False
                
                # 提取默认值
                default_match = re.search(r'default\s*=\s*([^,]+)', options, re.IGNORECASE)
                if default_match:
                    param["default"] = self._parse_default_value(default_match.group(1).strip())
            
            params.append(param)
        
        return params
    
    def _parse_default_value(self, value_str: str) -> Any:
        """
        解析默认值字符串
        
        Args:
            value_str: 默认值字符串
        
        Returns:
            解析后的默认值
        """
        value_str = value_str.strip()
        
        # 尝试解析为 JSON
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            pass
        
        # 尝试解析为数字
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass
        
        # 尝试解析为布尔值
        lower_val = value_str.lower()
        if lower_val == "true":
            return True
        if lower_val == "false":
            return False
        if lower_val == "none":
            return None
        
        # 返回字符串
        return value_str
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """
        获取工具定义
        
        Args:
            name: 工具名称
        
        Returns:
            工具定义对象
        """
        return self.definitions.get(name)
    
    def get_all_tools(self) -> List[ToolDefinition]:
        """获取所有工具定义"""
        return list(self.definitions.values())
    
    def validate_definitions(self) -> List[Tuple[str, str]]:
        """
        验证所有工具定义
        
        Returns:
            错误列表 [(工具名称, 错误描述)]
        """
        errors = []
        
        for name, tool in self.definitions.items():
            if not tool.description:
                errors.append((name, "缺少描述"))
            
            # 检查参数名是否重复
            param_names = [p["name"] for p in tool.parameters]
            if len(param_names) != len(set(param_names)):
                errors.append((name, "参数名重复"))
        
        return errors
    
    def export_to_markdown(self, file_path: str) -> bool:
        """
        将工具定义导出为 Markdown 文件
        
        Args:
            file_path: 输出文件路径
        
        Returns:
            是否导出成功
        """
        try:
            content = self._generate_markdown()
            dirpath = os.path.dirname(file_path)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            logger.info(f"[ToolLoader] 工具定义已导出到: {file_path}")
            return True
        
        except Exception as e:
            logger.error(f"[ToolLoader] 导出失败: {e}")
            return False
    
    def _generate_markdown(self) -> str:
        """生成 Markdown 格式的工具定义"""
        lines = ["# Tool Definitions", "", f"Total: {len(self.definitions)} tools", ""]
        
        for name, tool in self.definitions.items():
            lines.append(f"## {name}")
            lines.append(f"**Description**: {tool.description}")
            lines.append(f"**Type**: {tool.type}")
            
            if tool.parameters:
                lines.append("**Parameters**:")
                for param in tool.parameters:
                    req = "required" if param["required"] else "optional"
                    default = f", default={param['default']}" if param["default"] is not None else ""
                    lines.append(f"- {param['name']} ({param['type']}): {param['description']} [{req}{default}]")
            
            if tool.example:
                lines.append("**Example**:")
                lines.append("```json")
                lines.append(tool.example)
                lines.append("```")
            
            if tool.returns:
                lines.append(f"**Returns**: {tool.returns}")
            
            lines.append("")
        
        return "\n".join(lines)


# 全局实例
_tool_loader: Optional[ToolDefinitionLoader] = None


def get_tool_loader() -> ToolDefinitionLoader:
    """获取全局工具定义加载器实例"""
    global _tool_loader
    if _tool_loader is None:
        _tool_loader = ToolDefinitionLoader()
    return _tool_loader


# 示例 Markdown 格式
"""
## read_file
**Description**: Read file contents from the filesystem
**Type**: action
**Parameters**:
- file_path (string): Path to the file to read [required]
- start_line (integer): Starting line number [optional, default=0]
- end_line (integer): Ending line number [optional]
**Example**:
```json
{"tool": "read_file", "arguments": {"file_path": "/path/to/file.txt"}}
```
**Returns**: File content as string
"""

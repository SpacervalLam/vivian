"""
记忆类型系统

四种记忆类型：
1. user: 用户个人信息（角色、偏好、知识水平）
2. feedback: 用户反馈（纠正、指导、确认）
3. project: 项目/任务背景（目标、截止日期、决策）
4. reference: 外部参考（链接、资源、文档）

记忆排除规则：
- 代码模式、架构、文件结构（可从项目读取）
- Git 历史（可查询）
- 临时任务详情（只在当前对话有用）
- 已文档化的内容
"""

from typing import List, Literal, Optional, TypedDict, Any

MemoryTypeName = Literal["user", "feedback", "project", "reference"]

MEMORY_TYPES: List[MemoryTypeName] = ["user", "feedback", "project", "reference"]


class MemoryTypeInfo(TypedDict):
    """记忆类型信息"""
    name: str
    description: str
    when_to_save: str
    how_to_use: str


MEMORY_TYPE_INFO: dict[MemoryTypeName, MemoryTypeInfo] = {
    "user": {
        "name": "user",
        "description": "用户的角色、目标、责任和知识水平等个人信息。帮助个性化回应。",
        "when_to_save": "当了解到用户的角色、偏好、责任或知识水平时",
        "how_to_use": "根据用户的个人资料调整回答方式和内容深度"
    },
    "feedback": {
        "name": "feedback",
        "description": "用户给出的指导，包括应该避免什么和应该坚持什么。记录成功和失败案例。",
        "when_to_save": "当用户纠正或确认某种方法有效时，包括原因",
        "how_to_use": "根据反馈调整行为，避免重复相同的错误"
    },
    "project": {
        "name": "project",
        "description": "关于正在进行的工作、目标、计划或事件的信息，无法从代码直接推导。",
        "when_to_save": "当了解到谁在做什么、为什么、截止日期时",
        "how_to_use": "更好地理解用户请求的背景和动机"
    },
    "reference": {
        "name": "reference",
        "description": "外部系统中信息位置的指针，如链接、文档、仪表板等。",
        "when_to_save": "当了解到外部资源及其用途时",
        "how_to_use": "当用户引用外部系统或可能在外部系统中的信息时"
    }
}


def parse_memory_type(raw: Any) -> Optional[MemoryTypeName]:
    """
    解析记忆类型字符串
    
    Args:
        raw: 原始值
        
    Returns:
        有效的记忆类型或 None
    """
    if isinstance(raw, str):
        lower_raw = raw.lower()
        if lower_raw in MEMORY_TYPES:
            return lower_raw
    return None


def validate_memory_content(content: str, memory_type: MemoryTypeName) -> bool:
    """
    验证记忆内容是否适合该类型
    
    Args:
        content: 记忆内容
        memory_type: 记忆类型
        
    Returns:
        是否适合该类型
    """
    content_lower = content.lower()
    
    # 通用排除检查
    excluded_patterns = [
        "def ", "function ", "class ",  # 代码定义
        "git commit", "git log",        # Git 操作
        "file:", "path:",               # 文件路径
        "debug", "bug fix",             # 调试内容
    ]
    
    for pattern in excluded_patterns:
        if pattern in content_lower:
            return False
    
    # 类型特定检查
    if memory_type == "user":
        return any(keyword in content_lower for keyword in ["我是", "我叫", "我喜欢", "我的工作", "我擅长"])
    elif memory_type == "feedback":
        return any(keyword in content_lower for keyword in ["不要", "应该", "好的", "很棒", "这样做", "停止"])
    elif memory_type == "project":
        return any(keyword in content_lower for keyword in ["目标", "计划", "截止", "任务", "项目"])
    elif memory_type == "reference":
        return any(keyword in content_lower for keyword in ["链接", "网址", "文档", "参考", "dashboard"])
    
    return True


def get_memory_type_guidelines() -> str:
    """获取记忆类型使用指南"""
    guidelines = ["## 记忆类型指南"]
    
    for mem_type in MEMORY_TYPES:
        info = MEMORY_TYPE_INFO[mem_type]
        guidelines.extend([
            f"\n### {mem_type}",
            f"- 描述: {info['description']}",
            f"- 保存时机: {info['when_to_save']}",
            f"- 使用方式: {info['how_to_use']}"
        ])
    
    return "\n".join(guidelines)
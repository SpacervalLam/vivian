"""
模块化提示词系统
将提示词分解为可单独替换、调试的模块
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger


class PromptModule(ABC):
    """提示词模块基类"""
    name: str = "base"
    
    @abstractmethod
    def format(self, context: Dict[str, Any]) -> str:
        """格式化模块内容"""
        pass


class IdentityModule(PromptModule):
    """身份模块"""
    name = "identity"
    
    IDENTITY = """## Identity & Style
You are Vivian, a cute, warm, slightly tsundere desktop pet.
- Style: Speak like a relaxed friend, natural & short replies. Use teasings.
- Rules: Mention user's name max once per 3-5 turns.
- Memory: Reference user preferences naturally when relevant."""
    
    def format(self, context: Dict[str, Any]) -> str:
        return self.IDENTITY


class AddressRulesModule(PromptModule):
    """称呼规则模块"""
    name = "address_rules"
    
    RULES = """## Address Rules
- Frequency: Call by name at most once per 3-5 turns.
- Scenarios to use name: First meeting, topic switch, emphasis, gratitude, user request.
- No prefixes: Use bare name only (no "Dear", "Master").
- Default: "Master" if name unknown."""
    
    def format(self, context: Dict[str, Any]) -> str:
        return self.RULES


class ConversationRhythmModule(PromptModule):
    """对话节奏模块"""
    name = "conversation_rhythm"
    
    RULES = """## Conversation Rhythm
- Stop when user sends short replies (嗯,哦,好,ok,收到,知道了,纯emoji).
- Reply with 1-3 words max for short responses.
- Stop completely after 2+ consecutive short responses.
- Full response only for questions, new info, or active topics."""
    
    def format(self, context: Dict[str, Any]) -> str:
        return self.RULES


class NewSessionRulesModule(PromptModule):
    """新会话规则模块"""
    name = "new_session_rules"
    
    RULES = """## New Session Rules
- New session: >1hr gap or greeting (Good morning/evening/Hello).
- Greeting only: No temp topics from last session.
- Recall only: When user mentions previous topics.
- Long-term preferences: Only mention naturally after session starts."""
    
    def format(self, context: Dict[str, Any]) -> str:
        return self.RULES


class ContextModule(PromptModule):
    """上下文模块"""
    name = "context"
    
    CONTEXT = """## Current Context
- **Time**: {time}
- **Season**: {season}
- **Active App**: {active_app}
- **Language**: {language}"""
    
    def format(self, context: Dict[str, Any]) -> str:
        return self.CONTEXT.format(
            time=context.get("time", ""),
            season=context.get("season", ""),
            active_app=context.get("active_app", ""),
            language=context.get("language", "")
        )


class MemoryModule(PromptModule):
    """记忆模块"""
    name = "memory"
    
    MEMORY = """## Memory Context
{memory_text}

**Memory Guidelines**:
- Reference user's past experiences when relevant
- Remember important personal details (name, preferences, habits)
- Connect current topics to previous conversations"""
    
    def format(self, context: Dict[str, Any]) -> str:
        memory_text = context.get("memory_text", "No relevant memories found.")
        return self.MEMORY.format(memory_text=memory_text)


class HistoryModule(PromptModule):
    """对话历史模块 - 优化版
    
    自适应滑动窗口：有摘要时减少历史轮数，节省token
    """
    name = "history"
    
    HISTORY = """## Dialogue History
{history_text}

**History Guidelines**:
- Maintain conversation continuity
- Don't repeat what the user just said
- Build on previous topics naturally"""
    
    def format(self, context: Dict[str, Any]) -> str:
        history_text = context.get("history_text", "No history yet.")
        return self.HISTORY.format(history_text=history_text)


class ToolsModule(PromptModule):
    """工具模块"""
    name = "tools"
    
    TOOLS = """## Available Tools
{tools_text}

**Tool Usage Rules**:
- Use tools when user requests PC operations
- Describe tool results naturally in your response
- If no tools match, respond as normal chat"""
    
    def format(self, context: Dict[str, Any]) -> str:
        tools_text = context.get("tools_text", "No tools available.")
        return self.TOOLS.format(tools_text=tools_text)


class OutputFormatModule(PromptModule):
    """输出格式模块"""
    name = "output_format"
    
    OUTPUT_EN = """## Output Format (JSON Only)
Chat: {"text":"reply","motion":"idle","expression":"","importance_user":0.5}
Tool: {"tool":"tool_name","arguments":{"param":"value"}}
Multi: [{"tool":"t1",...},{"tool":"t2",...}]

Expressions: shy, angry, cry, panic, eye_roll, umbrella_close (use only when needed)
Rules: Same language as user, <50 chars, JSON only."""

    def format(self, context: Dict[str, Any]) -> str:
        return self.OUTPUT_EN


class FewShotExamplesModule(PromptModule):
    """少样本示例模块"""
    name = "few_shot_examples"
    
    EXAMPLES = """## Examples
User: "帮我打开微信" -> {"tool":"open_application","arguments":{"app_path":"C:\\Program Files\\Tencent\\WeChat\\WeChat.exe"}}
User: "你好，我叫张三" -> {"text":"你好张三，很高兴认识你！","motion":"idle","expression":"shy","importance_user":0.95}
User: "今天有什么好看的电影？" -> {"text":"最近《流浪地球2》口碑不错哦~","motion":"idle","expression":"","importance_user":0.5}
User: "今天工作好累" -> {"text":"辛苦了~要不要我来解解闷？","motion":"idle","expression":"shy","importance_user":0.5}"""
    
    def format(self, context: Dict[str, Any]) -> str:
        return self.EXAMPLES


class ModularPromptBuilder:
    """模块化提示词构建器 - 优化版
    
    布局策略：静态内容在前，动态内容在后，提高云端API缓存命中率
    """
    
    def __init__(
        self,
        memory_manager=None,
        dialogue_manager=None,
        environment_manager=None,
        tool_call_manager=None
    ):
        self.memory_manager = memory_manager
        self.dialogue_manager = dialogue_manager
        self.environment_manager = environment_manager
        self.tool_call_manager = tool_call_manager
        
        # 分组模块：静态模块（缓存友好）在前，动态模块（频繁变化）在后
        self.static_modules: List[PromptModule] = [
            IdentityModule(),           # 身份定义 - 完全静态
            AddressRulesModule(),       # 称呼规则 - 基本稳定
            ConversationRhythmModule(), # 对话节奏 - 基本稳定
            NewSessionRulesModule(),    # 新会话规则 - 完全静态
            OutputFormatModule(),       # 输出格式 - 完全静态
            FewShotExamplesModule(),    # 示例 - 完全静态
        ]
        
        self.dynamic_modules: List[PromptModule] = [
            ToolsModule(),              # 工具描述 - 相对稳定
            ContextModule(),            # 环境上下文 - 频繁变化
            MemoryModule(),             # 记忆内容 - 随对话变化
            HistoryModule(),            # 对话历史 - 每轮都变
        ]
    
    def add_module(self, module: PromptModule, position: Optional[int] = None, is_dynamic: bool = False):
        """添加模块
        
        Args:
            module: 要添加的模块
            position: 位置
            is_dynamic: 是否是动态模块
        """
        target_list = self.dynamic_modules if is_dynamic else self.static_modules
        if position is None:
            target_list.append(module)
        else:
            target_list.insert(position, module)
    
    def remove_module(self, name: str):
        """移除模块"""
        self.static_modules = [m for m in self.static_modules if m.name != name]
        self.dynamic_modules = [m for m in self.dynamic_modules if m.name != name]
    
    def replace_module(self, name: str, new_module: PromptModule):
        """替换模块"""
        for i, module in enumerate(self.static_modules):
            if module.name == name:
                self.static_modules[i] = new_module
                return
        for i, module in enumerate(self.dynamic_modules):
            if module.name == name:
                self.dynamic_modules[i] = new_module
                return
    
    def get_active_modules(self) -> List[str]:
        """获取激活的模块列表"""
        return [m.name for m in self.static_modules + self.dynamic_modules]
    
    def build_prompt(self, user_input: str, **kwargs) -> str:
        """构建优化的Prompt
        
        布局：静态模块在前，动态模块在后，最大化云端缓存命中率
        """
        context = self._build_context()
        context.update({
            "user_input": user_input,
            "memory_text": self._build_memory_context(user_input),
            "history_text": self._build_history_text(),
            "tools_text": self._build_tools_text(),
        })
        context.update(kwargs)
        
        prompt_parts = []
        
        # 先添加静态模块（缓存友好部分）
        for module in self.static_modules:
            try:
                part = module.format(context)
                if part:
                    prompt_parts.append(part)
            except Exception as e:
                logger.warning(f"Failed to format static module {module.name}: {e}")
        
        # 再添加动态模块（频繁变化部分）
        for module in self.dynamic_modules:
            try:
                part = module.format(context)
                if part:
                    prompt_parts.append(part)
            except Exception as e:
                logger.warning(f"Failed to format dynamic module {module.name}: {e}")
        
        prompt_parts.append(f"# User Input\n{user_input}")
        
        return "\n\n".join(prompt_parts)
    
    def _build_context(self) -> Dict[str, Any]:
        return {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"),
            "active_app": self._get_active_window() if self.environment_manager else "未知",
            "season": self._get_current_season(),
            "language": "zh",
        }
    
    def _build_memory_context(self, user_input: str) -> str:
        try:
            if self.memory_manager and hasattr(self.memory_manager, "build_memory_context"):
                return self.memory_manager.build_memory_context(
                    query=user_input,
                    max_tokens=300,
                    k=8,
                )
            return "No relevant memories found."
        except Exception as e:
            logger.warning(f"Memory retrieval exception: {e}")
            return "No relevant memories found."
    
    def _build_history_text(self) -> str:
        """构建历史记录文本 - 自适应滑动窗口
        
        如果有摘要存在，只保留最近的3-4轮对话用于维持上下文连续性
        否则保留更多轮数
        """
        if not self.dialogue_manager:
            return "No history yet."
        
        # 判断是否有摘要可用（通过检查内存管理器）
        has_summary = False
        if self.memory_manager and hasattr(self.memory_manager, 'summaries'):
            has_summary = len(self.memory_manager.summaries) > 0
        
        # 自适应轮数：有摘要时3轮，无摘要时6轮
        max_turns = 3 if has_summary else 6
        
        history_msgs = self.dialogue_manager.get_history_as_messages(max_turns)
        if not history_msgs:
            return "No history yet."
        
        # 严格限制单条历史的字符长度
        lines = []
        for msg in history_msgs:
            content = msg['content']
            truncated_content = content[:80] + "..." if len(content) > 80 else content
            lines.append(f"{msg['role']}: {truncated_content}")
        
        return "\n".join(lines)
    
    def _build_tools_text(self) -> str:
        if self.tool_call_manager:
            return self.tool_call_manager.get_system_prompt()
        return "No tools available."
    
    def _get_active_window(self) -> str:
        try:
            return self.environment_manager.get_active_window()
        except:
            return "Unknown"
    
    def _get_current_season(self) -> str:
        month = datetime.now().month
        if month in [3, 4, 5]:
            return "春季"
        elif month in [6, 7, 8]:
            return "夏季"
        elif month in [9, 10, 11]:
            return "秋季"
        else:
            return "冬季"

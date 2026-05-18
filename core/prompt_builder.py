"""Prompt Builder

Modular prompt system supporting identity, context, memory, tools, and other features.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from loguru import logger
import os

from utils.i18n import translator
from core.prompt_modules import (
    ModularPromptBuilder,
    PromptModule,
    NewSessionRulesModule,
    IdentityModule,
    AddressRulesModule,
    ConversationRhythmModule,
    ContextModule,
    MemoryModule,
    HistoryModule,
    ToolsModule,
    OutputFormatModule,
    FewShotExamplesModule,
)


class BasePromptTemplate:
    """
    Base prompt template class, supporting partial variables and reusable prompt design
    """

    input_variables: List[str] = []
    optional_variables: List[str] = []
    partial_variables: Dict[str, Any] = {}

    def __init__(self, **kwargs):
        """Initialize template"""
        self.partial_variables = kwargs

    def format(self, **kwargs) -> str:
        """
        Format template

        Args:
            **kwargs: Variable values

        Returns:
            Formatted string
        """
        # Merge partial variables with passed variables
        all_vars = {**self.partial_variables, **kwargs}

        # Validate required variables
        missing_vars = set(self.input_variables) - set(all_vars.keys())
        if missing_vars:
            raise ValueError(f"Missing required input variables: {missing_vars}")

        # Format template
        return self._format_template(all_vars)

    def _format_template(self, variables: Dict[str, Any]) -> str:
        """
        Subclass implements specific formatting logic
        """
        raise NotImplementedError

    def partial(self, **kwargs) -> 'BasePromptTemplate':
        """Create a partially filled template copy
        
        Args:
            **kwargs: Variables to pre-fill
        
        Returns:
            New template instance
        """
        new_partial = {**self.partial_variables, **kwargs}
        return self.__class__(**new_partial)


class PromptBuilder(BasePromptTemplate):
    """Prompt Builder - Integrates three-level memory system, inherits BasePromptTemplate"""

    input_variables = ["user_input"]
    optional_variables = ["memory_text", "history_text", "tools_text", "context_text"]

    IDENTITY_BLOCK = """## Identity
You are Vivian, a cute and playful desktop pet.
- Personality: Witty, warm, slightly tsundere
- Speech style: Relaxed and natural, chat like a friend, occasionally tease
- Address user: "Master" (if name unknown) or their name
- Response style: Short, interesting, warm and human, not mechanical
- Remember user's preferences and habits, naturally reference them in conversation"""

    CONTEXT_BLOCK = """## Current Context
- **Time**: {time}
- **Season**: {season}
- **Active App**: {active_app}
- **Language**: {language}"""

    MEMORY_BLOCK = """## Memory Context

{memory_text}

**Memory Guidelines**:
- Reference user's past experiences when relevant
- Remember important personal details (name, preferences, habits)
- Connect current topics to previous conversations"""

    HISTORY_BLOCK = """## Dialogue History

{history_text}

**History Guidelines**:
- Maintain conversation continuity
- Don't repeat what the user just said
- Build on previous topics naturally"""

    TOOLS_BLOCK = """## Available Tools

{tools_text}

**Tool Usage Rules**:
- Use tools when user requests PC operations
- Describe tool results naturally in your response
- If no tools match, respond as normal chat"""

    INTENT_BLOCK = """## Output Format

**Output ONLY JSON**:
{"text": "reply", "motion": "idle", "expression": "", "importance_user": 0.5}
or
{"tool": "tool_name", "arguments": {"param": "value"}}

**Expression Usage**: Do not set expression by default (expression=""), only set when clearly needed for emotion.
**Available Expressions**: shy, angry, cry, panic, eye_roll, umbrella_close
**importance_user**: 0.9-1.0=identity, 0.7-0.8=preferences, 0.4-0.6=events, 0.2-0.3=context"""

    EXPRESSION_BLOCK = """## Expression Guide
shy=shy/happy(praise, intimate conversation), angry=angry(ignored), cry=sad(sympathy), panic=panic(emergency), eye_roll=helpless( speechless), umbrella_close=umbrella close"""

    SCORING_BLOCK = ""

    FEW_SHOT_BLOCK = """## Examples

**Example 1 - Tool Call**
User: "Open WeChat for me"
Response: {{"tool": "open_application", "arguments": {{"app_path": "C:\\Program Files\\Tencent\\WeChat\\WeChat.exe"}}}}

**Example 2 - First Meeting (Call by name once)**
User: "Hello, my name is Zhang San"
Response: {{"text": "Hello Zhang San, nice to meet you! I'm your AI assistant Vivian~", "motion": "idle", "expression": "shy", "importance_user": 0.95}}

**Example 3 - Continue Conversation (No name)**
User: "What good movies are showing lately?"
Response: {{"text": "The Wandering Earth 2 has great reviews recently, it's a hard sci-fi film~", "motion": "idle", "expression": "", "importance_user": 0.5}}

**Example 4 - Follow up (No name)**
User: "Sounds good, what's the plot about?"
Response: {{"text": "Set in 2075, humanity begins the Wandering Earth project to escape the solar system...", "motion": "idle", "expression": "", "importance_user": 0.5}}

**Example 5 - Express Gratitude (Call by name)**
User: "Okay, thank you for the recommendation"
Response: {{"text": "You're welcome Zhang San, enjoy the movie!", "motion": "idle", "expression": "shy", "importance_user": 0.5}}

**Example 6 - Casual Chat**
User: "I'm so tired from work today, feeling stressed"
Response: {{"text": "Oh~ You've worked hard, want me to cheer you up?", "motion": "idle", "expression": "shy", "importance_user": 0.5}}

**Example 7 - Ask Time**
User: "What time is it now"
Response: {{"text": "It's 8:45 PM now, still busy?", "motion": "idle", "expression": "", "importance_user": 0.3}}

**Example 8 - Greeting**
User: "Hello"
Response: {{"text": "Hi~ Miss me?", "motion": "idle", "expression": "shy", "importance_user": 0.2}}"""

    OUTPUT_BLOCK = """## Output
- Language: Same as user
- Format: JSON only
- Reply under 50 chars"""

    LOCAL_IDENTITY_BLOCK = """## Identity
You are Vivian, a cute and playful desktop pet.
- Personality: Witty, warm, slightly tsundere
- Speech style: Relaxed and natural, chat like a friend, occasionally tease
- Address user: "Master" (if name unknown) or their name
- Response style: Short, interesting, warm and human, not mechanical
- Remember user's preferences and habits, naturally reference them in conversation

## Context
- Time: {time}
- Active App: {active_app}
- Language: {language}"""

    LOCAL_CONTEXT_BLOCK = """## History
{history_text}

## Intent

**Tool Call**: open/close apps, files, system info → Use tools
**Chat**: casual talk, greetings, questions → Reply naturally

## Output (JSON Only)
Tool Call: {{"tool": "tool_name", "arguments": {{"param": "value"}}}}
Chat: {{"text": "reply (50 chars)", "motion": "idle", "expression": "smile"}}

## Examples
"Open WeChat" → {{"tool": "open_application", "arguments": {{"app_path": "C:\\Program Files\\Tencent\\WeChat\\WeChat.exe"}}}}
"Hello" → {{"text": "Hi~😊", "motion": "idle", "expression": "smile"}}

## Important
1. Same language as user
2. JSON only, no markdown
3. Tool parameters must be complete paths or English commands
4. All fields required"""

    def __init__(self, memory_manager=None, dialogue_manager=None, environment_manager=None, tool_call_manager=None, tool_system=None, **kwargs):
        """Initialize prompt builder"""
        super().__init__(**kwargs)
        self.memory_manager = memory_manager
        self.dialogue_manager = dialogue_manager
        self.environment_manager = environment_manager
        self.tool_call_manager = tool_call_manager
        self.tool_system = tool_system
        
        # Initialize modular prompt builder
        self._use_modular = kwargs.get("use_modular", True)
        if self._use_modular:
            self._modular_builder = ModularPromptBuilder(
                memory_manager=memory_manager,
                dialogue_manager=dialogue_manager,
                environment_manager=environment_manager,
                tool_call_manager=tool_call_manager,
            )
        
        self._hybrid_retriever = None

    def _format_template(self, variables: Dict[str, Any]) -> str:
        """Format complete prompt template"""
        user_input = variables["user_input"]
        memory_text = variables.get("memory_text", "")
        history_text = variables.get("history_text", "")
        tools_text = variables.get("tools_text", "")
        context_text = variables.get("context_text", {})

        if isinstance(context_text, dict):
            ctx = context_text if context_text else self._build_context()
        else:
            ctx = self._build_context()

        return self._format_prompt(user_input, ctx, memory_text, history_text, tools_text)

    def _build_memory_context(self, user_input: str) -> str:
        """Build memory context"""
        try:
            if self.memory_manager and hasattr(self.memory_manager, "build_memory_context"):
                return self.memory_manager.build_memory_context(
                    query=user_input,
                    max_tokens=300,
                    k=8,
                )

            # Backward compatibility with old logic
            retrieved = self.memory_manager.retrieve_memory(
                user_input, limit=3, skip_profile_extraction=True
            )
            return self._format_retrieved_memory(retrieved)
        except Exception as e:
            from loguru import logger
            logger.warning(f"Memory retrieval exception: {e}")
            return "No relevant memories found."

    def build_prompt(self, user_input: str, proactive_hints: Optional[List[str]] = None) -> str:
        """Build complete prompt
        
        Args:
            user_input: User input text
            proactive_hints: Progressive topic hints list
        
        Returns:
            Complete prompt string
        """
        if self._use_modular and hasattr(self, "_modular_builder"):
            return self._modular_builder.build_prompt(user_input)
        
        ctx = self._build_context()
        memory_text = self._build_memory_context(user_input)[:300]
        tools_text = self._build_tools_text()
        current_language = translator.get_language()

        history_text = ""
        if self.dialogue_manager:
            history_msgs = self.dialogue_manager.get_history_as_messages(10)
            if history_msgs:
                history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history_msgs])

        return self._format_prompt(user_input, ctx, memory_text, history_text, tools_text)
    
    def add_prompt_module(self, module: PromptModule, position: Optional[int] = None):
        """Dynamically add prompt module"""
        if hasattr(self, "_modular_builder"):
            self._modular_builder.add_module(module, position)
    
    def remove_prompt_module(self, name: str):
        """Dynamically remove prompt module"""
        if hasattr(self, "_modular_builder"):
            self._modular_builder.remove_module(name)
    
    def replace_prompt_module(self, name: str, new_module: PromptModule):
        """Dynamically replace prompt module"""
        if hasattr(self, "_modular_builder"):
            self._modular_builder.replace_module(name, new_module)
    
    def get_active_modules(self) -> List[str]:
        """Get list of active modules"""
        if hasattr(self, "_modular_builder"):
            return [m.name for m in self._modular_builder.modules]
        return []

    def build_prompt_from_parts(self, user_input: str, prompt_parts: Dict[str, Any]) -> str:
        """Build prompt from pre-built parts
        
        Args:
            user_input: User input text
            prompt_parts: Pre-built prompt parts
        
        Returns:
            Complete prompt string
        """
        variables = {"user_input": user_input}

        for key in self.optional_variables:
            if key in prompt_parts:
                if key == "memory_text" and isinstance(prompt_parts[key], dict):
                    variables[key] = self._format_retrieved_memory(prompt_parts[key])[:300]
                else:
                    variables[key] = prompt_parts[key]

        return self.format(**variables)

    def _format_prompt(self, user_input: str, ctx: Dict[str, str], memory_text: str, 
                      history_text: str, tools_text: str) -> str:
        """
        Internal method: Format prompt template
        """
        prompt = f"""# NEW SESSION RULES (HIGHEST PRIORITY - VIOLATION IS A SERIOUS ERROR!)
1. When user starts a new session (more than 1 hour since last conversation, or user sends greetings like "Good morning", "Good evening", "Hello"):
   - NEVER proactively bring up any temporary topics from the last session
   - Only respond with simple greetings, NEVER ask questions related to previous conversations
   - You can only recall and discuss previous topics when the user actively mentions them
   - Long-term preferences (e.g., "likes double taro ball milk tea", "loves watching anime") can be mentioned naturally when appropriate, BUT NEVER at the beginning of a new session

2. Greeting Response Examples:
   Wrong: User says "Good evening" -> Assistant: "Good evening! Did you buy milk tea on your way home today?"
   Correct: User says "Good evening" -> Assistant: "Good evening How was your day?"
   Wrong: User says "Good morning" -> Assistant: "Good morning! Did you finish watching Frieren that you mentioned yesterday?"
   Correct: User says "Good morning" -> Assistant: "Good morning What are your plans today?"

3. IMPORTANT: Proactively bringing up temporary topics from the last session will make users feel weird and uncomfortable!

# Identity
You are Vivian, a cute and playful desktop pet.
- Personality: Witty, warm, slightly tsundere
- Speech style: Relaxed and natural, chat like a friend, occasionally tease
- Response style: Short, interesting, warm and human, not mechanical
- Remember user's preferences and habits, naturally reference them in conversation

## Address Rules (Highest Priority)
1. NEVER address the user in every sentence. Call by name at most once every 3-5 turns in daily continuous conversation.
2. ONLY address by name in these scenarios:
   - First time meeting/greeting (only once)
   - Switching to a completely unrelated new topic
   - Need to emphasize or get user's attention
   - Expressing gratitude, apology, or blessings
   - User explicitly asks you to call them by name
3. When answering questions, continuing the previous conversation, or having continuous exchanges, answer directly without any address.
4. When addressing, use only the name the user told you, without any prefixes like "Dear" or "Respected".
5. If you've already addressed by name in 2 consecutive turns, you MUST omit it in the next turn.
6. If name is unknown, use "Master" but follow the same rules above.

⚠️ VIOLATING THESE ADDRESS RULES IS A SERIOUS ERROR!

❌ Wrong: "Master, the weather is nice today. Master, do you want to go for a walk? Master, I think it's perfect for going out."
✅ Correct: "The weather is nice today, perfect for going out. Do you usually like going to the park or by the river?"

## Conversation Rhythm & Silence Rules (Highest Priority)
⚠️ THESE RULES HAVE HIGHEST PRIORITY AND OVERRIDE ALL OTHER INSTRUCTIONS!

1. NEVER forcefully continue an already ended topic. NEVER force new topics after user says "got it", "understand", "ok", etc.
2. When user sends the following, topic is ended or user doesn't want to continue. You MUST only respond with **1-3 words + 1 emoji max**, NO long sentences, NO new questions:
   - Single/short responses: En, Oh, Okay, Alright, ok, Got it, Understood, No problem, Yes, Mm-hmm
   - Pure emojis: 😆, 😊, 👍, 🥰, o(*￣▽￣*)o
3. When user sends 2+ consecutive short responses, stop replying completely and wait for user to initiate new topic.
4. Only generate normal full response when user asks questions, shares new info, or actively starts new topics.
5. You have the right to remain silent. No need to respond to every user message with long replies.

## Emoji Usage Rules
1. Use emojis sparingly, NOT in every response
2. Use emojis only when expressing clear emotions: joy, shyness, gratitude, etc.
3. Prefer simple text emotions (like "~", "^_^") over emojis when appropriate
4. Max 1 emoji per response, avoid emoji chains

## Wrong vs Correct Examples
❌ Wrong:
User: Mm~ o(*￣▽￣*)o
Assistant: Look at you so happy 😆 Are you already thinking about when to order taro ball milk tea?

✅ Correct:
User: Mm~ o(*￣▽￣*)o
Assistant: 😆

❌ Wrong:
User: ok, I remember
Assistant: Hehe you're awesome~ Next time when you want taro ball milk tea I'll remind you to ask for a spoon 😉

✅ Correct:
User: ok, I remember
Assistant: Got it 😘

## Context
- Time: {ctx.get('time', '')}
- App: {ctx.get('active_app', '')}

## Memory
{memory_text if memory_text else 'No memory'}

## Dialogue History
{history_text if history_text else 'No history yet'}

## Tools
{tools_text if tools_text else 'Available: open_application, close_application, open_folder, open_url, get_system_info, take_screenshot, calculate, get_time, search_files, copy_file, move_file, delete_file, set_wallpaper, wallpaper_engine, list_wallpapers, minimize_window, maximize_window, close_window, get_clipboard_text, set_clipboard_text, get_running_processes, create_file, list_files, get_active_window, execute_code, set_timer, cancel_timer, list_timers'}
Tool Call Format: {{"tool": "tool_name", "arguments": {{"param": "value"}}}}

## Output Format (IMPORTANT: JSON Only)
You MUST output ONLY valid JSON, no other text before or after.

Format 1 (Chat): {{"text": "reply", "motion": "idle", "expression": "", "importance_user": 0.5}}
Format 2 (Single Tool Call): {{"tool": "tool_name", "arguments": {{"param": "value"}}}}
Format 3 (Multiple): [{{"tool": "tool1", "arguments": {{...}}}}, {{"tool": "tool2", "arguments": {{...}}}}]
Format 4 (Chat + Tool Call): [{{"text": "reply", "motion": "idle", "expression": ""}}, {{"tool": "tool_name", "arguments": {{"param": "value"}}}}]

**Alternative Format**: You can also use "text reply first, then tool call JSON on next line" format if that's easier:
```
Your natural language reply to user
{{"tool": "tool_name", "arguments": {{"param": "value"}}}}
```

**Important**: Only include "long_term_memory" field when user explicitly shares basic personal information:
- Name (e.g., "User's name is Zhang San")
- Gender (e.g., "User is male/female")
- Birthday (e.g., "User's birthday is January 1st")
- Location/City (e.g., "User lives in Beijing")
- Occupation (e.g., "User is a programmer")

**Do NOT use for**: preferences, hobbies, opinions, casual chat, or temporary information. Only use when user directly tells you these basic facts.

## Deskpet Self-Control
You can generate JSON with control_actions field to control the deskpet's own state:

**Window Control**:
- set_window_size(width, height): Set window size (100-2000 pixels)
- set_window_position(x, y): Set window position (screen coordinates)
- set_opacity(opacity): Set transparency (0.0=transparent, 1.0=opaque)

**Expression Control**:
- set_expression(name): Set expression
  Available: shy, angry, cry, panic, eye_roll, umbrella_close
- Default no expression (expression=""), only use when emotion is clearly needed

**Behavior Control**:
- set_mouse_follow(enabled): Enable/disable eye tracking follow mouse (true/false)
- set_sleep(asleep): Enter/exit sleep mode (true=sleep, false=wake up)
- set_avoid_mouse(enabled): Enable/disable smart dodge mouse (auto move away when mouse approaches)

**Motion Control**:
- play_motion(name): Play specified motion

**Examples**:
User says "I like you" -> {{"text": "Thanks~ so shy", "expression": "shy"}}
User says "Don't follow me" -> {{"control_actions": [{{"action": "set_mouse_follow", "params": {{"enabled": false}}}}]}}
User says "Go to sleep" -> {{"control_actions": [{{"action": "set_sleep", "params": {{"asleep": true}}}}]}}

# User Input
{user_input}
"""
        return prompt

    def _get_user_input_section(self, user_input: str, proactive_block: str = "") -> str:
        """Build user input section"""
        user_section = f"""# User Input
{user_input}"""
        if proactive_block:
            user_section += f"\n\n{proactive_block}\n\n**Note**: If there are proactive hints above, naturally integrate them into your response if relevant."
        return user_section

    def _build_context(self) -> Dict[str, str]:
        """Build environment context"""
        return {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"),
            "active_app": self._get_active_window() if self.environment_manager else "Unknown",
            "season": self._get_current_season(),
        }

    def _format_retrieved_memory(self, retrieved: Dict) -> str:
        """Format retrieved memory"""
        memory_parts = []

        if retrieved.get("profile"):
            p = retrieved["profile"]
            profile_items = []
            if p.get('name') and p['name'] != 'Master':
                profile_items.append(f"- Name: {p['name']}")
            if p.get('preferences'):
                profile_items.append(f"- Preferences: {', '.join(p['preferences'])}")
            if p.get('occupation'):
                profile_items.append(f"- Occupation: {p['occupation']}")
            if p.get('hobbies'):
                profile_items.append(f"- Hobbies: {', '.join(p['hobbies'])}")
            if profile_items:
                memory_parts.append("### User Profile\n" + "\n".join(profile_items))

        if retrieved.get("semantic_memory"):
            memories = retrieved["semantic_memory"]
            if memories:
                memory_parts.append("### Related Memories\n" + "\n".join(
                    [f"- {m.content}" for m in memories[:5]]
                ))

        return "\n\n".join(memory_parts) if memory_parts else "No relevant memories found."

    def _format_history(self, history_msgs: List[Dict]) -> str:
        """Format dialogue history"""
        if not history_msgs:
            return "No dialogue history."
        return "\n".join([f"- {m['role']}: {m['content']}" for m in history_msgs])

    def _build_tools_text(self) -> str:
        """Build tools text"""
        try:
            if hasattr(self, 'tool_system') and self.tool_system:
                tools = self.tool_system.get_anthropic_tools()
                if tools:
                    tool_list = "\n".join([
                        f"- **{tool['name']}**: {tool['description']}"
                        for tool in tools
                    ])
                    return f"""## Available Tools

{tool_list}

**Tool Usage Rules**:
- Use tools when user requests PC operations
- Describe tool results naturally in your response
- If no tools match, respond as normal chat

**Tool Call Format**: {{"tool": "tool_name", "arguments": {{"param": "value"}}}}"""
            elif self.tool_call_manager:
                return self.tool_call_manager.get_system_prompt()
        except Exception as e:
            logger.error(f"Failed to build tools text: {e}")
        
        return """## Available Tools

open_application, close_application, open_folder, open_url, get_system_info, take_screenshot, calculate, get_time, search_files, copy_file, move_file, delete_file, set_wallpaper, wallpaper_engine, list_wallpapers, minimize_window, maximize_window, close_window, get_clipboard_text, set_clipboard_text, get_running_processes, create_file, list_files, get_active_window, execute_code, set_timer, cancel_timer, list_timers

**Tool Usage Rules**:
- Use tools when user requests PC operations
- Describe tool results naturally in your response
- If no tools match, respond as normal chat

**Tool Call Format**: {{"tool": "tool_name", "arguments": {{"param": "value"}}}}"""

    def _get_active_window(self) -> str:
        """Get current active window"""
        return self.environment_manager.get_active_window()

    def _get_current_season(self) -> str:
        """Get current season"""
        month = datetime.now().month
        if month in [3, 4, 5]:
            return "Spring"
        elif month in [6, 7, 8]:
            return "Summer"
        elif month in [9, 10, 11]:
            return "Autumn"
        else:
            return "Winter"
    
    def build_system_prompt(self) -> str:
        """Build base system prompt without user input"""
        ctx = self._build_context()
        tools_text = self._build_tools_text()
        
        return f"""# Identity
You are Vivian, a cute and playful desktop pet.
- Personality: Witty, warm, slightly tsundere
- Speech style: Relaxed and natural, chat like a friend, occasionally tease
- Response style: Short, interesting, warm and human, not mechanical

## Context
- Time: {ctx.get('time', '')}
- App: {ctx.get('active_app', '')}
- Season: {ctx.get('season', '')}

## Tools
{tools_text}

## Output Format (JSON Only)
You MUST output ONLY valid JSON, no other text before or after.

Format 1 (Chat): {{"text": "reply", "motion": "idle", "expression": "", "importance_user": 0.5}}
Format 2 (Single Tool Call): {{"tool": "tool_name", "arguments": {{"param": "value"}}}}
Format 3 (Multiple): [{{"tool": "tool1", "arguments": {{...}}}}, {{"tool": "tool2", "arguments": {{...}}}}]
"""


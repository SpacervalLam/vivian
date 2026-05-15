"""Vivian Core Module - 核心功能模块"""

from loguru import logger

from .dialogue_manager import DialogueManager, History

from .memory_manager import MemoryManager

from .prompt_builder import PromptBuilder

from .brain_runnables import (
    Runnable,
    RunnableConfig,
    RunnableSerializable,
    RunnableLambda,
    RunnableSequence,
    RunnableParallel,
    RunnableBinding,
    ensure_config,
    VivianRunnable,
    BrainState,
    TopicDetectionRunnable,
    CommandParsingRunnable,
    PromptBuildingRunnable,
    AIResponseGenerationRunnable,
    ResponseParsingRunnable,
    MemorySavingRunnable,
    BrainChatChain,
)

from .brain import Brain

from .ai_manager import AIManager

__all__ = [
    # 核心组件
    "DialogueManager",
    "History",
    "MemoryManager",
    "PromptBuilder",
    "Brain",
    "AIManager",
    
    # Runnable 架构组件
    "Runnable",
    "RunnableConfig",
    "RunnableSerializable",
    "RunnableLambda",
    "RunnableSequence",
    "RunnableParallel",
    "RunnableBinding",
    "ensure_config",
    "VivianRunnable",
    "BrainState",
    "TopicDetectionRunnable",
    "CommandParsingRunnable",
    "PromptBuildingRunnable",
    "AIResponseGenerationRunnable",
    "ResponseParsingRunnable",
    "MemorySavingRunnable",
    "BrainChatChain",
]

"""
Message types for the messaging system.
"""

from dataclasses import dataclass


@dataclass
class UserInputMessage:
    """Message representing user input."""
    text: str
    timestamp: float = 0.0
    is_voice: bool = False


@dataclass
class LLMDialogMessage:
    """Message representing LLM response."""
    name: str
    text: str
    asset_id: Optional[str] = None
    effect: str = ""
    is_system_message: bool = False


@dataclass
class TTSOutputMessage:
    """Message representing TTS output."""
    audio_path: str
    name: str
    asset_id: str
    text: str
    is_system_message: bool = False
    effect: str = ""
"""
Base classes for message handlers.
"""

from abc import ABC, abstractmethod


class MessageHandler(ABC):
    """Base class for message handlers."""
    
    def init(self):
        """Initialize handler (called once at startup)."""
        pass
    
    @abstractmethod
    def can_handle(self, message) -> bool:
        """Check if this handler can handle the message."""
        pass
    
    def pre_process(self, message):
        """Process message before handling."""
        pass
    
    @abstractmethod
    def handle(self, message):
        """Handle the message."""
        pass
    
    def post_process(self, message):
        """Process after handling."""
        pass


class UIOutputMessageHandler(ABC):
    """Base class for UI output handlers."""
    
    def init(self):
        """Initialize handler."""
        pass
    
    @abstractmethod
    def can_handle(self, message) -> bool:
        """Check if this handler can handle the message."""
        pass
    
    def pre_process(self, message):
        """Process message before handling."""
        pass
    
    @abstractmethod
    def handle(self, message):
        """Handle the message."""
        pass
    
    def post_process(self, message):
        """Process after handling."""
        pass
"""
core/channels/__init__.py — Channel Bridge

Sistema de integração multi-canal.
"""

# Models
from .models import (
    # Enums
    ChannelType,
    MessageType,
    ConnectorStatus,
    ThreadType,
    # Models
    UserIdentity,
    ChannelAttachment,
    ChannelMessage,
    ChannelThread,
    ChannelConnectorConfig,
)

# Base
from .base import (
    BaseConnector,
    ChannelError,
    ConnectionError,
    AuthenticationError,
    RateLimitError,
    MessageError,
)

# Manager
from .manager import ChannelManager

# Connectors
from .connectors.telegram import TelegramConnector
from .connectors.whatsapp import WhatsAppConnector

# API Router
from .api import router

__version__ = "1.0.0"

__all__ = [
    # Version
    "__version__",
    
    # Enums
    "ChannelType",
    "MessageType",
    "ConnectorStatus",
    "ThreadType",
    
    # Models
    "UserIdentity",
    "ChannelAttachment",
    "ChannelMessage",
    "ChannelThread",
    "ChannelConnectorConfig",
    
    # Base
    "BaseConnector",
    "ChannelError",
    "ConnectionError",
    "AuthenticationError",
    "RateLimitError",
    "MessageError",
    
    # Manager
    "ChannelManager",
    
    # Connectors
    "TelegramConnector",
    "WhatsAppConnector",
    
    # API
    "router",
]

"""
core/channels/models.py — Channel Bridge Models

Pydantic models para o sistema de integração multi-canal.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ChannelType(str, enum.Enum):
    """Tipos de canais suportados."""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    WEBCHAT = "webchat"


class MessageType(str, enum.Enum):
    """Tipos de mensagens."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACT = "contact"
    STICKER = "sticker"
    REACTION = "reaction"
    SYSTEM = "system"


class ConnectorStatus(str, enum.Enum):
    """Status de um conector."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class ThreadType(str, enum.Enum):
    """Tipo de thread/conversa."""
    DIRECT = "direct"  # 1:1
    GROUP = "group"     # Grupo
    CHANNEL = "channel"  # Canal (Discord/Slack)
    BROADCAST = "broadcast"  # Broadcast


class UserIdentity(BaseModel):
    """Identidade de um usuário cross-canal."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Identificadores por canal
    channel_ids: Dict[ChannelType, str] = Field(default_factory=dict)
    # Ex: {ChannelType.TELEGRAM: "123456789", ChannelType.DISCORD: "987654321"}
    
    # Dados comuns
    display_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    
    # Metadados
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    
    # Preferências
    preferences: Dict[str, Any] = Field(default_factory=dict)


class ChannelAttachment(BaseModel):
    """Anexo em uma mensagem."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[float] = None  # Para áudio/vídeo
    width: Optional[int] = None  # Para imagens/vídeos
    height: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChannelMessage(BaseModel):
    """Mensagem em um canal."""
    model_config = ConfigDict(frozen=False)
    
    # Identificação
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str
    channel_type: ChannelType
    thread_id: Optional[str] = None
    
    # Conteúdo
    message_type: MessageType = MessageType.TEXT
    content: str
    attachments: List[ChannelAttachment] = Field(default_factory=list)
    
    # Autoria
    author_id: str
    author_type: str = "user"  # user, bot, system
    
    # Contexto
    reply_to_message_id: Optional[str] = None
    mentions: List[str] = Field(default_factory=list)  # IDs de usuários mencionados
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    edited_at: Optional[datetime] = None
    
    # Metadados
    is_edited: bool = False
    is_deleted: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChannelThread(BaseModel):
    """Thread/conversa em um canal."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str
    channel_type: ChannelType
    thread_type: ThreadType = ThreadType.DIRECT
    
    # Participantes
    participant_ids: List[str] = Field(default_factory=list)
    participant_count: int = 0
    
    # Conteúdo
    title: Optional[str] = None
    first_message_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    message_count: int = 0
    
    # Configurações
    is_archived: bool = False
    is_pinned: bool = False
    settings: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChannelConnectorConfig(BaseModel):
    """Configuração de um conector de canal."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel_type: ChannelType
    name: str
    
    # Configurações específicas do canal
    # Telegram: bot_token
    # Discord: bot_token, guild_id
    # WhatsApp: phone_number, api_key
    # Slack: bot_token, signing_secret
    config: Dict[str, Any] = Field(default_factory=dict)
    
    # Status
    is_enabled: bool = True
    status: ConnectorStatus = ConnectorStatus.DISCONNECTED
    last_connected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    error_count: int = 0
    
    # Webhook
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # segundos
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Re-exportar
__all__ = [
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
]

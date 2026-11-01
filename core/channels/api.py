"""
core/channels/api.py — Channels API

Rotas FastAPI para o Channel Bridge.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .manager import ChannelManager
from .models import (
    ChannelConnectorConfig,
    ChannelMessage,
    ChannelThread,
    ChannelType,
    ConnectorStatus,
    MessageType,
    ThreadType,
    UserIdentity,
)


# ============================================================================
# Schemas Pydantic para API
# ============================================================================

class ConnectorCreateRequest(BaseModel):
    """Request para criar conector."""
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., min_length=1, max_length=100)
    channel_type: ChannelType
    config: Dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None


class ConnectorUpdateRequest(BaseModel):
    """Request para atualizar conector."""
    model_config = ConfigDict(extra="forbid")
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Request para enviar mensagem."""
    model_config = ConfigDict(extra="forbid")
    
    thread_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    reply_to_message_id: Optional[str] = None


class BroadcastMessageRequest(BaseModel):
    """Request para broadcast."""
    model_config = ConfigDict(extra="forbid")
    
    destinations: List[Dict[str, str]] = Field(..., min_length=1)
    # [{"connector_id": "...", "thread_id": "..."}]
    content: str = Field(..., min_length=1)


class UserIdentityCreateRequest(BaseModel):
    """Request para criar identidade de usuário."""
    model_config = ConfigDict(extra="forbid")
    
    display_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    channel_ids: Dict[str, str] = Field(default_factory=dict)
    # {"telegram": "123456", "whatsapp": "5511999999999"}


# ============================================================================
# Dependências
# ============================================================================

def get_channel_manager() -> ChannelManager:
    """Retorna instância do ChannelManager."""
    # Implementar injeção de dependência real
    raise NotImplementedError("ChannelManager dependency not configured")


# ============================================================================
# Rotas
# ============================================================================

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/connectors", response_model=List[Dict[str, Any]])
async def list_connectors(
    channel_type: Optional[ChannelType] = None,
    manager: ChannelManager = Depends(get_channel_manager),
) -> List[Dict[str, Any]]:
    """Lista todos os conectores."""
    connectors = manager.list_connectors(channel_type=channel_type)
    
    return [
        {
            "id": c.connector_id,
            "name": c.config.name,
            "channel_type": c.channel_type.value,
            "status": c.status.value,
            "is_connected": c.is_connected,
            "is_enabled": c.config.is_enabled,
            "last_connected_at": c.config.last_connected_at.isoformat() if c.config.last_connected_at else None,
        }
        for c in connectors
    ]


@router.post("/connectors", response_model=Dict[str, Any])
async def create_connector(
    request: ConnectorCreateRequest,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Cria e conecta um novo conector."""
    from .models import ChannelConnectorConfig
    
    config = ChannelConnectorConfig(
        name=request.name,
        channel_type=request.channel_type,
        config=request.config,
        is_enabled=request.is_enabled,
        webhook_url=request.webhook_url,
        webhook_secret=request.webhook_secret,
    )
    
    connector = await manager.add_connector(config)
    
    return {
        "id": connector.connector_id,
        "name": config.name,
        "channel_type": connector.channel_type.value,
        "status": connector.status.value,
        "is_connected": connector.is_connected,
    }


@router.get("/connectors/{connector_id}", response_model=Dict[str, Any])
async def get_connector(
    connector_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Obtém detalhes de um conector."""
    connector = manager.get_connector(connector_id)
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    return {
        "id": connector.connector_id,
        "name": connector.config.name,
        "channel_type": connector.channel_type.value,
        "status": connector.status.value,
        "is_connected": connector.is_connected,
        "is_enabled": connector.config.is_enabled,
        "config": connector.config.config,
        "webhook_url": connector.config.webhook_url,
        "last_connected_at": connector.config.last_connected_at.isoformat() if connector.config.last_connected_at else None,
        "last_error": connector.config.last_error,
        "error_count": connector.config.error_count,
    }


@router.delete("/connectors/{connector_id}")
async def delete_connector(
    connector_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, str]:
    """Remove um conector."""
    success = await manager.remove_connector(connector_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    return {"message": "Connector removed successfully"}


@router.post("/connectors/{connector_id}/connect")
async def connect_connector(
    connector_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Reconecta um conector."""
    connector = manager.get_connector(connector_id)
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    await connector.connect()
    
    return {
        "id": connector_id,
        "status": connector.status.value,
        "is_connected": connector.is_connected,
    }


@router.post("/connectors/{connector_id}/disconnect")
async def disconnect_connector(
    connector_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Desconecta um conector."""
    connector = manager.get_connector(connector_id)
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    await connector.disconnect()
    
    return {
        "id": connector_id,
        "status": connector.status.value,
        "is_connected": connector.is_connected,
    }


# ============================================================================
# Mensagens
# ============================================================================

@router.post("/connectors/{connector_id}/messages", response_model=Dict[str, Any])
async def send_message(
    connector_id: str,
    request: SendMessageRequest,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Envia mensagem através de um conector."""
    message = await manager.send_message(
        connector_id=connector_id,
        thread_id=request.thread_id,
        content=request.content,
        attachments=None,  # TODO: Converter attachments
        reply_to_message_id=request.reply_to_message_id,
    )
    
    if not message:
        raise HTTPException(status_code=400, detail="Failed to send message")
    
    return message.model_dump()


@router.post("/broadcast", response_model=Dict[str, Any])
async def broadcast_message(
    request: BroadcastMessageRequest,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Envia mensagem para múltiplos destinos."""
    destinations = [
        (d["connector_id"], d["thread_id"])
        for d in request.destinations
    ]
    
    results = await manager.broadcast_message(
        thread_ids=destinations,
        content=request.content,
    )
    
    return {
        "results": results,
        "total": len(results),
        "successful": sum(1 for r in results.values() if r),
        "failed": sum(1 for r in results.values() if not r),
    }


# ============================================================================
# Threads e Usuários
# ============================================================================

@router.get("/connectors/{connector_id}/threads/{thread_id}", response_model=Dict[str, Any])
async def get_thread(
    connector_id: str,
    thread_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Obtém informações de uma thread."""
    connector = manager.get_connector(connector_id)
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    thread = await connector.get_thread(thread_id)
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    return thread.model_dump()


@router.get("/connectors/{connector_id}/threads/{thread_id}/messages", response_model=List[Dict[str, Any]])
async def get_messages(
    connector_id: str,
    thread_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    before_message_id: Optional[str] = None,
    manager: ChannelManager = Depends(get_channel_manager),
) -> List[Dict[str, Any]]:
    """Obtém mensagens de uma thread."""
    connector = manager.get_connector(connector_id)
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    messages = await connector.get_messages(thread_id, limit, before_message_id)
    
    return [m.model_dump() for m in messages]


@router.get("/connectors/{connector_id}/users/{user_id}", response_model=Dict[str, Any])
async def get_user(
    connector_id: str,
    user_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Obtém informações de um usuário."""
    connector = manager.get_connector(connector_id)
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    user = await connector.get_user(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user.model_dump()


# ============================================================================
# Identidade de Usuários
# ============================================================================

@router.post("/users/identity", response_model=Dict[str, Any])
async def create_user_identity(
    request: UserIdentityCreateRequest,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Cria identidade unificada de usuário."""
    from .models import UserIdentity
    
    identity = UserIdentity(
        display_name=request.display_name,
        username=request.username,
        email=request.email,
        phone=request.phone,
        avatar_url=request.avatar_url,
        channel_ids={
            ChannelType(k): v for k, v in request.channel_ids.items()
        },
    )
    
    # Armazenar no manager
    manager._user_identities[identity.id] = identity
    
    return identity.model_dump()


@router.get("/users/identity/{identity_id}", response_model=Dict[str, Any])
async def get_user_identity(
    identity_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Obtém identidade unificada de usuário."""
    identity = manager._user_identities.get(identity_id)
    
    if not identity:
        raise HTTPException(status_code=404, detail="User identity not found")
    
    return identity.model_dump()


@router.get("/users/lookup", response_model=Dict[str, Any])
async def lookup_user_by_channel(
    channel_type: ChannelType,
    channel_user_id: str,
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Busca identidade unificada por ID de canal."""
    identity = manager.get_user_by_channel_id(channel_type, channel_user_id)
    
    if not identity:
        raise HTTPException(status_code=404, detail="User not found")
    
    return identity.model_dump()


# ============================================================================
# Health e Status
# ============================================================================

@router.get("/health", response_model=Dict[str, Any])
async def health_check(
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Verifica saúde de todos os conectores."""
    results = await manager.health_check()
    overall_healthy = all(r.get("healthy", False) for r in results.values())
    
    return {
        "overall_healthy": overall_healthy,
        "connectors": results,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/status", response_model=Dict[str, Any])
async def get_status(
    manager: ChannelManager = Depends(get_channel_manager),
) -> Dict[str, Any]:
    """Obtém status geral do Channel Manager."""
    return manager.get_status()


# Re-exportar router
__all__ = [
    "router",
]

"""
core/channels/connectors/whatsapp.py — WhatsApp Connector

Conector para WhatsApp usando WhatsApp Business API ou whatsapp-web.js via bridge.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from ..base import (
    AuthenticationError,
    BaseConnector,
    ConnectionError,
    MessageError,
    RateLimitError,
)
from ..models import (
    ChannelAttachment,
    ChannelConnectorConfig,
    ChannelMessage,
    ChannelThread,
    ChannelType,
    ConnectorStatus,
    MessageType,
    ThreadType,
    UserIdentity,
)

logger = logging.getLogger(__name__)


class WhatsAppConnector(BaseConnector):
    """
    Conector para WhatsApp.
    
    Suporta duas modalidades:
    1. WhatsApp Business API (oficial, requer Meta approval)
    2. whatsapp-web.js bridge (não oficial, via Node.js)
    
    Por padrão, tenta usar a API oficial se configurada.
    """
    
    def __init__(self, config: ChannelConnectorConfig):
        """
        Inicializa o conector WhatsApp.
        
        Args:
            config: Configuração com:
                - api_type: "business_api" ou "web_js"
                - Para Business API: phone_number_id, access_token, business_account_id
                - Para Web JS: bridge_url, session_name
        """
        super().__init__(config)
        
        self.api_type = config.config.get("api_type", "business_api")
        
        # Configurações Business API
        self.phone_number_id = config.config.get("phone_number_id")
        self.access_token = config.config.get("access_token")
        self.business_account_id = config.config.get("business_account_id")
        
        # Configurações Web JS Bridge
        self.bridge_url = config.config.get("bridge_url", "http://localhost:3000")
        self.session_name = config.config.get("session_name", "default")
        
        # State
        self._client = None
        self._bridge_ws = None
        self._polling_task = None
        
    @property
    def channel_type(self) -> ChannelType:
        """Retorna tipo de canal."""
        return ChannelType.WHATSAPP
    
    async def connect(self) -> bool:
        """
        Conecta ao WhatsApp.
        
        Returns:
            True se conectado com sucesso
        """
        try:
            self.status = ConnectorStatus.CONNECTING
            
            if self.api_type == "business_api":
                await self._connect_business_api()
            else:
                await self._connect_web_js()
            
            self.status = ConnectorStatus.CONNECTED
            self.config.status = ConnectorStatus.CONNECTED
            
            logger.info(f"Connected to WhatsApp ({self.api_type})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to WhatsApp: {e}")
            self.status = ConnectorStatus.ERROR
            self.config.status = ConnectorStatus.ERROR
            self.config.last_error = str(e)
            raise ConnectionError(f"Failed to connect to WhatsApp: {e}")
    
    async def _connect_business_api(self) -> None:
        """Conecta via Business API."""
        import httpx
        
        if not self.access_token or not self.phone_number_id:
            raise AuthenticationError("Business API requires access_token and phone_number_id")
        
        # Verificar conexão
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v18.0/{self.phone_number_id}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            
            if response.status_code != 200:
                raise AuthenticationError(f"Failed to authenticate: {response.text}")
            
            data = response.json()
            logger.info(f"Connected to WhatsApp Business API: {data.get('display_phone_number')}")
        
        # Iniciar polling de mensagens (webhook seria ideal, mas polling funciona)
        self._polling_task = asyncio.create_task(self._business_api_polling())
    
    async def _connect_web_js(self) -> None:
        """Conecta via Web JS Bridge."""
        import aiohttp
        
        # Verificar se bridge está rodando
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.bridge_url}/health") as response:
                    if response.status != 200:
                        raise ConnectionError(f"Bridge not healthy: {response.status}")
            except Exception as e:
                raise ConnectionError(f"Cannot connect to bridge at {self.bridge_url}: {e}")
        
        # Iniciar sessão
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.bridge_url}/session/start",
                json={"session_name": self.session_name},
            ) as response:
                if response.status != 200:
                    data = await response.json()
                    raise ConnectionError(f"Failed to start session: {data}")
        
        logger.info(f"Connected to WhatsApp Web JS Bridge: {self.session_name}")
        
        # Iniciar WebSocket para receber mensagens
        self._polling_task = asyncio.create_task(self._web_js_websocket())
    
    async def disconnect(self) -> bool:
        """
        Desconecta do WhatsApp.
        
        Returns:
            True se desconectado com sucesso
        """
        try:
            self.status = ConnectorStatus.DISCONNECTED
            
            # Cancelar polling
            if self._polling_task:
                self._polling_task.cancel()
                try:
                    await self._polling_task
                except asyncio.CancelledError:
                    pass
                self._polling_task = None
            
            # Fechar conexões
            self._client = None
            self._bridge_ws = None
            
            self.config.status = ConnectorStatus.DISCONNECTED
            
            logger.info("Disconnected from WhatsApp")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from WhatsApp: {e}")
            return False
    
    async def send_message(
        self,
        thread_id: str,
        content: str,
        attachments: Optional[List[ChannelAttachment]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> ChannelMessage:
        """
        Envia mensagem no WhatsApp.
        
        Args:
            thread_id: Número de telefone do destinatário (com código do país)
            content: Texto da mensagem
            attachments: Anexos
            reply_to_message_id: ID da mensagem para responder
            
        Returns:
            Mensagem enviada
        """
        if self.api_type == "business_api":
            return await self._send_message_business_api(
                thread_id, content, attachments, reply_to_message_id
            )
        else:
            return await self._send_message_web_js(
                thread_id, content, attachments, reply_to_message_id
            )
    
    async def _send_message_business_api(
        self,
        thread_id: str,
        content: str,
        attachments: Optional[List] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> ChannelMessage:
        """Envia mensagem via Business API."""
        import httpx
        
        url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        
        # Preparar payload
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": thread_id,
        }
        
        # Adicionar contexto de reply se necessário
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}
        
        # Enviar anexo ou texto
        if attachments:
            attachment = attachments[0]  # WhatsApp permite um anexo por vez
            
            if attachment.type.value == "image":
                payload["type"] = "image"
                payload["image"] = {
                    "link": attachment.url or "",
                    "caption": content if content else None,
                }
            elif attachment.type.value == "document":
                payload["type"] = "document"
                payload["document"] = {
                    "link": attachment.url or "",
                    "caption": content if content else None,
                    "filename": attachment.file_name or "document",
                }
            elif attachment.type.value == "audio":
                payload["type"] = "audio"
                payload["audio"] = {"link": attachment.url or ""}
            elif attachment.type.value == "video":
                payload["type"] = "video"
                payload["video"] = {
                    "link": attachment.url or "",
                    "caption": content if content else None,
                }
            else:
                # Fallback para texto
                payload["type"] = "text"
                payload["text"] = {"body": content}
        else:
            # Mensagem de texto
            payload["type"] = "text"
            payload["text"] = {"body": content}
        
        # Enviar
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                error_data = response.json()
                raise MessageError(f"WhatsApp API error: {error_data}")
            
            data = response.json()
            message_id = data.get("messages", [{}])[0].get("id", "unknown")
            
            # Criar mensagem de retorno
            return ChannelMessage(
                id=message_id,
                channel_id=self.connector_id,
                channel_type=ChannelType.WHATSAPP,
                thread_id=thread_id,
                message_type=MessageType.TEXT if not attachments else MessageType(attachments[0].type.value),
                content=content,
                author_id=self.phone_number_id or "0",
                created_at=datetime.utcnow(),
                metadata={
                    "whatsapp_message_id": message_id,
                    "recipient": thread_id,
                },
            )
    
    async def _send_message_web_js(
        self,
        thread_id: str,
        content: str,
        attachments: Optional[List] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> ChannelMessage:
        """Envia mensagem via Web JS Bridge."""
        import aiohttp
        
        url = f"{self.bridge_url}/message/send"
        
        payload = {
            "session_name": self.session_name,
            "to": thread_id,
            "content": content,
        }
        
        if reply_to_message_id:
            payload["reply_to"] = reply_to_message_id
        
        if attachments:
            payload["attachments"] = [
                {
                    "url": att.url,
                    "type": att.type.value,
                    "filename": att.file_name,
                }
                for att in attachments
            ]
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise MessageError(f"Bridge error: {error_text}")
                
                data = await response.json()
                message_id = data.get("message_id", "unknown")
                
                return ChannelMessage(
                    id=message_id,
                    channel_id=self.connector_id,
                    channel_type=ChannelType.WHATSAPP,
                    thread_id=thread_id,
                    message_type=MessageType.TEXT if not attachments else MessageType(attachments[0].type.value),
                    content=content,
                    author_id="me",
                    created_at=datetime.utcnow(),
                    metadata={
                        "whatsapp_message_id": message_id,
                        "sent_via": "web_js_bridge",
                    },
                )
    
    async def _business_api_polling(self) -> None:
        """Polling para receber mensagens via Business API."""
        import httpx
        
        url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        while self._is_running:
            try:
                # TODO: Implementar webhook ou long-polling real
                # A API do WhatsApp Business usa webhooks, não polling
                # Esta é uma implementação placeholder
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Business API polling: {e}")
                await asyncio.sleep(5)
    
    async def _web_js_websocket(self) -> None:
        """WebSocket para receber mensagens via Web JS Bridge."""
        import aiohttp
        
        ws_url = self.bridge_url.replace("http", "ws") + "/ws"
        
        while self._is_running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_url) as ws:
                        self._bridge_ws = ws
                        logger.info("Connected to WhatsApp Web JS Bridge WebSocket")
                        
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_bridge_message(msg.json())
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(f"Bridge WebSocket error: {ws.exception()}")
                                break
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                break
                
                if self._is_running:
                    logger.warning("Bridge WebSocket disconnected, reconnecting...")
                    await asyncio.sleep(5)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Bridge WebSocket error: {e}")
                await asyncio.sleep(5)
    
    async def _handle_bridge_message(self, data: Dict[str, Any]) -> None:
        """Processa mensagem recebida do bridge."""
        try:
            event_type = data.get("event")
            
            if event_type == "message":
                message_data = data.get("message", {})
                
                # Converter para formato unificado
                message = ChannelMessage(
                    id=message_data.get("id", "unknown"),
                    channel_id=self.connector_id,
                    channel_type=ChannelType.WHATSAPP,
                    thread_id=message_data.get("from", "unknown"),
                    message_type=MessageType.TEXT,
                    content=message_data.get("body", ""),
                    author_id=message_data.get("from", "unknown"),
                    created_at=datetime.utcnow(),
                    metadata={
                        "whatsapp_message_id": message_data.get("id"),
                        "is_group": message_data.get("isGroup", False),
                    },
                )
                
                # Notificar handlers
                await self._handle_message(message)
                
            elif event_type == "status":
                logger.info(f"Bridge status: {data.get('status')}")
                
        except Exception as e:
            logger.error(f"Error handling bridge message: {e}")
    
    async def get_messages(
        self,
        thread_id: str,
        limit: int = 50,
        before_message_id: Optional[str] = None,
    ) -> List[ChannelMessage]:
        """Obtém mensagens de uma conversa."""
        # WhatsApp não tem API para pegar histórico
        return []
    
    async def get_thread(self, thread_id: str) -> Optional[ChannelThread]:
        """Obtém informações de uma conversa."""
        # Criar thread básica
        return ChannelThread(
            id=thread_id,
            channel_id=self.connector_id,
            channel_type=ChannelType.WHATSAPP,
            thread_type=ThreadType.DIRECT,
            participant_ids=[thread_id],
        )
    
    async def get_user(self, user_id: str) -> Optional[UserIdentity]:
        """Obtém informações de um usuário."""
        return UserIdentity(
            channel_ids={ChannelType.WHATSAPP: user_id},
            display_name=user_id,  # WhatsApp não expõe nome via API
        )


# Re-exportar
__all__ = [
    "WhatsAppConnector",
]

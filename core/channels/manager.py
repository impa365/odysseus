"""
core/channels/manager.py — Channel Manager

Gerencia todos os conectores de canais ativos.
Orquestra mensagens entre canais e o sistema Odysseus.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Type, Union

from .base import BaseConnector
from .models import (
    ChannelConnectorConfig,
    ChannelMessage,
    ChannelThread,
    ChannelType,
    ConnectorStatus,
    UserIdentity,
)

logger = logging.getLogger(__name__)


class ChannelManager:
    """
    Gerenciador de canais.
    
    Gerencia múltiplos conectores, roteia mensagens,
    sincroniza threads e mantém identidade de usuários.
    """
    
    def __init__(self, db_connection=None):
        """
        Inicializa o manager.
        
        Args:
            db_connection: Conexão com banco de dados
        """
        self.db = db_connection
        self._connectors: Dict[str, BaseConnector] = {}
        self._connector_classes: Dict[ChannelType, Type[BaseConnector]] = {}
        
        # Callbacks
        self._message_callbacks: List[Callable[[ChannelMessage], Any]] = []
        self._connector_callbacks: List[Callable[[str, str], Any]] = []  # (connector_id, event)
        
        # Cache
        self._user_identities: Dict[str, UserIdentity] = {}
        self._thread_mappings: Dict[str, Dict[str, str]] = {}  # thread_id -> {connector_id -> connector_thread_id}
        
        logger.info("ChannelManager initialized")
    
    def register_connector_class(
        self,
        channel_type: ChannelType,
        connector_class: Type[BaseConnector],
    ) -> None:
        """
        Registra classe de conector para um tipo de canal.
        
        Args:
            channel_type: Tipo de canal
            connector_class: Classe do conector
        """
        self._connector_classes[channel_type] = connector_class
        logger.info(f"Registered connector class for {channel_type}")
    
    async def add_connector(
        self,
        config: ChannelConnectorConfig,
    ) -> BaseConnector:
        """
        Adiciona e conecta um novo conector.
        
        Args:
            config: Configuração do conector
            
        Returns:
            Conector conectado
            
        Raises:
            ValueError: Se tipo de canal não suportado
            ConnectionError: Se falhar ao conectar
        """
        # Verificar se temos classe registrada
        connector_class = self._connector_classes.get(config.channel_type)
        if not connector_class:
            raise ValueError(
                f"No connector class registered for {config.channel_type}"
            )
        
        # Criar instância
        connector = connector_class(config)
        
        # Registrar callbacks
        connector.on_message(self._on_message_received)
        connector.on_error(self._on_connector_error)
        
        # Conectar
        await connector.connect()
        
        # Armazenar
        self._connectors[config.id] = connector
        
        # Notificar
        await self._notify_connector_event(config.id, "connected")
        
        logger.info(f"Added and connected connector: {config.id} ({config.channel_type})")
        
        return connector
    
    async def remove_connector(
        self,
        connector_id: str,
        force: bool = False,
    ) -> bool:
        """
        Remove um conector.
        
        Args:
            connector_id: ID do conector
            force: Forçar remoção mesmo se não conseguir desconectar
            
        Returns:
            True se removido com sucesso
        """
        connector = self._connectors.get(connector_id)
        if not connector:
            logger.warning(f"Connector not found: {connector_id}")
            return False
        
        try:
            # Desconectar
            if connector.is_connected:
                await connector.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting connector {connector_id}: {e}")
            if not force:
                return False
        
        # Remover
        del self._connectors[connector_id]
        
        # Notificar
        await self._notify_connector_event(connector_id, "disconnected")
        
        logger.info(f"Removed connector: {connector_id}")
        
        return True
    
    async def send_message(
        self,
        connector_id: str,
        thread_id: str,
        content: str,
        attachments: Optional[List] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[ChannelMessage]:
        """
        Envia mensagem através de um conector.
        
        Args:
            connector_id: ID do conector
            thread_id: ID da thread/conversa
            content: Conteúdo da mensagem
            attachments: Anexos
            reply_to_message_id: ID da mensagem para responder
            
        Returns:
            Mensagem enviada ou None se falhou
        """
        connector = self._connectors.get(connector_id)
        if not connector:
            logger.error(f"Connector not found: {connector_id}")
            return None
        
        if not connector.is_connected:
            logger.error(f"Connector not connected: {connector_id}")
            return None
        
        try:
            message = await connector.send_message(
                thread_id=thread_id,
                content=content,
                attachments=attachments,
                reply_to_message_id=reply_to_message_id,
            )
            return message
        except Exception as e:
            logger.error(f"Error sending message via {connector_id}: {e}")
            return None
    
    async def broadcast_message(
        self,
        thread_ids: List[tuple],  # [(connector_id, thread_id), ...]
        content: str,
    ) -> Dict[str, bool]:
        """
        Envia mensagem para múltiplas threads.
        
        Args:
            thread_ids: Lista de tuplas (connector_id, thread_id)
            content: Conteúdo da mensagem
            
        Returns:
            Dict com resultados {f"{connector_id}:{thread_id}": success}
        """
        results = {}
        
        for connector_id, thread_id in thread_ids:
            message = await self.send_message(
                connector_id=connector_id,
                thread_id=thread_id,
                content=content,
            )
            key = f"{connector_id}:{thread_id}"
            results[key] = message is not None
        
        return results
    
    # -----------------------------------------------------------------------
    # Callbacks e Eventos
    # -----------------------------------------------------------------------
    
    def on_message(self, callback: Callable[[ChannelMessage], Any]) -> Callable:
        """
        Registra callback para mensagens.
        
        Args:
            callback: Função a chamar quando receber mensagem
            
        Returns:
            O próprio callback
        """
        self._message_callbacks.append(callback)
        return callback
    
    def on_connector_event(
        self,
        callback: Callable[[str, str], Any],
    ) -> Callable:
        """
        Registra callback para eventos de conectores.
        
        Args:
            callback: Função a chamar quando ocorrer evento
            
        Returns:
            O próprio callback
        """
        self._connector_callbacks.append(callback)
        return callback
    
    async def _on_message_received(self, message: ChannelMessage) -> None:
        """
        Processa mensagem recebida de um conector.
        
        Args:
            message: Mensagem recebida
        """
        # Notificar todos os callbacks
        for callback in self._message_callbacks:
            try:
                result = callback(message)
                if hasattr(result, '__await__'):
                    await result
            except Exception as e:
                logger.exception(f"Error in message callback: {e}")
    
    async def _on_connector_error(self, error: Exception) -> None:
        """
        Processa erro de um conector.
        
        Args:
            error: Erro ocorrido
        """
        logger.error(f"Connector error: {error}")
        # Notificar callbacks se necessário
    
    async def _notify_connector_event(self, connector_id: str, event: str) -> None:
        """
        Notifica evento de conector.
        
        Args:
            connector_id: ID do conector
            event: Tipo de evento
        """
        for callback in self._connector_callbacks:
            try:
                result = callback(connector_id, event)
                if hasattr(result, '__await__'):
                    await result
            except Exception as e:
                logger.exception(f"Error in connector event callback: {e}")
    
    # -----------------------------------------------------------------------
    # Gerenciamento de Identidade
    # -----------------------------------------------------------------------
    
    def map_user_identity(
        self,
        channel_type: ChannelType,
        channel_user_id: str,
        unified_identity: UserIdentity,
    ) -> None:
        """
        Mapeia identidade de usuário cross-canal.
        
        Args:
            channel_type: Tipo de canal
            channel_user_id: ID do usuário no canal
            unified_identity: Identidade unificada
        """
        # Adicionar ID do canal à identidade
        unified_identity.channel_ids[channel_type] = channel_user_id
        
        # Armazenar
        self._user_identities[unified_identity.id] = unified_identity
        
        logger.debug(f"Mapped user identity: {unified_identity.id}")
    
    def get_user_by_channel_id(
        self,
        channel_type: ChannelType,
        channel_user_id: str,
    ) -> Optional[UserIdentity]:
        """
        Busca identidade unificada por ID de canal.
        
        Args:
            channel_type: Tipo de canal
            channel_user_id: ID do usuário no canal
            
        Returns:
            Identidade unificada ou None
        """
        for identity in self._user_identities.values():
            if identity.channel_ids.get(channel_type) == channel_user_id:
                return identity
        return None
    
    # -----------------------------------------------------------------------
    # Informações e Status
    # -----------------------------------------------------------------------
    
    def get_connector(self, connector_id: str) -> Optional[BaseConnector]:
        """
        Obtém conector pelo ID.
        
        Args:
            connector_id: ID do conector
            
        Returns:
            Conector ou None
        """
        return self._connectors.get(connector_id)
    
    def list_connectors(
        self,
        channel_type: Optional[ChannelType] = None,
    ) -> List[BaseConnector]:
        """
        Lista conectores.
        
        Args:
            channel_type: Filtrar por tipo de canal
            
        Returns:
            Lista de conectores
        """
        connectors = list(self._connectors.values())
        
        if channel_type:
            connectors = [
                c for c in connectors
                if c.channel_type == channel_type
            ]
        
        return connectors
    
    def get_status(self) -> Dict[str, Any]:
        """
        Obtém status do manager.
        
        Returns:
            Status
        """
        return {
            "total_connectors": len(self._connectors),
            "connected": sum(
                1 for c in self._connectors.values() if c.is_connected
            ),
            "by_status": {
                status.value: sum(
                    1 for c in self._connectors.values()
                    if c.status == status
                )
                for status in ConnectorStatus
            },
            "registered_connector_classes": list(
                self._connector_classes.keys()
            ),
            "user_identities_mapped": len(self._user_identities),
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica saúde de todos os conectores.
        
        Returns:
            Resultados do health check
        """
        results = {}
        
        for connector_id, connector in self._connectors.items():
            try:
                # Tentar verificar conexão
                if hasattr(connector, 'health_check'):
                    healthy = await connector.health_check()
                else:
                    healthy = connector.is_connected
                
                results[connector_id] = {
                    "healthy": healthy,
                    "status": connector.status.value,
                }
            except Exception as e:
                results[connector_id] = {
                    "healthy": False,
                    "status": "error",
                    "error": str(e),
                }
        
        return results


# Re-exportar
__all__ = [
    "ChannelManager",
]

"""
core/channels/base.py — Base Classes for Channel Bridge

Classes abstratas para conectores de canais.
Define interface unificada para todos os canais.
"""

from __future__ import annotations

import abc
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .models import (
    ChannelAttachment,
    ChannelConnectorConfig,
    ChannelMessage,
    ChannelThread,
    ChannelType,
    ConnectorStatus,
    ThreadType,
    UserIdentity,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class ChannelError(Exception):
    """Erro base para canais."""
    pass


class ConnectionError(ChannelError):
    """Erro de conexão."""
    pass


class AuthenticationError(ChannelError):
    """Erro de autenticação."""
    pass


class RateLimitError(ChannelError):
    """Erro de rate limit."""
    pass


class MessageError(ChannelError):
    """Erro ao processar mensagem."""
    pass


# ============================================================================
# Abstract Base Connector
# ============================================================================

class BaseConnector(abc.ABC):
    """
    Classe base abstrata para conectores de canais.
    
    Todos os conectores (Telegram, Discord, WhatsApp, etc.)
    devem herdar desta classe e implementar os métodos abstratos.
    """
    
    def __init__(self, config: ChannelConnectorConfig):
        """
        Inicializa o conector.
        
        Args:
            config: Configuração do conector
        """
        self.config = config
        self.status = ConnectorStatus.DISCONNECTED
        self._message_handlers: List[Callable[[ChannelMessage], Any]] = []
        self._error_handlers: List[Callable[[Exception], Any]] = []
        self._is_running = False
    
    # -----------------------------------------------------------------------
    # Propriedades
    # -----------------------------------------------------------------------
    
    @property
    def channel_type(self) -> ChannelType:
        """Tipo de canal."""
        return self.config.channel_type
    
    @property
    def connector_id(self) -> str:
        """ID do conector."""
        return self.config.id
    
    @property
    def is_connected(self) -> bool:
        """Se está conectado."""
        return self.status == ConnectorStatus.CONNECTED
    
    @property
    def is_running(self) -> bool:
        """Se está rodando."""
        return self._is_running
    
    # -----------------------------------------------------------------------
    # Métodos abstratos - Devem ser implementados pelas subclasses
    # -----------------------------------------------------------------------
    
    @abc.abstractmethod
    async def connect(self) -> bool:
        """
        Conecta ao canal.
        
        Returns:
            True se conectado com sucesso
            
        Raises:
            ConnectionError: Se falhar ao conectar
            AuthenticationError: Se falhar autenticação
        """
        pass
    
    @abc.abstractmethod
    async def disconnect(self) -> bool:
        """
        Desconecta do canal.
        
        Returns:
            True se desconectado com sucesso
        """
        pass
    
    @abc.abstractmethod
    async def send_message(
        self,
        thread_id: str,
        content: str,
        attachments: Optional[List[ChannelAttachment]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> ChannelMessage:
        """
        Envia mensagem.
        
        Args:
            thread_id: ID da thread/conversa
            content: Conteúdo da mensagem
            attachments: Anexos (opcional)
            reply_to_message_id: ID da mensagem para responder (opcional)
            
        Returns:
            Mensagem enviada
            
        Raises:
            MessageError: Se falhar ao enviar
            RateLimitError: Se atingir rate limit
        """
        pass
    
    @abc.abstractmethod
    async def get_messages(
        self,
        thread_id: str,
        limit: int = 50,
        before_message_id: Optional[str] = None,
    ) -> List[ChannelMessage]:
        """
        Obtém mensagens de uma thread.
        
        Args:
            thread_id: ID da thread
            limit: Limite de mensagens
            before_message_id: Obter mensagens antes desta ID
            
        Returns:
            Lista de mensagens
        """
        pass
    
    @abc.abstractmethod
    async def get_thread(self, thread_id: str) -> Optional[ChannelThread]:
        """
        Obtém informações de uma thread.
        
        Args:
            thread_id: ID da thread
            
        Returns:
            Thread ou None se não encontrada
        """
        pass
    
    @abc.abstractmethod
    async def get_user(self, user_id: str) -> Optional[UserIdentity]:
        """
        Obtém informações de um usuário.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Usuário ou None se não encontrado
        """
        pass
    
    # -----------------------------------------------------------------------
    # Métodos opcionais - Podem ser sobrescritos pelas subclasses
    # -----------------------------------------------------------------------
    
    async def edit_message(
        self,
        message_id: str,
        new_content: str,
    ) -> ChannelMessage:
        """Edita uma mensagem."""
        raise NotImplementedError(f"{self.channel_type} does not support message editing")
    
    async def delete_message(self, message_id: str) -> bool:
        """Deleta uma mensagem."""
        raise NotImplementedError(f"{self.channel_type} does not support message deletion")
    
    async def add_reaction(
        self,
        message_id: str,
        reaction: str,
    ) -> bool:
        """Adiciona reação a uma mensagem."""
        raise NotImplementedError(f"{self.channel_type} does not support reactions")
    
    async def typing_indicator(
        self,
        thread_id: str,
        is_typing: bool = True,
    ) -> bool:
        """Envia indicador de digitação."""
        # Muitos canais não suportam, então retornar False silenciosamente
        return False
    
    # -----------------------------------------------------------------------
    # Handlers e Eventos
    # -----------------------------------------------------------------------
    
    def on_message(self, handler: Callable[[ChannelMessage], Any]) -> Callable:
        """
        Registra handler para mensagens.
        
        Args:
            handler: Função a ser chamada quando receber mensagem
            
        Returns:
            O próprio handler (para uso como decorator)
        """
        self._message_handlers.append(handler)
        return handler
    
    def on_error(self, handler: Callable[[Exception], Any]) -> Callable:
        """
        Registra handler para erros.
        
        Args:
            handler: Função a ser chamada quando ocorrer erro
            
        Returns:
            O próprio handler (para uso como decorator)
        """
        self._error_handlers.append(handler)
        return handler
    
    async def _handle_message(self, message: ChannelMessage) -> None:
        """
        Processa mensagem recebida.
        
        Args:
            message: Mensagem recebida
        """
        for handler in self._message_handlers:
            try:
                result = handler(message)
                if hasattr(result, '__await__'):
                    await result
            except Exception as e:
                logger.exception(f"Error in message handler: {e}")
    
    async def _handle_error(self, error: Exception) -> None:
        """
        Processa erro.
        
        Args:
            error: Erro ocorrido
        """
        for handler in self._error_handlers:
            try:
                result = handler(error)
                if hasattr(result, '__await__'):
                    await result
            except Exception as e:
                logger.exception(f"Error in error handler: {e}")
    
    # -----------------------------------------------------------------------
    # Context Manager
    # -----------------------------------------------------------------------
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Re-exportar
__all__ = [
    "BaseConnector",
    "ChannelError",
    "ConnectionError",
    "AuthenticationError",
    "RateLimitError",
    "MessageError",
]

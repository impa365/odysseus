"""
core/channels/connectors/telegram.py — Telegram Connector

Conector para Telegram usando python-telegram-bot.
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


class TelegramConnector(BaseConnector):
    """
    Conector para Telegram.
    
    Usa python-telegram-bot para interagir com a API do Telegram.
    Suporta mensagens, edições, deleções, e callbacks inline.
    """
    
    def __init__(self, config: ChannelConnectorConfig):
        """
        Inicializa o conector do Telegram.
        
        Args:
            config: Configuração com bot_token em config['bot_token']
        """
        super().__init__(config)
        
        self.bot_token = config.config.get("bot_token")
        if not self.bot_token:
            raise ValueError("Telegram bot_token is required in config")
        
        self._bot = None
        self._application = None
        self._update_queue: Optional[asyncio.Queue] = None
        self._polling_task: Optional[asyncio.Task] = None
    
    @property
    def channel_type(self) -> ChannelType:
        """Retorna tipo de canal."""
        return ChannelType.TELEGRAM
    
    async def connect(self) -> bool:
        """
        Conecta ao Telegram.
        
        Returns:
            True se conectado com sucesso
        """
        try:
            from telegram import Bot
            from telegram.ext import Application
            
            self.status = ConnectorStatus.CONNECTING
            
            # Criar bot
            self._bot = Bot(token=self.bot_token)
            
            # Verificar conexão
            me = await self._bot.get_me()
            logger.info(f"Connected to Telegram as @{me.username} (ID: {me.id})")
            
            # Criar application para handlers
            self._application = Application.builder().token(self.bot_token).build()
            
            # Setup handlers
            self._setup_handlers()
            
            # Iniciar polling em background
            self._update_queue = asyncio.Queue()
            self._polling_task = asyncio.create_task(self._polling_loop())
            
            self.status = ConnectorStatus.CONNECTED
            self.config.status = ConnectorStatus.CONNECTED
            self.config.last_connected_at = datetime.utcnow()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            self.status = ConnectorStatus.ERROR
            self.config.status = ConnectorStatus.ERROR
            self.config.last_error = str(e)
            self.config.error_count += 1
            raise ConnectionError(f"Failed to connect to Telegram: {e}")
    
    async def disconnect(self) -> bool:
        """
        Desconecta do Telegram.
        
        Returns:
            True se desconectado com sucesso
        """
        try:
            self.status = ConnectorStatus.DISCONNECTED
            
            # Parar polling
            if self._polling_task:
                self._polling_task.cancel()
                try:
                    await self._polling_task
                except asyncio.CancelledError:
                    pass
                self._polling_task = None
            
            # Limpar bot
            if self._bot:
                await self._bot.session.close()
                self._bot = None
            
            self._application = None
            self._update_queue = None
            
            self.config.status = ConnectorStatus.DISCONNECTED
            
            logger.info("Disconnected from Telegram")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Telegram: {e}")
            return False
    
    async def send_message(
        self,
        thread_id: str,
        content: str,
        attachments: Optional[List[ChannelAttachment]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> ChannelMessage:
        """
        Envia mensagem no Telegram.
        
        Args:
            thread_id: ID do chat (chat_id no Telegram)
            content: Texto da mensagem
            attachments: Anexos
            reply_to_message_id: ID da mensagem para responder
            
        Returns:
            Mensagem enviada
        """
        from telegram import InputFile
        
        if not self._bot:
            raise MessageError("Not connected to Telegram")
        
        try:
            chat_id = int(thread_id)
            reply_to = int(reply_to_message_id) if reply_to_message_id else None
            
            # Enviar anexos primeiro se houver
            if attachments:
                for attachment in attachments:
                    if attachment.type.value == "image":
                        await self._bot.send_photo(
                            chat_id=chat_id,
                            photo=attachment.url or attachment.file_name,
                            caption=content if attachment == attachments[-1] else None,
                            reply_to_message_id=reply_to if attachment == attachments[-1] else None,
                        )
                    elif attachment.type.value == "document":
                        await self._bot.send_document(
                            chat_id=chat_id,
                            document=attachment.url or attachment.file_name,
                            caption=content if attachment == attachments[-1] else None,
                            reply_to_message_id=reply_to if attachment == attachments[-1] else None,
                        )
                    elif attachment.type.value == "audio":
                        await self._bot.send_audio(
                            chat_id=chat_id,
                            audio=attachment.url or attachment.file_name,
                            caption=content if attachment == attachments[-1] else None,
                            reply_to_message_id=reply_to if attachment == attachments[-1] else None,
                        )
                
                return self._create_message_from_telegram(None, chat_id, content)
            
            # Enviar mensagem de texto
            sent_message = await self._bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_to_message_id=reply_to,
                parse_mode="HTML",
            )
            
            return self._create_message_from_telegram(sent_message, chat_id, content)
            
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            raise MessageError(f"Failed to send message: {e}")
    
    async def get_messages(
        self,
        thread_id: str,
        limit: int = 50,
        before_message_id: Optional[str] = None,
    ) -> List[ChannelMessage]:
        """
        Obtém mensagens de um chat.
        
        Nota: Telegram não suporta pegar histórico via Bot API facilmente.
        Requer usar getUpdates ou armazenar mensagens localmente.
        """
        # Implementação simplificada - em produção, armazenar mensagens em DB
        return []
    
    async def get_thread(self, thread_id: str) -> Optional[ChannelThread]:
        """Obtém informações de um chat."""
        try:
            chat = await self._bot.get_chat(int(thread_id))
            
            thread_type = ThreadType.DIRECT
            if chat.type in ["group", "supergroup"]:
                thread_type = ThreadType.GROUP
            elif chat.type == "channel":
                thread_type = ThreadType.CHANNEL
            
            return ChannelThread(
                id=str(chat.id),
                channel_id=self.connector_id,
                channel_type=ChannelType.TELEGRAM,
                thread_type=thread_type,
                participant_count=chat.member_count or 0,
                title=chat.title or chat.username or str(chat.id),
            )
        except Exception as e:
            logger.error(f"Error getting Telegram chat: {e}")
            return None
    
    async def get_user(self, user_id: str) -> Optional[UserIdentity]:
        """Obtém informações de um usuário."""
        try:
            chat = await self._bot.get_chat(int(user_id))
            
            return UserIdentity(
                channel_ids={ChannelType.TELEGRAM: str(chat.id)},
                display_name=chat.first_name or chat.username or str(chat.id),
                username=chat.username,
            )
        except Exception as e:
            logger.error(f"Error getting Telegram user: {e}")
            return None
    
    # -----------------------------------------------------------------------
    # Métodos Privados
    # -----------------------------------------------------------------------
    
    def _setup_handlers(self) -> None:
        """Configura handlers para updates do Telegram."""
        from telegram.ext import MessageHandler, filters
        
        async def handle_message(update, context):
            """Handler para mensagens."""
            try:
                message = self._convert_telegram_message(update.message)
                await self._handle_message(message)
            except Exception as e:
                logger.error(f"Error handling Telegram message: {e}")
        
        # Adicionar handler
        self._application.add_handler(
            MessageHandler(filters.ALL, handle_message)
        )
    
    async def _polling_loop(self) -> None:
        """Loop de polling para updates."""
        try:
            await self._application.initialize()
            await self._application.start()
            
            while self._is_running:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
            
            await self._application.stop()
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in Telegram polling loop: {e}")
    
    def _convert_telegram_message(self, telegram_message) -> ChannelMessage:
        """Converte mensagem do Telegram para formato unificado."""
        # Detectar tipo de mensagem
        message_type = MessageType.TEXT
        content = ""
        attachments = []
        
        if telegram_message.text:
            content = telegram_message.text
        elif telegram_message.caption:
            content = telegram_message.caption
        
        # Verificar tipos de mídia
        if telegram_message.photo:
            message_type = MessageType.IMAGE
            photo = telegram_message.photo[-1]  # Maior resolução
            attachments.append(ChannelAttachment(
                type=MessageType.IMAGE,
                file_id=str(photo.file_id),
                size_bytes=photo.file_size,
                width=photo.width,
                height=photo.height,
            ))
        
        elif telegram_message.video:
            message_type = MessageType.VIDEO
            video = telegram_message.video
            attachments.append(ChannelAttachment(
                type=MessageType.VIDEO,
                file_id=str(video.file_id),
                file_name=video.file_name,
                mime_type=video.mime_type,
                size_bytes=video.file_size,
                duration_seconds=video.duration,
                width=video.width,
                height=video.height,
            ))
        
        elif telegram_message.document:
            message_type = MessageType.DOCUMENT
            doc = telegram_message.document
            attachments.append(ChannelAttachment(
                type=MessageType.DOCUMENT,
                file_id=str(doc.file_id),
                file_name=doc.file_name,
                mime_type=doc.mime_type,
                size_bytes=doc.file_size,
            ))
        
        elif telegram_message.audio:
            message_type = MessageType.AUDIO
            audio = telegram_message.audio
            attachments.append(ChannelAttachment(
                type=MessageType.AUDIO,
                file_id=str(audio.file_id),
                file_name=audio.file_name,
                mime_type=audio.mime_type,
                size_bytes=audio.file_size,
                duration_seconds=audio.duration,
            ))
        
        elif telegram_message.voice:
            message_type = MessageType.AUDIO
            voice = telegram_message.voice
            attachments.append(ChannelAttachment(
                type=MessageType.AUDIO,
                file_id=str(voice.file_id),
                mime_type="audio/ogg",
                size_bytes=voice.file_size,
                duration_seconds=voice.duration,
            ))
        
        elif telegram_message.sticker:
            message_type = MessageType.STICKER
            sticker = telegram_message.sticker
            attachments.append(ChannelAttachment(
                type=MessageType.STICKER,
                file_id=str(sticker.file_id),
                width=sticker.width,
                height=sticker.height,
                metadata={"is_animated": sticker.is_animated, "is_video": sticker.is_video},
            ))
        
        elif telegram_message.location:
            message_type = MessageType.LOCATION
            location = telegram_message.location
            attachments.append(ChannelAttachment(
                type=MessageType.LOCATION,
                metadata={"latitude": location.latitude, "longitude": location.longitude},
            ))
        
        elif telegram_message.contact:
            message_type = MessageType.CONTACT
            contact = telegram_message.contact
            content = f"Contact: {contact.first_name} {contact.last_name or ''} - {contact.phone_number}"
            attachments.append(ChannelAttachment(
                type=MessageType.CONTACT,
                metadata={
                    "phone_number": contact.phone_number,
                    "first_name": contact.first_name,
                    "last_name": contact.last_name,
                    "user_id": contact.user_id,
                },
            ))
        
        # Criar mensagem unificada
        return ChannelMessage(
            id=str(telegram_message.message_id),
            channel_id=self.connector_id,
            channel_type=ChannelType.TELEGRAM,
            thread_id=str(telegram_message.chat.id),
            message_type=message_type,
            content=content,
            attachments=attachments,
            author_id=str(telegram_message.from_user.id) if telegram_message.from_user else "0",
            reply_to_message_id=str(telegram_message.reply_to_message.message_id) if telegram_message.reply_to_message else None,
            created_at=telegram_message.date,
            metadata={
                "chat_type": telegram_message.chat.type,
                "chat_title": telegram_message.chat.title if hasattr(telegram_message.chat, 'title') else None,
            },
        )
    
    def _create_message_from_telegram(
        self,
        telegram_message,
        chat_id: int,
        content: str,
    ) -> ChannelMessage:
        """Cria mensagem a partir de resposta do Telegram."""
        return ChannelMessage(
            id=str(telegram_message.message_id),
            channel_id=self.connector_id,
            channel_type=ChannelType.TELEGRAM,
            thread_id=str(chat_id),
            message_type=MessageType.TEXT,
            content=content,
            author_id=self._bot.id if self._bot else "0",
            created_at=datetime.utcnow(),
        )


# Re-exportar
__all__ = [
    "TelegramConnector",
]

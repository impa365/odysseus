"""
Models for Subagent System

Define os modelos de dados para execuções de subagentes,
status, configurações e mensagens.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
import uuid
import json


class SubagentStatus(Enum):
    """Status possíveis de uma execução de subagente"""
    PENDING = "pending"           # Aguardando início
    SPAWNING = "spawning"         # Iniciando
    RUNNING = "running"           # Em execução
    PAUSED = "paused"             # Pausado
    COMPLETED = "completed"       # Completado com sucesso
    FAILED = "failed"             # Falhou
    CANCELLED = "cancelled"       # Cancelado
    TIMEOUT = "timeout"           # Timeout
    ORPHANED = "orphaned"         # Órfão (parent morreu)
    RECOVERING = "recovering"     # Em recuperação


class SubagentOutcome(Enum):
    """Resultado de uma execução"""
    SUCCESS = "success"
    PARTIAL = "partial"           # Sucesso parcial
    FAILURE = "failure"
    ABORTED = "aborted"
    TIMEOUT = "timeout"
    ERROR = "error"


class MessageType(Enum):
    """Tipos de mensagens entre agentes"""
    # Lifecycle
    SPAWN = "spawn"
    READY = "ready"
    COMPLETE = "complete"
    FAILED = "failed"
    
    # Control
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    STEER = "steer"              # Mudar direção/modo
    
    # Data
    RESULT = "result"
    PROGRESS = "progress"
    PARTIAL_RESULT = "partial_result"
    
    # Communication
    MESSAGE = "message"
    QUESTION = "question"
    ANSWER = "answer"
    
    # System
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    
    # Context
    CONTEXT_UPDATE = "context_update"
    CONTEXT_REQUEST = "context_request"
    CONTEXT_RESPONSE = "context_response"


@dataclass
class SubagentConfig:
    """Configuração para execução de subagente"""
    # Identificação
    name: str
    description: Optional[str] = None
    
    # Tipo e capacidades
    agent_type: str = "general"     # general, research, code, analysis, etc.
    capabilities: List[str] = field(default_factory=list)
    
    # Ferramentas
    allowed_tools: List[str] = field(default_factory=list)
    blocked_tools: List[str] = field(default_factory=list)
    
    # Limites
    max_iterations: int = 50
    timeout_seconds: int = 600        # 10 minutos
    max_tokens: int = 100000
    
    # Comportamento
    reasoning_level: str = "normal"   # minimal, normal, detailed, maximum
    bootstrap_mode: str = "full"    # full, limited, none
    can_spawn_subagents: bool = False
    
    # Contexto
    system_prompt_addition: Optional[str] = None
    context_files: List[str] = field(default_factory=list)
    
    # Persistência
    save_results: bool = True
    save_conversation: bool = True
    
    # Callbacks
    on_progress: Optional[Callable] = None
    on_complete: Optional[Callable] = None
    on_error: Optional[Callable] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa config para dict (exclui callbacks)"""
        data = {
            'name': self.name,
            'description': self.description,
            'agent_type': self.agent_type,
            'capabilities': self.capabilities,
            'allowed_tools': self.allowed_tools,
            'blocked_tools': self.blocked_tools,
            'max_iterations': self.max_iterations,
            'timeout_seconds': self.timeout_seconds,
            'max_tokens': self.max_tokens,
            'reasoning_level': self.reasoning_level,
            'bootstrap_mode': self.bootstrap_mode,
            'can_spawn_subagents': self.can_spawn_subagents,
            'system_prompt_addition': self.system_prompt_addition,
            'context_files': self.context_files,
            'save_results': self.save_results,
            'save_conversation': self.save_conversation,
        }
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubagentConfig':
        """Cria config a partir de dict"""
        return cls(
            name=data.get('name', 'unnamed'),
            description=data.get('description'),
            agent_type=data.get('agent_type', 'general'),
            capabilities=data.get('capabilities', []),
            allowed_tools=data.get('allowed_tools', []),
            blocked_tools=data.get('blocked_tools', []),
            max_iterations=data.get('max_iterations', 50),
            timeout_seconds=data.get('timeout_seconds', 600),
            max_tokens=data.get('max_tokens', 100000),
            reasoning_level=data.get('reasoning_level', 'normal'),
            bootstrap_mode=data.get('bootstrap_mode', 'full'),
            can_spawn_subagents=data.get('can_spawn_subagents', False),
            system_prompt_addition=data.get('system_prompt_addition'),
            context_files=data.get('context_files', []),
            save_results=data.get('save_results', True),
            save_conversation=data.get('save_conversation', True),
        )


@dataclass  
class SubagentRun:
    """Representa uma execução de subagente"""
    # Identificadores
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "unnamed"
    
    # Hierarquia
    parent_id: Optional[str] = None
    session_id: str = ""          # Sessão do usuário
    user_id: str = ""             # ID do usuário
    
    # Configuração
    config: SubagentConfig = field(default_factory=lambda: SubagentConfig(name="default"))
    
    # Status e resultado
    status: SubagentStatus = SubagentStatus.PENDING
    outcome: Optional[SubagentOutcome] = None
    
    # Dados
    task_description: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Métricas
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    iteration_count: int = 0
    token_usage: int = 0
    cost_estimate: float = 0.0
    
    # Relações
    child_ids: List[str] = field(default_factory=list)
    messages: List['SubagentMessage'] = field(default_factory=list)
    checkpoints: List[Dict] = field(default_factory=list)
    
    # Flags
    is_checkpointed: bool = False
    can_recover: bool = True
    is_orphaned: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa para dict"""
        return {
            'id': self.id,
            'name': self.name,
            'parent_id': self.parent_id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'config': self.config.to_dict(),
            'status': self.status.value,
            'outcome': self.outcome.value if self.outcome else None,
            'task_description': self.task_description,
            'input_data': self.input_data,
            'output_data': self.output_data,
            'result_summary': self.result_summary,
            'error_message': self.error_message,
            'error_traceback': self.error_traceback,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'iteration_count': self.iteration_count,
            'token_usage': self.token_usage,
            'cost_estimate': self.cost_estimate,
            'child_ids': self.child_ids,
            'is_checkpointed': self.is_checkpointed,
            'can_recover': self.can_recover,
            'is_orphaned': self.is_orphaned,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubagentRun':
        """Cria a partir de dict"""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'unnamed'),
            parent_id=data.get('parent_id'),
            session_id=data.get('session_id', ''),
            user_id=data.get('user_id', ''),
            config=SubagentConfig.from_dict(data.get('config', {})),
            status=SubagentStatus(data.get('status', 'pending')),
            outcome=SubagentOutcome(data['outcome']) if data.get('outcome') else None,
            task_description=data.get('task_description', ''),
            input_data=data.get('input_data', {}),
            output_data=data.get('output_data', {}),
            result_summary=data.get('result_summary', ''),
            error_message=data.get('error_message'),
            error_traceback=data.get('error_traceback'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.utcnow(),
            started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else None,
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            iteration_count=data.get('iteration_count', 0),
            token_usage=data.get('token_usage', 0),
            cost_estimate=data.get('cost_estimate', 0.0),
            child_ids=data.get('child_ids', []),
            is_checkpointed=data.get('is_checkpointed', False),
            can_recover=data.get('can_recover', True),
            is_orphaned=data.get('is_orphaned', False),
        )


@dataclass
class SubagentMessage:
    """Mensagem trocada entre agentes"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""                      # ID do subagent run
    parent_run_id: Optional[str] = None   # ID do parent (se houver)
    
    message_type: MessageType = MessageType.MESSAGE
    direction: str = "incoming"           # incoming/outgoing
    
    content: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sequence_number: int = 0              # Ordem na conversa
    
    # Metadados
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'run_id': self.run_id,
            'parent_run_id': self.parent_run_id,
            'message_type': self.message_type.value,
            'direction': self.direction,
            'content': self.content,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'sequence_number': self.sequence_number,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubagentMessage':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            run_id=data.get('run_id', ''),
            parent_run_id=data.get('parent_run_id'),
            message_type=MessageType(data.get('message_type', 'message')),
            direction=data.get('direction', 'incoming'),
            content=data.get('content', ''),
            payload=data.get('payload', {}),
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else datetime.utcnow(),
            sequence_number=data.get('sequence_number', 0),
            metadata=data.get('metadata', {}),
        )

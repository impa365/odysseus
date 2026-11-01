"""
Database Models for Subagent System

SQLAlchemy models para persistência de subagentes.
"""

from sqlalchemy import (
    Column, String, Integer, DateTime, Text, 
    ForeignKey, Enum, Float, Boolean, JSON,
    Index, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import enum

Base = declarative_base()


class DBSubagentStatus(str, enum.Enum):
    """Status de subagente no banco"""
    PENDING = "pending"
    SPAWNING = "spawning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    ORPHANED = "orphaned"
    RECOVERING = "recovering"


class DBSubagentOutcome(str, enum.Enum):
    """Outcome de subagente no banco"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    ABORTED = "aborted"
    TIMEOUT = "timeout"
    ERROR = "error"


class DBSubagentRun(Base):
    """Modelo de execução de subagente"""
    
    __tablename__ = 'subagent_runs'
    
    # Identificação
    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    
    # Hierarquia
    parent_id = Column(String(36), ForeignKey('subagent_runs.id'), nullable=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    
    # Configuração (JSON)
    config = Column(JSON, nullable=False)
    
    # Status e resultado
    status = Column(Enum(DBSubagentStatus), nullable=False, index=True)
    outcome = Column(Enum(DBSubagentOutcome), nullable=True)
    
    # Dados
    task_description = Column(Text, nullable=False)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    result_summary = Column(Text)
    
    # Erros
    error_message = Column(Text)
    error_traceback = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Métricas
    iteration_count = Column(Integer, default=0)
    token_usage = Column(Integer, default=0)
    cost_estimate = Column(Float, default=0.0)
    
    # Relações
    parent = relationship("DBSubagentRun", remote_side=[id], backref="children")
    messages = relationship("DBSubagentMessage", back_populates="run", cascade="all, delete-orphan")
    
    # Flags
    is_checkpointed = Column(Boolean, default=False)
    can_recover = Column(Boolean, default=True)
    is_orphaned = Column(Boolean, default=False, index=True)
    
    # Checkpoints (JSON array)
    checkpoints = Column(JSON, default=list)
    
    # Índices compostos
    __table_args__ = (
        Index('idx_subagent_user_status', 'user_id', 'status'),
        Index('idx_subagent_session_created', 'session_id', 'created_at'),
        Index('idx_subagent_parent_status', 'parent_id', 'status'),
        Index('idx_subagent_orphaned', 'is_orphaned', 'status'),
    )
    
    def to_dict(self) -> dict:
        """Converte para dict"""
        return {
            'id': self.id,
            'name': self.name,
            'parent_id': self.parent_id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'config': self.config,
            'status': self.status.value if self.status else None,
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
            'is_checkpointed': self.is_checkpointed,
            'can_recover': self.can_recover,
            'is_orphaned': self.is_orphaned,
            'checkpoints': self.checkpoints,
        }


class DBSubagentMessage(Base):
    """Modelo de mensagem entre agentes"""
    
    __tablename__ = 'subagent_messages'
    
    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey('subagent_runs.id'), nullable=False, index=True)
    parent_run_id = Column(String(36), nullable=True)
    
    message_type = Column(String(50), nullable=False, index=True)
    direction = Column(String(20), nullable=False)  # incoming/outgoing
    
    content = Column(Text, nullable=False)
    payload = Column(JSON, default=dict)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    sequence_number = Column(Integer, default=0)
    
    metadata = Column(JSON, default=dict)
    
    # Relação
    run = relationship("DBSubagentRun", back_populates="messages")
    
    # Índice composto
    __table_args__ = (
        Index('idx_message_run_timestamp', 'run_id', 'timestamp'),
        Index('idx_message_type_timestamp', 'message_type', 'timestamp'),
    )
    
    def to_dict(self) -> dict:
        """Converte para dict"""
        return {
            'id': self.id,
            'run_id': self.run_id,
            'parent_run_id': self.parent_run_id,
            'message_type': self.message_type,
            'direction': self.direction,
            'content': self.content,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'sequence_number': self.sequence_number,
            'metadata': self.metadata,
        }


# ============================================================================
# MIGRATIONS
# ============================================================================

def create_tables(engine):
    """Cria todas as tabelas"""
    Base.metadata.create_all(engine)


def drop_tables(engine):
    """Dropa todas as tabelas"""
    Base.metadata.drop_all(engine)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == '__main__':
    # Criar engine SQLite para teste
    engine = create_engine('sqlite:///test_subagents.db', echo=True)
    
    # Criar tabelas
    create_tables(engine)
    
    print("Tabelas criadas com sucesso!")
    print("Tabelas:", Base.metadata.tables.keys())

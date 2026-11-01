"""
Odysseus Subagent System

Sistema de subagentes para execução paralela de tarefas.

Módulos:
- registry.py  : SubagentRegistry (spawn, resume, complete, cancel)
- models.py    : SubagentRun, SubagentConfig, SubagentMessage
- database.py  : SQLAlchemy models para persistência
- api.py       : REST API endpoints (usado por routes/subagent_routes.py)
"""

__version__ = "1.0.0"

from .registry import SubagentRegistry, get_registry
from .models import (
    SubagentRun,
    SubagentStatus,
    SubagentOutcome,
    SubagentConfig,
    SubagentMessage,
    MessageType
)

__all__ = [
    'SubagentRegistry',
    'get_registry',
    'SubagentRun',
    'SubagentStatus',
    'SubagentOutcome',
    'SubagentConfig',
    'SubagentMessage',
    'MessageType',
]

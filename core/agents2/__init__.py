"""
core/agents2/__init__.py — Agent System 2.0

Sistema de agentes autônomos, proativos e auto-evolutivos.

Arquitetura:
- AutonomousAgent: Loop principal (Observe → Plan → Act → Reflect)
- Planner: Planejamento de tarefas
- ToolExecutor: Execução de ferramentas
- AgentMemory: Memória episódica, semântica e procedural
- Reflection: Auto-reflexão e melhoria contínua
- EvolutionEngine: Evolução via algoritmos genéticos
"""

__version__ = "2.0.0"

from .agent import (
    AutonomousAgent,
    AgentConfig,
    AgentState,
    Observation,
    Action,
)

from .planner import (
    Planner,
    Plan,
    Step,
)

from .executor import (
    ToolExecutor,
    ToolResult,
    Tool,
    ShellTool,
    FileTool,
    APITool,
)

from .memory import (
    AgentMemory,
    Episode,
    EpisodicMemory,
    SemanticFact,
    SemanticMemory,
)

from .reflection import (
    Reflection,
    Insight,
    PerformanceAnalyzer,
    ReflectionEngine,
)

from .evolution import (
    EvolutionEngine,
    AgentGene,
)

__all__ = [
    # Version
    "__version__",
    
    # Agent
    "AutonomousAgent",
    "AgentConfig",
    "AgentState",
    "Observation",
    "Action",
    
    # Planner
    "Planner",
    "Plan",
    "Step",
    
    # Executor
    "ToolExecutor",
    "ToolResult",
    "Tool",
    "ShellTool",
    "FileTool",
    "APITool",
    
    # Memory
    "AgentMemory",
    "Episode",
    "EpisodicMemory",
    "SemanticFact",
    "SemanticMemory",
    
    # Reflection
    "Reflection",
    "Insight",
    "PerformanceAnalyzer",
    "ReflectionEngine",
    
    # Evolution
    "EvolutionEngine",
    "AgentGene",
]

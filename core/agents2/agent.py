"""
core/agents2/agent.py — Autonomous Agent Core

Agente autônomo com loop principal:
OBSERVE → PLAN → ACT → REFLECT
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar

from .memory import AgentMemory, EpisodicMemory
from .planner import Planner, Plan, Step
from .executor import ToolExecutor, ToolResult
from .reflection import Reflection, PerformanceAnalyzer

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Estados do agente."""
    IDLE = auto()
    OBSERVING = auto()
    PLANNING = auto()
    EXECUTING = auto()
    REFLECTING = auto()
    PAUSED = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass
class AgentConfig:
    """Configuração do agente."""
    name: str = "autonomous_agent"
    description: str = "Agente autônomo proativo"
    
    # Comportamento
    proactive: bool = True
    max_iterations: int = 100
    reflection_interval: int = 5  # Refletir a cada N ações
    planning_depth: int = 3  # Quanto planejar à frente
    
    # Memória
    memory_enabled: bool = True
    max_episodes: int = 1000
    
    # Tool use
    tool_timeout: int = 30
    allowed_tools: Set[str] = field(default_factory=lambda: {
        "shell", "file_read", "file_write", "api_request", "python_exec"
    })
    
    # LLM
    llm_model: str = "claude-3-opus-20240229"
    llm_temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class Observation:
    """Observação do ambiente."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "user"  # user, system, tool, event
    priority: int = 0  # -10 (low) a 10 (critical)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "metadata": self.metadata,
            "source": self.source,
            "priority": self.priority,
        }


@dataclass  
class Action:
    """Ação executada pelo agente."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    type: str = ""  # tool_use, message, plan, think
    tool: Optional[str] = None
    input_params: Dict[str, Any] = field(default_factory=dict)
    output: Any = None
    success: bool = True
    execution_time_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "type": self.type,
            "tool": self.tool,
            "input_params": self.input_params,
            "output": self.output,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
        }


class AutonomousAgent:
    """
    Agente autônomo proativo.
    
    Loop principal:
    1. OBSERVE - Perceber ambiente
    2. PLAN - Criar plano de ação
    3. ACT - Executar ações
    4. REFLECT - Refletir e aprender
    
    Características:
    - Proativo (não só reage, inicia ações)
    - Memória de longo prazo
    - Tool use (shell, arquivos, APIs)
    - Self-reflection e melhoria contínua
    - Evolução (pode melhorar com o tempo)
    """
    
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        memory: Optional[AgentMemory] = None,
        planner: Optional[Planner] = None,
        executor: Optional[ToolExecutor] = None,
        reflection: Optional[Reflection] = None,
        llm_client = None,
    ):
        """
        Inicializa agente autônomo.
        
        Args:
            config: Configuração do agente
            memory: Sistema de memória
            planner: Planejador
            executor: Executador de tools
            reflection: Sistema de reflexão
            llm_client: Cliente LLM (OpenAI, Anthropic, etc.)
        """
        self.id = str(uuid.uuid4())
        self.config = config or AgentConfig()
        self.state = AgentState.IDLE
        
        # Componentes
        self.memory = memory or AgentMemory()
        self.planner = planner or Planner(llm_client=llm_client)
        self.executor = executor or ToolExecutor()
        self.reflection = reflection or Reflection()
        self.llm = llm_client
        
        # Estado de execução
        self.observations: List[Observation] = []
        self.actions: List[Action] = []
        self.current_plan: Optional[Plan] = None
        self.iteration_count = 0
        self.last_reflection_index = 0
        
        # Controle
        self._running = False
        self._paused = False
        self._stop_event = asyncio.Event()
        self._observers: List[Callable] = []
        
        logger.info(f"Agent {self.id} initialized: {self.config.name}")
    
    # ================================================================
    # LOOP PRINCIPAL
    # ================================================================
    
    async def run(self, goal: Optional[str] = None) -> None:
        """
        Executa loop principal do agente.
        
        Args:
            goal: Objetivo inicial (opcional)
        """
        if self._running:
            logger.warning("Agent already running")
            return
        
        self._running = True
        self._stop_event.clear()
        self.state = AgentState.OBSERVING
        
        logger.info(f"Agent {self.id} started with goal: {goal}")
        
        try:
            # Loop principal
            while self._running and self.iteration_count < self.config.max_iterations:
                
                # Verificar se deve parar
                if self._stop_event.is_set():
                    break
                
                # Pausar se necessário
                while self._paused:
                    await asyncio.sleep(0.1)
                    if not self._running:
                        return
                
                # EXECUTAR ITERAÇÃO
                await self._iteration(goal)
                
                self.iteration_count += 1
                
                # Notificar observers
                await self._notify_observers()
            
            logger.info(f"Agent {self.id} completed after {self.iteration_count} iterations")
            
        except Exception as e:
            logger.exception(f"Agent {self.id} error: {e}")
            self.state = AgentState.ERROR
        finally:
            self._running = False
    
    async def _iteration(self, goal: Optional[str]) -> None:
        """
        Executa uma iteração do loop.
        
        Fases:
        1. OBSERVE - Perceber ambiente
        2. PLAN - Planejar ações
        3. ACT - Executar ações
        4. REFLECT - Refletir (periódico)
        """
        # ==================== 1. OBSERVE ====================
        self.state = AgentState.OBSERVING
        observation = await self._observe()
        if observation:
            self.observations.append(observation)
            await self.memory.store_observation(observation)
        
        # ==================== 2. PLAN ====================
        self.state = AgentState.PLANNING
        if self.current_plan is None or self.current_plan.is_complete():
            context = self._build_context(goal)
            self.current_plan = await self.planner.create_plan(
                goal=goal or self.config.description,
                context=context,
                observations=self.observations[-10:],  # Últimas 10 observações
            )
            logger.info(f"Created new plan with {len(self.current_plan.steps)} steps")
        
        # Pegar próximo passo
        current_step = self.current_plan.get_next_step()
        if not current_step:
            logger.info("Plan complete")
            self._stop_event.set()
            return
        
        # ==================== 3. ACT ====================
        self.state = AgentState.EXECUTING
        action = await self._act(current_step)
        self.actions.append(action)
        await self.memory.store_action(action)
        
        # Marcar passo como completo se ação foi bem-sucedida
        if action.success:
            current_step.mark_complete()
        else:
            # Se falhou, talvez replanejar
            logger.warning(f"Step failed: {current_step.description}")
            current_step.mark_failed()
        
        # ==================== 4. REFLECT (periódico) ====================
        if self.iteration_count - self.last_reflection_index >= self.config.reflection_interval:
            self.state = AgentState.REFLECTING
            await self._reflect()
            self.last_reflection_index = self.iteration_count
    
    # ================================================================
    # MÉTODOS AUXILIARES
    # ================================================================
    
    async def _observe(self) -> Optional[Observation]:
        """Coleta observações do ambiente."""
        # TODO: Implementar observação real do ambiente
        # Por enquanto, retornar None (sem nova observação)
        return None
    
    async def _act(self, step: Step) -> Action:
        """Executa uma ação baseada no passo."""
        start_time = time.time()
        
        try:
            # Determinar tipo de ação
            if step.tool:
                # Executar tool
                result = await self.executor.execute(
                    tool_name=step.tool,
                    params=step.parameters,
                )
                action = Action(
                    type="tool_use",
                    tool=step.tool,
                    input_params=step.parameters,
                    output=result.output,
                    success=result.success,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
            else:
                # Ação de pensamento/mensagem
                action = Action(
                    type="think",
                    output=step.description,
                    success=True,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
            
            return action
            
        except Exception as e:
            logger.exception(f"Action execution failed: {e}")
            return Action(
                type="error",
                output=str(e),
                success=False,
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
    
    async def _reflect(self) -> None:
        """Executa reflexão sobre desempenho recente."""
        try:
            # Analisar ações recentes
            recent_actions = self.actions[-self.config.reflection_interval:]
            
            # Gerar reflexão
            reflection_result = await self.reflection.reflect(
                observations=self.observations[-10:],
                actions=recent_actions,
                current_plan=self.current_plan,
            )
            
            # Armazenar reflexão
            await self.memory.store_reflection(reflection_result)
            
            # Aplicar aprendizados (ajustar configurações, etc.)
            await self._apply_learnings(reflection_result)
            
            logger.info(f"Reflection completed: {reflection_result.insights}")
            
        except Exception as e:
            logger.exception(f"Reflection failed: {e}")
    
    async def _apply_learnings(self, reflection) -> None:
        """Aplica aprendizados da reflexão."""
        # TODO: Implementar ajustes baseados em reflexão
        pass
    
    def _build_context(self, goal: Optional[str]) -> Dict[str, Any]:
        """Constrói contexto para planejamento."""
        return {
            "agent_id": self.id,
            "agent_name": self.config.name,
            "goal": goal,
            "iteration": self.iteration_count,
            "capabilities": list(self.config.allowed_tools),
        }
    
    # ================================================================
    # CONTROLE PÚBLICO
    # ================================================================
    
    def pause(self) -> None:
        """Pausa execução."""
        self._paused = True
        logger.info(f"Agent {self.id} paused")
    
    def resume(self) -> None:
        """Retoma execução."""
        self._paused = False
        logger.info(f"Agent {self.id} resumed")
    
    def stop(self) -> None:
        """Para execução."""
        self._stop_event.set()
        logger.info(f"Agent {self.id} stopping...")
    
    def add_observer(self, callback: Callable) -> None:
        """Adiciona observer para eventos."""
        self._observers.append(callback)
    
    async def _notify_observers(self) -> None:
        """Notifica observers."""
        for observer in self._observers:
            try:
                if asyncio.iscoroutinefunction(observer):
                    await observer(self)
                else:
                    observer(self)
            except Exception as e:
                logger.warning(f"Observer error: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status atual."""
        return {
            "id": self.id,
            "name": self.config.name,
            "state": self.state.name,
            "iteration": self.iteration_count,
            "observations_count": len(self.observations),
            "actions_count": len(self.actions),
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "running": self._running,
            "paused": self._paused,
        }

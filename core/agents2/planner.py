"""
core/agents2/planner.py — Planner

Planeja sequências de ações para atingir objetivos.
Quebra tarefas complexas em passos executáveis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .memory import AgentMemory

logger = logging.getLogger(__name__)


@dataclass
class Step:
    """Passo individual de um plano."""
    id: str = field(default_factory=lambda: f"step_{datetime.utcnow().timestamp()}")
    description: str = ""
    tool: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # IDs de steps que devem completar primeiro
    expected_output: Optional[str] = None
    
    # Estado
    status: str = "pending"  # pending, in_progress, completed, failed, skipped
    result: Any = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def mark_in_progress(self) -> None:
        """Marca como em execução."""
        self.status = "in_progress"
        self.started_at = datetime.utcnow()
    
    def mark_complete(self, result: Any = None) -> None:
        """Marca como completo."""
        self.status = "completed"
        self.result = result
        self.completed_at = datetime.utcnow()
    
    def mark_failed(self, error: str) -> None:
        """Marca como falho."""
        self.status = "failed"
        self.error_message = error
        self.completed_at = datetime.utcnow()
    
    def can_execute(self, completed_step_ids: Set[str]) -> bool:
        """Verifica se pode executar (dependências satisfeitas)."""
        return all(dep in completed_step_ids for dep in self.dependencies)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "description": self.description,
            "tool": self.tool,
            "parameters": self.parameters,
            "dependencies": self.dependencies,
            "expected_output": self.expected_output,
            "status": self.status,
            "result": self.result,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class Plan:
    """Plano de execução."""
    id: str = field(default_factory=lambda: f"plan_{datetime.utcnow().timestamp()}")
    goal: str = ""
    steps: List[Step] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Metadados
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def get_next_step(self) -> Optional[Step]:
        """Retorna próximo passo executável."""
        completed_ids = {
            step.id for step in self.steps
            if step.status in ("completed", "skipped")
        }
        
        for step in self.steps:
            if step.status == "pending" and step.can_execute(completed_ids):
                return step
        
        return None
    
    def is_complete(self) -> bool:
        """Verifica se plano está completo."""
        return all(
            step.status in ("completed", "skipped", "failed")
            for step in self.steps
        )
    
    def get_progress(self) -> Dict[str, int]:
        """Retorna progresso do plano."""
        total = len(self.steps)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0}
        
        completed = sum(1 for s in self.steps if s.status == "completed")
        failed = sum(1 for s in self.steps if s.status == "failed")
        pending = total - completed - failed
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress": self.get_progress(),
        }


class Planner:
    """
    Planejador de ações.
    
    Responsabilidades:
    - Quebrar objetivos em passos
    - Selecionar tools apropriadas
    - Gerenciar dependências
    - Adaptar planos quando necessário
    """
    
    def __init__(
        self,
        llm_client = None,
        memory: Optional[AgentMemory] = None,
        available_tools: Optional[List[str]] = None,
    ):
        """
        Inicializa planejador.
        
        Args:
            llm_client: Cliente LLM para planejamento
            memory: Memória para contexto
            available_tools: Lista de tools disponíveis
        """
        self.llm = llm_client
        self.memory = memory
        self.available_tools = available_tools or [
            "shell", "file_read", "file_write", "api_request", "python_exec"
        ]
        self.plan_history: List[Plan] = []
    
    async def create_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        observations: Optional[List] = None,
    ) -> Plan:
        """
        Cria plano para atingir objetivo.
        
        Args:
            goal: Objetivo a alcançar
            context: Contexto atual
            observations: Observações recentes
            
        Returns:
            Plano criado
        """
        # Se temos LLM, usar para planejamento inteligente
        if self.llm:
            return await self._llm_planning(goal, context, observations)
        else:
            # Fallback: planejamento simples baseado em regras
            return self._rule_based_planning(goal, context)
    
    async def _llm_planning(
        self,
        goal: str,
        context: Dict[str, Any],
        observations: Optional[List],
    ) -> Plan:
        """Planejamento usando LLM."""
        # Construir prompt
        prompt = self._build_planning_prompt(goal, context, observations)
        
        # Chamar LLM
        response = await self._call_llm(prompt)
        
        # Parse da resposta para criar plano
        try:
            plan_data = self._parse_plan_response(response)
            plan = Plan(
                goal=goal,
                steps=[Step(**step_data) for step_data in plan_data["steps"]],
                context=context,
            )
            self.plan_history.append(plan)
            return plan
        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            return self._rule_based_planning(goal, context)
    
    def _rule_based_planning(self, goal: str, context: Dict[str, Any]) -> Plan:
        """Planejamento simples baseado em regras."""
        steps = []
        
        # Analisar objetivo e criar passos genéricos
        if "file" in goal.lower() or "arquivo" in goal.lower():
            steps.append(Step(
                description="Localizar arquivo",
                tool="file_read",
                parameters={"path": "{{file_path}}"},
            ))
        
        if "command" in goal.lower() or "executar" in goal.lower():
            steps.append(Step(
                description="Executar comando",
                tool="shell",
                parameters={"command": "{{command}}"},
            ))
        
        # Se não conseguiu inferir, criar passo genérico
        if not steps:
            steps.append(Step(
                description=f"Executar: {goal}",
                tool=None,
                parameters={},
            ))
        
        plan = Plan(goal=goal, steps=steps, context=context)
        self.plan_history.append(plan)
        return plan
    
    async def replan(
        self,
        current_plan: Plan,
        failure_reason: str,
        context: Dict[str, Any],
    ) -> Plan:
        """
        Replaneja após falha.
        
        Args:
            current_plan: Plano atual
            failure_reason: Motivo da falha
            context: Contexto
            
        Returns:
            Novo plano
        """
        logger.info(f"Replanning after failure: {failure_reason}")
        
        # Criar novo objetivo com contexto do erro
        new_goal = f"{current_plan.goal} (replan after: {failure_reason})"
        
        # Criar novo plano
        return await self.create_plan(
            goal=new_goal,
            context={**context, "failure_reason": failure_reason, "previous_plan": current_plan.to_dict()},
        )
    
    def _build_planning_prompt(
        self,
        goal: str,
        context: Dict[str, Any],
        observations: Optional[List],
    ) -> str:
        """Constrói prompt para LLM."""
        obs_text = ""
        if observations:
            obs_text = "\n".join([f"- {obs.content}" for obs in observations[-5:]])
        
        return f"""You are an expert task planner. Break down the following goal into concrete, executable steps.

Goal: {goal}

Context:
{json.dumps(context, indent=2, default=str)}

Recent observations:
{obs_text or "No recent observations"}

Available tools: {', '.join(self.available_tools)}

Create a step-by-step plan. Each step should:
1. Be concrete and actionable
2. Use available tools when appropriate
3. Include dependencies if a step depends on previous steps

Respond in JSON format:
{{
  "steps": [
    {{
      "description": "clear description of what to do",
      "tool": "tool_name or null",
      "parameters": {{"param": "value"}},
      "dependencies": ["step_ids"],
      "expected_output": "what should be produced"
    }}
  ]
}}"""
    
    async def _call_llm(self, prompt: str) -> str:
        """Chama LLM."""
        if not self.llm:
            raise ValueError("LLM client not configured")
        
        # Implementação depende do cliente LLM
        # Placeholder para exemplo
        response = await self.llm.generate(prompt)
        return response.content
    
    def _parse_plan_response(self, response: str) -> Dict[str, Any]:
        """Parse da resposta do LLM."""
        # Extrair JSON da resposta
        try:
            # Tentar parse direto
            return json.loads(response)
        except json.JSONDecodeError:
            # Tentar extrair JSON de markdown
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            raise
    
    def get_plan_history(self) -> List[Plan]:
        """Retorna histórico de planos."""
        return self.plan_history.copy()

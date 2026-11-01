"""
core/agents2/reflection.py — Self-Reflection

Sistema de auto-reflexão do agente:
- Análise de desempenho
- Identificação de padrões
- Geração de insights
- Recomendações de melhoria
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .planner import Plan

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    """Insight gerado pela reflexão."""
    id: str = field(default_factory=lambda: f"insight_{datetime.utcnow().timestamp()}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Conteúdo
    category: str = ""  # performance, pattern, error, improvement
    description: str = ""
    evidence: List[str] = field(default_factory=list)
    
    # Impacto
    severity: str = "medium"  # low, medium, high, critical
    confidence: float = 0.5  # 0-1
    
    # Ação recomendada
    recommendation: str = ""
    actionable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category,
            "description": self.description,
            "evidence": self.evidence,
            "severity": self.severity,
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "actionable": self.actionable,
        }


@dataclass
class Reflection:
    """Resultado de uma sessão de reflexão."""
    id: str = field(default_factory=lambda: f"reflection_{datetime.utcnow().timestamp()}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Contexto
    iteration_start: int = 0
    iteration_end: int = 0
    observations_analyzed: int = 0
    actions_analyzed: int = 0
    
    # Resultados
    insights: List[Insight] = field(default_factory=list)
    patterns_identified: List[Dict[str, Any]] = field(default_factory=list)
    errors_identified: List[Dict[str, Any]] = field(default_factory=list)
    improvements_suggested: List[str] = field(default_factory=list)
    
    # Métricas
    performance_score: float = 0.0  # 0-1
    learning_rate: float = 0.0  # melhoria relativa
    
    # Decisões
    plan_adjustments: List[Dict[str, Any]] = field(default_factory=list)
    behavior_changes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "iteration_start": self.iteration_start,
            "iteration_end": self.iteration_end,
            "observations_analyzed": self.observations_analyzed,
            "actions_analyzed": self.actions_analyzed,
            "insights": [i.to_dict() for i in self.insights],
            "patterns_identified": self.patterns_identified,
            "errors_identified": self.errors_identified,
            "improvements_suggested": self.improvements_suggested,
            "performance_score": self.performance_score,
            "learning_rate": self.learning_rate,
            "plan_adjustments": self.plan_adjustments,
            "behavior_changes": self.behavior_changes,
        }


class PerformanceAnalyzer:
    """
    Analisador de desempenho.
    
    Analisa:
    - Taxa de sucesso
    - Eficiência (tempo/resultado)
    - Progresso em direção ao objetivo
    - Padrões de erro
    """
    
    def __init__(self):
        self.metrics_history: List[Dict[str, Any]] = []
    
    def analyze(
        self,
        observations: List[Any],
        actions: List[Any],
        current_plan: Optional[Plan],
        previous_reflection: Optional[Reflection] = None,
    ) -> Dict[str, Any]:
        """
        Analisa desempenho.
        
        Args:
            observations: Observações recentes
            actions: Ações recentes
            current_plan: Plano atual
            previous_reflection: Reflexão anterior
            
        Returns:
            Métricas de desempenho
        """
        if not actions:
            return {"success_rate": 0, "efficiency": 0, "progress": 0}
        
        # Taxa de sucesso
        successful = sum(1 for a in actions if getattr(a, 'success', False))
        success_rate = successful / len(actions)
        
        # Eficiência (ações bem-sucedidas / tempo)
        total_time = sum(
            getattr(a, 'execution_time_ms', 0) for a in actions
        ) / 1000  # converter para segundos
        
        efficiency = successful / total_time if total_time > 0 else 0
        
        # Progresso no plano
        progress = 0
        if current_plan:
            prog = current_plan.get_progress()
            total_steps = prog.get("total", 0)
            completed_steps = prog.get("completed", 0)
            progress = completed_steps / total_steps if total_steps > 0 else 0
        
        # Calcular learning rate (comparação com reflexão anterior)
        learning_rate = 0
        if previous_reflection:
            prev_score = previous_reflection.performance_score
            current_score = (success_rate + efficiency + progress) / 3
            learning_rate = current_score - prev_score
        
        metrics = {
            "success_rate": success_rate,
            "efficiency": efficiency,
            "progress": progress,
            "learning_rate": learning_rate,
            "performance_score": (success_rate + efficiency + progress) / 3,
        }
        
        self.metrics_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            **metrics,
        })
        
        return metrics


class ReflectionEngine:
    """
    Motor de reflexão.
    
    Gera insights através de:
    - Análise de desempenho
    - Identificação de padrões
    - Análise de erros
    - Geração de recomendações
    """
    
    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.analyzer = PerformanceAnalyzer()
        self.reflection_history: List[Reflection] = []
    
    async def reflect(
        self,
        observations: List[Any],
        actions: List[Any],
        current_plan: Optional[Plan],
        iteration_start: int = 0,
        iteration_end: int = 0,
    ) -> Reflection:
        """
        Executa sessão de reflexão.
        
        Args:
            observations: Observações recentes
            actions: Ações recentes
            current_plan: Plano atual
            iteration_start: Iteração inicial
            iteration_end: Iteração final
            
        Returns:
            Resultado da reflexão
        """
        # Analisar desempenho
        previous_reflection = self.reflection_history[-1] if self.reflection_history else None
        metrics = self.analyzer.analyze(observations, actions, current_plan, previous_reflection)
        
        # Criar reflexão
        reflection = Reflection(
            iteration_start=iteration_start,
            iteration_end=iteration_end,
            observations_analyzed=len(observations),
            actions_analyzed=len(actions),
            performance_score=metrics.get("performance_score", 0),
            learning_rate=metrics.get("learning_rate", 0),
        )
        
        # Identificar padrões
        patterns = self._identify_patterns(observations, actions)
        reflection.patterns_identified = patterns
        
        # Identificar erros
        errors = self._identify_errors(actions)
        reflection.errors_identified = errors
        
        # Gerar insights
        insights = await self._generate_insights(
            observations, actions, patterns, errors, metrics
        )
        reflection.insights = insights
        
        # Sugerir melhorias
        improvements = self._suggest_improvements(insights, errors)
        reflection.improvements_suggested = improvements
        
        # Armazenar
        self.reflection_history.append(reflection)
        
        return reflection
    
    def _identify_patterns(
        self,
        observations: List[Any],
        actions: List[Any],
    ) -> List[Dict[str, Any]]:
        """Identifica padrões em observações e ações."""
        patterns = []
        
        # Padrão: Ações repetidas
        action_types = {}
        for action in actions:
            action_type = getattr(action, 'type', str(action))
            action_types[action_type] = action_types.get(action_type, 0) + 1
        
        for action_type, count in action_types.items():
            if count > 2:
                patterns.append({
                    "type": "repeated_action",
                    "description": f"Action '{action_type}' repeated {count} times",
                    "data": {"action_type": action_type, "count": count},
                    "significance": "medium",
                })
        
        # Padrão: Falhas consecutivas
        consecutive_failures = 0
        for action in actions:
            if not getattr(action, 'success', True):
                consecutive_failures += 1
            else:
                if consecutive_failures >= 2:
                    patterns.append({
                        "type": "consecutive_failures",
                        "description": f"{consecutive_failures} consecutive failures",
                        "data": {"count": consecutive_failures},
                        "significance": "high",
                    })
                consecutive_failures = 0
        
        return patterns
    
    def _identify_errors(self, actions: List[Any]) -> List[Dict[str, Any]]:
        """Identifica erros nas ações."""
        errors = []
        
        for action in actions:
            if not getattr(action, 'success', True):
                error_msg = getattr(action, 'error_message', str(action))
                
                errors.append({
                    "type": "action_failure",
                    "description": error_msg,
                    "action_type": getattr(action, 'type', 'unknown'),
                    "timestamp": getattr(action, 'timestamp', None),
                    "recoverable": "timeout" not in error_msg.lower() and "permission" not in error_msg.lower(),
                })
        
        return errors
    
    async def _generate_insights(
        self,
        observations: List[Any],
        actions: List[Any],
        patterns: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
        metrics: Dict[str, float],
    ) -> List[Insight]:
        """Gera insights baseados na análise."""
        insights = []
        
        # Insight 1: Desempenho geral
        performance = metrics.get("performance_score", 0)
        if performance > 0.8:
            insights.append(Insight(
                category="performance",
                description="High overall performance",
                evidence=[f"Performance score: {performance:.2f}"],
                severity="low",
                confidence=performance,
                recommendation="Maintain current strategy",
            ))
        elif performance < 0.4:
            insights.append(Insight(
                category="performance",
                description="Low performance detected",
                evidence=[f"Performance score: {performance:.2f}"],
                severity="high",
                confidence=1.0 - performance,
                recommendation="Consider strategy adjustment",
            ))
        
        # Insight 2: Taxa de erro
        if errors:
            error_rate = len(errors) / len(actions) if actions else 0
            if error_rate > 0.3:
                insights.append(Insight(
                    category="error",
                    description="High error rate detected",
                    evidence=[f"{len(errors)} errors in {len(actions)} actions"],
                    severity="critical",
                    confidence=min(1.0, error_rate * 2),
                    recommendation="Review and improve error handling",
                ))
        
        # Insight 3: Padrões
        for pattern in patterns:
            if pattern.get("significance") == "high":
                insights.append(Insight(
                    category="pattern",
                    description=pattern["description"],
                    evidence=[pattern["type"]],
                    severity="medium",
                    confidence=0.7,
                    recommendation=f"Monitor this {pattern['type']}",
                ))
        
        # Insight 4: Aprendizado
        learning_rate = metrics.get("learning_rate", 0)
        if learning_rate > 0.1:
            insights.append(Insight(
                category="improvement",
                description="Positive learning trend",
                evidence=[f"Learning rate: {learning_rate:.3f}"],
                severity="low",
                confidence=min(1.0, learning_rate * 5),
                recommendation="Continue current approach",
            ))
        elif learning_rate < -0.1:
            insights.append(Insight(
                category="degradation",
                description="Performance degrading",
                evidence=[f"Learning rate: {learning_rate:.3f}"],
                severity="high",
                confidence=min(1.0, abs(learning_rate) * 5),
                recommendation="Consider strategy change",
            ))
        
        return insights
    
    def _suggest_improvements(
        self,
        insights: List[Insight],
        errors: List[Dict[str, Any]],
    ) -> List[str]:
        """Sugere melhorias baseadas nos insights."""
        suggestions = []
        
        # Agrupar insights por categoria
        by_category = {}
        for insight in insights:
            cat = insight.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(insight)
        
        # Sugestões baseadas em erros
        if errors:
            suggestions.append("Implementar retry com exponential backoff para falhas de API")
            suggestions.append("Adicionar validação de parâmetros antes de executar tools")
        
        # Sugestões baseadas em performance
        if "performance" in by_category:
            perf_insights = by_category["performance"]
            low_perf = [i for i in perf_insights if i.severity == "high"]
            if low_perf:
                suggestions.append("Revisar estratégia de planejamento - considerar abordagem mais simples")
        
        # Sugestões baseadas em padrões
        if "pattern" in by_category:
            suggestions.append("Documentar padrões identificados para reutilização futura")
        
        # Sugestões genéricas
        if not suggestions:
            suggestions.append("Continuar monitoramento de métricas")
            suggestions.append("Considerar expansão de ferramentas disponíveis")
        
        return suggestions

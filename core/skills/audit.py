"""
core/skills/audit.py — Skill Audit System

Audit loop: worker testa skill → teacher avalia → atualiza métricas.
Sistema de auditoria contínua para evolução de skills.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    Skill2,
    SkillAuditResult,
    SkillConfidence,
    SkillStatus,
)

logger = logging.getLogger(__name__)


class SkillTester:
    """Executa testes em skills."""
    
    def __init__(self, test_timeout: int = 30):
        """
        Inicializa o tester.
        
        Args:
            test_timeout: Timeout em segundos para cada teste
        """
        self.test_timeout = test_timeout
    
    def generate_test_case(self, skill: Skill2) -> Dict[str, Any]:
        """
        Gera caso de teste para uma skill.
        
        Args:
            skill: Skill a ser testada
            
        Returns:
            Caso de teste com input, contexto e critérios
        """
        # Usar when_to_use como base para cenário
        scenario = skill.when_to_use or f"Apply {skill.name}"
        
        # Criar input de teste
        test_input = f"""
Test this skill: {skill.name}

Scenario: {scenario}

Apply the skill according to its procedure:
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(skill.procedure[:5]))}

Provide the result of applying this skill to the scenario.
"""
        
        return {
            "input": test_input,
            "context": {
                "skill_name": skill.name,
                "skill_description": skill.description,
                "expected_procedure": skill.procedure,
            },
            "success_criteria": skill.verification or ["Correctly applied the skill"],
        }
    
    def execute_test(
        self,
        skill: Skill2,
        test_case: Dict[str, Any],
        llm_client,
    ) -> Dict[str, Any]:
        """
        Executa teste em uma skill.
        
        Args:
            skill: Skill sendo testada
            test_case: Caso de teste
            llm_client: Cliente LLM para execução
            
        Returns:
            Resultado do teste
        """
        start_time = time.time()
        
        try:
            # Executar skill via LLM
            if llm_client:
                response = self._call_llm(
                    llm_client,
                    test_case["input"],
                    timeout=self.test_timeout,
                )
                output = response
            else:
                output = "LLM client not available"
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "output": output,
                "execution_time_ms": execution_time,
                "error": None,
            }
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "output": "",
                "execution_time_ms": execution_time,
                "error": str(e),
            }
    
    def _call_llm(
        self,
        llm_client,
        prompt: str,
        timeout: int = 30,
    ) -> str:
        """Chama LLM com timeout."""
        # Implementação específica depende do cliente
        # Aqui é um placeholder
        return f"[Simulated LLM response for: {prompt[:50]}...]"


class SkillAuditor:
    """Orquestra o processo de auditoria de skills."""
    
    def __init__(
        self,
        worker_llm_client,
        teacher_llm_client,
        tester: Optional[SkillTester] = None,
    ):
        """
        Inicializa o auditor.
        
        Args:
            worker_llm_client: LLM para executar skills (pode ser mais fraco)
            teacher_llm_client: LLM para avaliar (deve ser mais forte)
            tester: Instância de SkillTester (opcional)
        """
        self.worker_llm = worker_llm_client
        self.teacher_llm = teacher_llm_client
        self.tester = tester or SkillTester()
    
    def audit_skill(
        self,
        skill: Skill2,
        custom_test: Optional[Dict[str, Any]] = None,
    ) -> SkillAuditResult:
        """
        Executa auditoria completa em uma skill.
        
        Args:
            skill: Skill a ser auditada
            custom_test: Caso de teste customizado (opcional)
            
        Returns:
            Resultado da auditoria
        """
        # 1. Gerar/executar teste
        if custom_test:
            test_case = custom_test
        else:
            test_case = self.tester.generate_test_case(skill)
        
        test_result = self.tester.execute_test(skill, test_case, self.worker_llm)
        
        # 2. Worker avalia próprio resultado
        worker_verdict = self._worker_evaluate(skill, test_case, test_result)
        
        # 3. Teacher avalia tudo
        teacher_verdict = self._teacher_evaluate(
            skill, test_case, test_result, worker_verdict
        )
        
        # 4. Calcular consenso
        final_verdict, score = self._calculate_consensus(
            worker_verdict, teacher_verdict, test_result
        )
        
        # 5. Criar resultado
        result = SkillAuditResult(
            skill_id=skill.id,
            test_input=test_case["input"],
            test_context=test_case["context"],
            actual_output=test_result.get("output", ""),
            execution_time_ms=test_result.get("execution_time_ms", 0),
            worker_model="worker-llm",  # Nome do modelo
            worker_verdict=worker_verdict["verdict"],
            worker_notes=worker_verdict["notes"],
            teacher_model="teacher-llm",  # Nome do modelo
            teacher_verdict=teacher_verdict["verdict"],
            teacher_notes=teacher_verdict["notes"],
            teacher_confidence=teacher_verdict.get("confidence", 0.5),
            final_verdict=final_verdict,
            score=score,
            improvement_suggestions=teacher_verdict.get("suggestions", []),
            tags_to_add=teacher_verdict.get("tags_to_add", []),
            tags_to_remove=teacher_verdict.get("tags_to_remove", []),
        )
        
        return result
    
    def _worker_evaluate(
        self,
        skill: Skill2,
        test_case: Dict[str, Any],
        test_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Worker avalia próprio resultado."""
        # Simplificação: baseado em heurísticas
        success = test_result.get("success", False)
        has_output = len(test_result.get("output", "")) > 20
        
        if success and has_output:
            return {
                "verdict": "pass",
                "notes": "Test completed successfully with output",
                "confidence": 0.8,
            }
        elif success:
            return {
                "verdict": "partial",
                "notes": "Test completed but output is minimal",
                "confidence": 0.5,
            }
        else:
            return {
                "verdict": "fail",
                "notes": f"Test failed: {test_result.get('error', 'Unknown error')}",
                "confidence": 0.9,
            }
    
    def _teacher_evaluate(
        self,
        skill: Skill2,
        test_case: Dict[str, Any],
        test_result: Dict[str, Any],
        worker_verdict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Teacher avalia resultado do worker."""
        # Simplificação: teacher revisa o veredicto do worker
        # Em implementação real, teria prompt específico para o teacher
        
        worker_score = 0.5
        if worker_verdict["verdict"] == "pass":
            worker_score = 0.9
        elif worker_verdict["verdict"] == "partial":
            worker_score = 0.6
        elif worker_verdict["verdict"] == "fail":
            worker_score = 0.2
        
        # Verificar se resultado atende critérios
        output = test_result.get("output", "")
        criteria = test_case.get("success_criteria", [])
        
        criteria_met = 0
        for criterion in criteria:
            if criterion.lower() in output.lower():
                criteria_met += 1
        
        criteria_score = criteria_met / len(criteria) if criteria else 0.5
        
        # Calcular score final
        final_score = (worker_score * 0.4) + (criteria_score * 0.6)
        
        # Determinar veredicto
        if final_score >= 0.8:
            verdict = "pass"
        elif final_score >= 0.5:
            verdict = "partial"
        else:
            verdict = "fail"
        
        return {
            "verdict": verdict,
            "notes": f"Teacher evaluation: {criteria_met}/{len(criteria)} criteria met. Worker: {worker_verdict['verdict']}",
            "confidence": final_score,
            "suggestions": [
                "Consider adding more detailed examples" if criteria_score < 0.8 else None,
                "Verify procedure steps are clear" if worker_score < 0.7 else None,
            ],
            "tags_to_add": [],
            "tags_to_remove": [],
        }
    
    def _calculate_consensus(
        self,
        worker_verdict: Dict[str, Any],
        teacher_verdict: Dict[str, Any],
        test_result: Dict[str, Any],
    ) -> Tuple[str, float]:
        """
        Calcula consenso entre worker e teacher.
        
        Returns:
            Tupla (veredicto_final, score)
        """
        worker_score = worker_verdict.get("confidence", 0.5)
        teacher_score = teacher_verdict.get("confidence", 0.5)
        
        # Teacher tem peso maior
        final_score = (worker_score * 0.3) + (teacher_score * 0.7)
        
        # Verificar sucesso técnico
        if not test_result.get("success", False):
            final_score *= 0.5  # Penalizar falha técnica
        
        # Determinar veredicto final
        if final_score >= 0.8:
            verdict = "pass"
        elif final_score >= 0.5:
            verdict = "needs_improvement"
        else:
            verdict = "fail"
        
        return verdict, final_score


class AuditScheduler:
    """Agenda auditorias de skills."""
    
    def __init__(
        self,
        auditor: SkillAuditor,
        min_interval_hours: int = 24,
        max_concurrent: int = 3,
    ):
        """
        Inicializa o scheduler.
        
        Args:
            auditor: Instância de SkillAuditor
            min_interval_hours: Intervalo mínimo entre auditorias
            max_concurrent: Máximo de auditorias simultâneas
        """
        self.auditor = auditor
        self.min_interval_hours = min_interval_hours
        self.max_concurrent = max_concurrent
        self._pending_audits: List[str] = []
        self._running_audits: Dict[str, Any] = {}
    
    def schedule_audit(self, skill_id: str, priority: int = 0) -> bool:
        """
        Agenda auditoria para uma skill.
        
        Args:
            skill_id: ID da skill
            priority: Prioridade (maior = mais prioritário)
            
        Returns:
            True se agendado com sucesso
        """
        if skill_id in self._pending_audits or skill_id in self._running_audits:
            return False
        
        self._pending_audits.append(skill_id)
        # Ordenar por prioridade (implementação simplificada)
        
        return True
    
    def process_next(self) -> Optional[SkillAuditResult]:
        """
        Processa próxima auditoria agendada.
        
        Returns:
            Resultado da auditoria ou None se não houver
        """
        if not self._pending_audits:
            return None
        
        if len(self._running_audits) >= self.max_concurrent:
            return None
        
        skill_id = self._pending_audits.pop(0)
        
        # Aqui precisaríamos buscar a skill completa
        # Por enquanto, retornar None
        # skill = get_skill(skill_id)
        # result = self.auditor.audit_skill(skill)
        
        return None
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Retorna status da fila.
        
        Returns:
            Status da fila
        """
        return {
            "pending": len(self._pending_audits),
            "running": len(self._running_audits),
            "max_concurrent": self.max_concurrent,
        }


# Re-exportar para conveniência
__all__ = [
    "SkillTester",
    "SkillAuditor",
    "AuditScheduler",
]

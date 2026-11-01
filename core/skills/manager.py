"""
core/skills/manager.py — Skill Manager 2.0

Orquestra todo o sistema de skills: criação, matching semântico, 
audit, versionamento, evolução automática.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .audit import AuditScheduler, SkillAuditor
from .extraction import SkillExtractionStorage, SkillExtractor
from .models import (
    Skill2,
    SkillAuditResult,
    SkillConfidence,
    SkillEvolutionReport,
    SkillExtraction,
    SkillSource,
    SkillStatus,
    SkillTag,
    SkillVector,
    SkillVersion,
    SemanticMatchResult,
    SemanticQuery,
)
from .semantic import SemanticMatcher

logger = logging.getLogger(__name__)


class SkillManager2:
    """
    Gerenciador principal do Skills System 2.0.
    
    Orquestra todos os componentes:
    - Criação e armazenamento de skills
    - Matching semântico
    - Extração automática
    - Auditoria
    - Versionamento
    - Evolução
    """
    
    def __init__(
        self,
        db_connection=None,
        chroma_client=None,
        llm_client_worker=None,
        llm_client_teacher=None,
        data_dir: str = "./data/skills2",
    ):
        """
        Inicializa o SkillManager2.
        
        Args:
            db_connection: Conexão com banco de dados
            chroma_client: Cliente ChromaDB para embeddings
            llm_client_worker: LLM para execução de skills
            llm_client_teacher: LLM para avaliação (mais forte)
            data_dir: Diretório para dados locais
        """
        self.db = db_connection
        self.data_dir = data_dir
        
        # Inicializar componentes
        self.semantic_matcher = SemanticMatcher(
            chroma_client=chroma_client,
        )
        
        self.skill_extractor = SkillExtractor(
            llm_client=llm_client_teacher,
        )
        
        self.extraction_storage = SkillExtractionStorage(
            db_connection=db_connection,
        )
        
        self.skill_auditor = SkillAuditor(
            worker_llm_client=llm_client_worker,
            teacher_llm_client=llm_client_teacher,
        )
        
        self.audit_scheduler = AuditScheduler(
            auditor=self.skill_auditor,
        )
        
        # Cache em memória
        self._skills_cache: Dict[str, Skill2] = {}
        
        logger.info("SkillManager2 initialized")
    
    # -----------------------------------------------------------------------
    # CRUD Básico
    # -----------------------------------------------------------------------
    
    def create_skill(
        self,
        name: str,
        description: str,
        created_by: Optional[str] = None,
        **kwargs,
    ) -> Skill2:
        """
        Cria nova skill.
        
        Args:
            name: Nome da skill
            description: Descrição
            created_by: Quem criou
            **kwargs: Campos adicionais
            
        Returns:
            Skill criada
        """
        slug = kwargs.get("slug", name.lower().replace(" ", "-"))
        
        skill = Skill2(
            slug=slug,
            name=name,
            description=description,
            created_by=created_by,
            owner=created_by,
            source=kwargs.get("source", SkillSource.MANUAL),
            status=kwargs.get("status", SkillStatus.DRAFT),
            category=kwargs.get("category", "general"),
            tags=[SkillTag(name=t) for t in kwargs.get("tags", [])],
            when_to_use=kwargs.get("when_to_use", ""),
            procedure=kwargs.get("procedure", []),
            pitfalls=kwargs.get("pitfalls", []),
            verification=kwargs.get("verification", []),
        )
        
        # Salvar
        self._save_skill(skill)
        
        # Indexar para busca semântica
        self.semantic_matcher.index_skill(skill)
        
        logger.info(f"Created skill: {skill.name} ({skill.id})")
        
        return skill
    
    def get_skill(self, skill_id: str) -> Optional[Skill2]:
        """
        Recupera skill por ID.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Skill ou None se não encontrada
        """
        # Verificar cache
        if skill_id in self._skills_cache:
            return self._skills_cache[skill_id]
        
        # Buscar no banco (implementação depende do DB)
        # Por enquanto, retornar None
        return None
    
    def update_skill(
        self,
        skill_id: str,
        updates: Dict[str, Any],
        updated_by: Optional[str] = None,
    ) -> Optional[Skill2]:
        """
        Atualiza uma skill.
        
        Args:
            skill_id: ID da skill
            updates: Campos a atualizar
            updated_by: Quem atualizou
            
        Returns:
            Skill atualizada ou None
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return None
        
        # Criar versão antes de atualizar
        skill.create_version_snapshot(
            changed_by=updated_by,
            change_summary=updates.get("change_summary", "Update"),
        )
        
        # Aplicar updates
        for field, value in updates.items():
            if field == "change_summary":
                continue
            if hasattr(skill, field):
                setattr(skill, field, value)
        
        skill.updated_at = datetime.utcnow()
        
        # Reindexar
        self.semantic_matcher.index_skill(skill)
        
        # Salvar
        self._save_skill(skill)
        
        return skill
    
    def delete_skill(self, skill_id: str, deleted_by: Optional[str] = None) -> bool:
        """
        Deleta uma skill.
        
        Args:
            skill_id: ID da skill
            deleted_by: Quem deletou
            
        Returns:
            True se deletado com sucesso
        """
        # Remover do índice semântico
        self.semantic_matcher.delete_skill_index(skill_id)
        
        # Remover do cache
        if skill_id in self._skills_cache:
            del self._skills_cache[skill_id]
        
        # Remover do banco (implementação depende do DB)
        
        return True
    
    def list_skills(
        self,
        owner: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[SkillStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Skill2]:
        """
        Lista skills com filtros.
        
        Args:
            owner: Filtrar por owner
            category: Filtrar por categoria
            status: Filtrar por status
            limit: Limite de resultados
            offset: Offset para paginação
            
        Returns:
            Lista de skills
        """
        # Filtrar do cache
        skills = list(self._skills_cache.values())
        
        if owner:
            skills = [s for s in skills if s.owner == owner]
        if category:
            skills = [s for s in skills if s.category == category]
        if status:
            skills = [s for s in skills if s.status == status]
        
        # Ordenar por updated_at (mais recentes primeiro)
        skills.sort(key=lambda s: s.updated_at or s.created_at, reverse=True)
        
        return skills[offset:offset + limit]
    
    # -----------------------------------------------------------------------
    # Busca Semântica
    # -----------------------------------------------------------------------
    
    def search_skills(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.5,
        **filters,
    ) -> List[SemanticMatchResult]:
        """
        Busca skills semanticamente.
        
        Args:
            query: Query de busca
            limit: Número máximo de resultados
            min_score: Score mínimo de similaridade
            **filters: Filtros adicionais
            
        Returns:
            Lista de matches ordenados por relevância
        """
        semantic_query = SemanticQuery(
            query=query,
            limit=limit,
            **filters,
        )
        
        results = self.semantic_matcher.search(semantic_query)
        
        # Filtrar por score mínimo
        results = [r for r in results if r.similarity_score >= min_score]
        
        return results
    
    def find_similar_skills(
        self,
        skill_id: str,
        limit: int = 5,
    ) -> List[SemanticMatchResult]:
        """
        Encontra skills similares.
        
        Args:
            skill_id: ID da skill de referência
            limit: Número máximo de resultados
            
        Returns:
            Lista de skills similares
        """
        return self.semantic_matcher.get_similar_skills(skill_id, limit)
    
    # -----------------------------------------------------------------------
    # Extração Automática
    # -----------------------------------------------------------------------
    
    def extract_skills_from_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> List[SkillExtraction]:
        """
        Extrai skills de uma conversa.
        
        Args:
            conversation_id: ID da conversa
            messages: Lista de mensagens
            
        Returns:
            Lista de skills extraídas
        """
        extractions = self.skill_extractor.extract_from_conversation(
            conversation_id, messages
        )
        
        # Salvar extrações
        for extraction in extractions:
            self.extraction_storage.save(extraction)
        
        return extractions
    
    def get_pending_extractions(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> List[SkillExtraction]:
        """
        Lista extrações pendentes de revisão.
        
        Args:
            limit: Limite de resultados
            offset: Offset para paginação
            
        Returns:
            Lista de extrações pendentes
        """
        return self.extraction_storage.list_pending(limit=limit, offset=offset)
    
    def approve_extraction(
        self,
        extraction_id: str,
        reviewed_by: str,
        modifications: Optional[Dict[str, Any]] = None,
    ) -> Optional[Skill2]:
        """
        Aprova uma extração e converte em skill.
        
        Args:
            extraction_id: ID da extração
            reviewed_by: Quem revisou
            modifications: Modificações a aplicar
            
        Returns:
            Skill criada ou None se falhou
        """
        extraction = self.extraction_storage.get(extraction_id)
        if not extraction:
            return None
        
        # Aplicar modificações
        if modifications:
            for field, value in modifications.items():
                if hasattr(extraction, field):
                    setattr(extraction, field, value)
        
        # Converter para Skill2
        skill = self.create_skill(
            name=extraction.name,
            description=extraction.description,
            created_by=reviewed_by,
            category=extraction.category,
            tags=[t.name for t in extraction.tags],
            when_to_use=extraction.when_to_use,
            procedure=extraction.procedure,
            pitfalls=extraction.pitfalls,
            verification=extraction.verification,
            source=SkillSource.EXTRACTED,
            status=SkillStatus.DRAFT,
        )
        
        # Marcar extração como aprovada
        self.extraction_storage.update_status(
            extraction_id,
            status="approved",
            reviewed_by=reviewed_by,
        )
        
        return skill
    
    def reject_extraction(
        self,
        extraction_id: str,
        reviewed_by: str,
        reason: str,
    ) -> bool:
        """
        Rejeita uma extração.
        
        Args:
            extraction_id: ID da extração
            reviewed_by: Quem revisou
            reason: Motivo da rejeição
            
        Returns:
            True se rejeitado com sucesso
        """
        return self.extraction_storage.update_status(
            extraction_id,
            status="rejected",
            reviewed_by=reviewed_by,
        )
    
    # -----------------------------------------------------------------------
    # Auditoria
    # -----------------------------------------------------------------------
    
    def schedule_audit(self, skill_id: str, priority: int = 0) -> bool:
        """
        Agenda auditoria para uma skill.
        
        Args:
            skill_id: ID da skill
            priority: Prioridade
            
        Returns:
            True se agendado com sucesso
        """
        return self.audit_scheduler.schedule_audit(skill_id, priority)
    
    def run_audit(self, skill_id: str) -> Optional[SkillAuditResult]:
        """
        Executa auditoria imediata em uma skill.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Resultado da auditoria ou None se falhou
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return None
        
        result = self.skill_auditor.audit_skill(skill)
        
        # Atualizar skill com resultado
        skill.audit_results.append(result)
        skill.last_audit = datetime.utcnow()
        
        # Atualizar confiança baseado no resultado
        self._update_confidence_from_audit(skill, result)
        
        # Salvar
        self._save_skill(skill)
        
        return result
    
    def _update_confidence_from_audit(
        self,
        skill: Skill2,
        result: SkillAuditResult,
    ) -> None:
        """Atualiza confiança da skill baseado em auditoria."""
        # Atualizar taxa de passagem
        total_audits = len(skill.audit_results)
        passed_audits = sum(
            1 for r in skill.audit_results if r.final_verdict == "pass"
        )
        
        skill.confidence.test_pass_rate = passed_audits / total_audits if total_audits > 0 else 0.0
        
        # Atualizar scores baseado no resultado mais recente
        if result.score > 0.8:
            skill.confidence.accuracy = min(1.0, skill.confidence.accuracy + 0.1)
            skill.confidence.reliability = min(1.0, skill.confidence.reliability + 0.05)
        elif result.score < 0.5:
            skill.confidence.accuracy = max(0.0, skill.confidence.accuracy - 0.1)
            skill.confidence.reliability = max(0.0, skill.confidence.reliability - 0.05)
        
        # Recalcular overall
        skill.confidence.overall = (
            skill.confidence.accuracy * 0.3 +
            skill.confidence.reliability * 0.3 +
            skill.confidence.test_pass_rate * 0.4
        )
        
        # Atualizar status baseado na confiança
        if skill.confidence.overall >= 0.8 and skill.status == SkillStatus.PENDING:
            skill.status = SkillStatus.ACTIVE
        elif skill.confidence.overall < 0.3 and skill.status == SkillStatus.ACTIVE:
            skill.status = SkillStatus.DEPRECATED
    
    # -----------------------------------------------------------------------
    # Versionamento
    # -----------------------------------------------------------------------
    
    def create_version(
        self,
        skill_id: str,
        change_summary: str,
        changed_by: Optional[str] = None,
        bump_type: str = "patch",
    ) -> Optional[SkillVersion]:
        """
        Cria nova versão de uma skill.
        
        Args:
            skill_id: ID da skill
            change_summary: Descrição das mudanças
            changed_by: Quem criou a versão
            bump_type: Tipo de bump (major, minor, patch)
            
        Returns:
            Versão criada ou None se falhou
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return None
        
        # Criar snapshot
        version = skill.create_version_snapshot(
            changed_by=changed_by,
            change_summary=change_summary,
        )
        
        # Bump versão
        skill.version = skill.bump_version(bump_type)
        skill.parent_version_id = version.id
        
        # Salvar
        self._save_skill(skill)
        
        logger.info(f"Created version {skill.version} for skill {skill.name}")
        
        return version
    
    def rollback_to_version(
        self,
        skill_id: str,
        version_id: str,
    ) -> Optional[Skill2]:
        """
        Faz rollback para uma versão anterior.
        
        Args:
            skill_id: ID da skill
            version_id: ID da versão
            
        Returns:
            Skill restaurada ou None se falhou
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return None
        
        # Encontrar versão
        version = None
        for v in skill.versions:
            if v.id == version_id:
                version = v
                break
        
        if not version:
            return None
        
        # Criar backup da versão atual antes do rollback
        skill.create_version_snapshot(
            changed_by="system",
            change_summary="Auto-backup before rollback",
        )
        
        # Restaurar dados da versão
        restored_data = version.skill_data
        
        # Criar nova skill com dados restaurados
        restored_skill = Skill2(**restored_data)
        restored_skill.id = skill.id  # Manter mesmo ID
        restored_skill.version = skill.bump_version("patch")
        restored_skill.parent_version_id = version.id
        restored_skill.updated_at = datetime.utcnow()
        
        # Salvar
        self._save_skill(restored_skill)
        
        # Reindexar
        self.semantic_matcher.index_skill(restored_skill)
        
        logger.info(f"Rolled back skill {restored_skill.name} to version {version.version}")
        
        return restored_skill
    
    def get_version_history(self, skill_id: str) -> List[SkillVersion]:
        """
        Retorna histórico de versões de uma skill.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Lista de versões
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return []
        
        return sorted(
            skill.versions,
            key=lambda v: v.created_at,
            reverse=True,
        )
    
    # -----------------------------------------------------------------------
    # Busca e Matching
    # -----------------------------------------------------------------------
    
    def find_skills(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.5,
        **filters,
    ) -> List[SemanticMatchResult]:
        """
        Busca skills semanticamente.
        
        Args:
            query: Query de busca
            limit: Número máximo de resultados
            min_score: Score mínimo
            **filters: Filtros adicionais
            
        Returns:
            Lista de matches
        """
        return self.search_skills(query, limit, min_score, **filters)
    
    def get_recommendations(
        self,
        context: str,
        limit: int = 5,
    ) -> List[SemanticMatchResult]:
        """
        Recomenda skills baseado no contexto atual.
        
        Args:
            context: Contexto atual (últimas mensagens, etc)
            limit: Número máximo de recomendações
            
        Returns:
            Lista de recomendações
        """
        return self.search_skills(
            query=context,
            limit=limit,
            min_score=0.4,  # Score mais baixo para recomendações
            status=SkillStatus.ACTIVE,  # Só skills ativas
        )
    
    # -----------------------------------------------------------------------
    # Extração Automática
    # -----------------------------------------------------------------------
    
    def extract_skills(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> List[SkillExtraction]:
        """
        Extrai skills de uma conversa.
        
        Args:
            conversation_id: ID da conversa
            messages: Lista de mensagens
            
        Returns:
            Lista de extrações
        """
        return self.extract_skills_from_conversation(conversation_id, messages)
    
    def get_pending_extractions(
        self,
        limit: int = 10,
    ) -> List[SkillExtraction]:
        """
        Lista extrações pendentes.
        
        Args:
            limit: Limite de resultados
            
        Returns:
            Lista de extrações pendentes
        """
        return self.extraction_storage.list_pending(limit=limit)
    
    def approve_extraction(
        self,
        extraction_id: str,
        reviewed_by: str,
    ) -> Optional[Skill2]:
        """
        Aprova extração e converte em skill.
        
        Args:
            extraction_id: ID da extração
            reviewed_by: Quem revisou
            
        Returns:
            Skill criada ou None
        """
        return self.extraction_storage.convert_to_skill(extraction_id, reviewed_by)
    
    def reject_extraction(
        self,
        extraction_id: str,
        reviewed_by: str,
        reason: str,
    ) -> bool:
        """
        Rejeita extração.
        
        Args:
            extraction_id: ID da extração
            reviewed_by: Quem revisou
            reason: Motivo
            
        Returns:
            True se rejeitado com sucesso
        """
        return self.extraction_storage.update_status(
            extraction_id,
            status="rejected",
            reviewed_by=reviewed_by,
        )
    
    # -----------------------------------------------------------------------
    # Auditoria
    # -----------------------------------------------------------------------
    
    def schedule_audit(self, skill_id: str, priority: int = 0) -> bool:
        """
        Agenda auditoria para uma skill.
        
        Args:
            skill_id: ID da skill
            priority: Prioridade
            
        Returns:
            True se agendado com sucesso
        """
        return self.audit_scheduler.schedule_audit(skill_id, priority)
    
    def run_audit(self, skill_id: str) -> Optional[SkillAuditResult]:
        """
        Executa auditoria imediata.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Resultado da auditoria ou None
        """
        return self.run_audit(skill_id)
    
    def get_audit_history(self, skill_id: str) -> List[SkillAuditResult]:
        """
        Retorna histórico de auditorias de uma skill.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Lista de resultados de auditoria
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return []
        
        return sorted(
            skill.audit_results,
            key=lambda r: r.created_at,
            reverse=True,
        )
    
    # -----------------------------------------------------------------------
    # Evolução
    # -----------------------------------------------------------------------
    
    def generate_evolution_report(self, skill_id: str) -> Optional[SkillEvolutionReport]:
        """
        Gera relatório de evolução de uma skill.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Relatório de evolução ou None
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return None
        
        # Histórico de uso
        usage_history = []
        for version in skill.versions:
            usage_history.append({
                "version": version.version,
                "timestamp": version.created_at.isoformat(),
            })
        
        # Histórico de confiança
        confidence_history = []
        for audit in skill.audit_results:
            confidence_history.append({
                "timestamp": audit.created_at.isoformat(),
                "score": audit.score,
                "verdict": audit.final_verdict,
            })
        
        # Análise de pontos fortes e fracos
        strengths = []
        improvement_areas = []
        
        if skill.confidence.overall >= 0.8:
            strengths.append("High overall confidence")
        else:
            improvement_areas.append("Overall confidence could be improved")
        
        if skill.confidence.test_pass_rate >= 0.8:
            strengths.append("Consistent test performance")
        else:
            improvement_areas.append("Test pass rate needs improvement")
        
        if len(skill.versions) > 1:
            strengths.append("Actively maintained with version history")
        
        # Sugestões
        suggestions = []
        if skill.confidence.overall < 0.6:
            suggestions.append("Consider running more audits to improve confidence")
        if not skill.verification:
            suggestions.append("Add verification steps to improve reliability")
        if len(skill.examples) < 2:
            suggestions.append("Add more usage examples")
        
        return SkillEvolutionReport(
            skill_id=skill.id,
            skill_name=skill.name,
            current_version=skill.version,
            usage_over_time=usage_history,
            confidence_history=confidence_history,
            audit_results=skill.audit_results[-10:],  # Últimas 10
            improvement_areas=improvement_areas,
            strengths=strengths,
            suggestions=suggestions,
        )
    
    def suggest_improvements(self, skill_id: str) -> List[str]:
        """
        Sugere melhorias para uma skill.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Lista de sugestões
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return []
        
        suggestions = []
        
        # Verificar campos incompletos
        if not skill.when_to_use:
            suggestions.append("Add 'when_to_use' to clarify when this skill applies")
        
        if len(skill.procedure) < 3:
            suggestions.append("Expand the procedure with more detailed steps")
        
        if not skill.pitfalls:
            suggestions.append("Add common pitfalls or mistakes to avoid")
        
        if not skill.verification:
            suggestions.append("Add verification steps to ensure correct application")
        
        if len(skill.tags) < 2:
            suggestions.append("Add more tags to improve discoverability")
        
        if not skill.examples:
            suggestions.append("Add usage examples to clarify how to apply the skill")
        
        # Verificar qualidade baseada em auditorias
        if skill.audit_results:
            latest_audit = max(skill.audit_results, key=lambda a: a.created_at)
            if latest_audit.score < 0.6:
                suggestions.append("Recent audit shows low performance - review and improve the skill")
            if latest_audit.improvement_suggestions:
                suggestions.extend(latest_audit.improvement_suggestions[:3])
        
        return suggestions
    
    # -----------------------------------------------------------------------
    # Forking
    # -----------------------------------------------------------------------
    
    def fork_skill(
        self,
        skill_id: str,
        new_name: str,
        forked_by: Optional[str] = None,
        modifications: Optional[Dict[str, Any]] = None,
    ) -> Optional[Skill2]:
        """
        Cria um fork de uma skill.
        
        Args:
            skill_id: ID da skill original
            new_name: Nome para o fork
            forked_by: Quem criou o fork
            modifications: Modificações a aplicar
            
        Returns:
            Skill fork criada ou None
        """
        original = self.get_skill(skill_id)
        if not original:
            return None
        
        # Criar cópia
        fork_data = original.model_dump()
        fork_data["id"] = None  # Gerar novo ID
        fork_data["slug"] = new_name.lower().replace(" ", "-")
        fork_data["name"] = new_name
        fork_data["is_forked"] = True
        fork_data["forked_from"] = original.id
        fork_data["created_by"] = forked_by
        fork_data["owner"] = forked_by
        fork_data["source"] = SkillSource.FORKED
        fork_data["versions"] = []
        fork_data["audit_results"] = []
        fork_data["confidence"] = SkillConfidence()
        fork_data["created_at"] = datetime.utcnow()
        fork_data["updated_at"] = datetime.utcnow()
        
        # Aplicar modificações
        if modifications:
            for field, value in modifications.items():
                if field in fork_data:
                    fork_data[field] = value
        
        # Criar skill
        fork = Skill2(**fork_data)
        
        # Salvar
        self._save_skill(fork)
        
        # Indexar
        self.semantic_matcher.index_skill(fork)
        
        logger.info(f"Created fork {fork.name} from {original.name}")
        
        return fork
    
    # -----------------------------------------------------------------------
    # Relatórios
    # -----------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do sistema de skills.
        
        Returns:
            Dicionário com estatísticas
        """
        skills = list(self._skills_cache.values())
        
        total = len(skills)
        active = sum(1 for s in skills if s.status == SkillStatus.ACTIVE)
        draft = sum(1 for s in skills if s.status == SkillStatus.DRAFT)
        pending = sum(1 for s in skills if s.status == SkillStatus.PENDING)
        deprecated = sum(1 for s in skills if s.status == SkillStatus.DEPRECATED)
        
        by_source = {}
        for s in skills:
            source = s.source.value
            by_source[source] = by_source.get(source, 0) + 1
        
        avg_confidence = 0.0
        if skills:
            avg_confidence = sum(s.confidence.overall for s in skills) / len(skills)
        
        return {
            "total": total,
            "by_status": {
                "active": active,
                "draft": draft,
                "pending": pending,
                "deprecated": deprecated,
            },
            "by_source": by_source,
            "average_confidence": round(avg_confidence, 3),
            "indexed_in_semantic_matcher": len(self.semantic_matcher._skills_by_id),
        }
    
    # -----------------------------------------------------------------------
    # Métodos Privados
    # -----------------------------------------------------------------------
    
    def _save_skill(self, skill: Skill2) -> bool:
        """
        Salva uma skill no banco de dados.
        
        Args:
            skill: Skill a salvar
            
        Returns:
            True se salvo com sucesso
        """
        # Atualizar cache
        self._skills_cache[skill.id] = skill
        
        # Salvar no banco (implementação depende do DB)
        if self.db:
            # Implementar persistência no banco
            pass
        
        return True
    
    def _load_skill(self, skill_id: str) -> Optional[Skill2]:
        """
        Carrega uma skill do banco de dados.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            Skill carregada ou None
        """
        # Implementar carregamento do banco
        return None
    
    def _generate_slug(self, name: str) -> str:
        """Gera slug a partir do nome."""
        import re
        slug = name.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug[:100]


# Re-exportar para conveniência
__all__ = [
    "SkillManager2",
]

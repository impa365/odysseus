"""
core/skills/api.py — Skills 2.0 API

Rotas FastAPI para o Skills System 2.0.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .manager import SkillManager2
from .models import (
    Skill2,
    SkillAuditResult,
    SkillEvolutionReport,
    SkillExtraction,
    SkillSource,
    SkillStatus,
    SkillVersion,
    SemanticMatchResult,
)


# ============================================================================
# Schemas Pydantic para API
# ============================================================================

class SkillCreateRequest(BaseModel):
    """Request para criar skill."""
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=1000)
    category: str = Field(default="general", max_length=50)
    tags: List[str] = Field(default_factory=list)
    when_to_use: str = Field(default="", max_length=2000)
    procedure: List[str] = Field(default_factory=list)
    pitfalls: List[str] = Field(default_factory=list)
    verification: List[str] = Field(default_factory=list)


class SkillUpdateRequest(BaseModel):
    """Request para atualizar skill."""
    model_config = ConfigDict(extra="forbid")
    
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=1000)
    category: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = None
    when_to_use: Optional[str] = Field(None, max_length=2000)
    procedure: Optional[List[str]] = None
    pitfalls: Optional[List[str]] = None
    verification: Optional[List[str]] = None
    status: Optional[SkillStatus] = None
    change_summary: str = Field(default="Update")


class SkillSearchRequest(BaseModel):
    """Request para busca semântica."""
    model_config = ConfigDict(extra="forbid")
    
    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    category: Optional[str] = None
    status: Optional[SkillStatus] = None
    owner: Optional[str] = None


class SkillForkRequest(BaseModel):
    """Request para fork de skill."""
    model_config = ConfigDict(extra="forbid")
    
    new_name: str = Field(..., min_length=1, max_length=200)
    modifications: Dict[str, Any] = Field(default_factory=dict)


class ExtractionReviewRequest(BaseModel):
    """Request para revisão de extração."""
    model_config = ConfigDict(extra="forbid")
    
    action: str = Field(..., pattern="^(approve|reject)$")
    modifications: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


# ============================================================================
# Rotas
# ============================================================================

router = APIRouter(prefix="/api/skills2", tags=["skills2"])

# Dependência para obter SkillManager2
def get_skill_manager() -> SkillManager2:
    """Retorna instância do SkillManager2."""
    # Implementar injeção de dependência real
    # Por enquanto, retorna None e rotas devem tratar
    raise NotImplementedError("SkillManager2 dependency not configured")


@router.post("/search", response_model=List[Dict[str, Any]])
async def search_skills(
    request: SkillSearchRequest,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> List[Dict[str, Any]]:
    """Busca skills semanticamente."""
    results = manager.search_skills(
        query=request.query,
        limit=request.limit,
        min_score=request.min_score,
        category=request.category,
        status=request.status,
        owner=request.owner,
    )
    
    return [
        {
            "skill": r.skill.model_dump(),
            "similarity_score": r.similarity_score,
            "matched_fields": r.matched_fields,
            "explanation": r.explanation,
        }
        for r in results
    ]


@router.get("/recommendations", response_model=List[Dict[str, Any]])
async def get_recommendations(
    context: str = Query(..., min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    manager: SkillManager2 = Depends(get_skill_manager),
) -> List[Dict[str, Any]]:
    """Obtém recomendações de skills baseado no contexto."""
    results = manager.get_recommendations(context, limit)
    
    return [
        {
            "skill": r.skill.model_dump(),
            "similarity_score": r.similarity_score,
        }
        for r in results
    ]


@router.post("", response_model=Dict[str, Any])
async def create_skill(
    request: SkillCreateRequest,
    manager: SkillManager2 = Depends(get_skill_manager),
    current_user: str = Depends(lambda: "user"),  # Implementar auth real
) -> Dict[str, Any]:
    """Cria nova skill."""
    skill = manager.create_skill(
        name=request.name,
        description=request.description,
        created_by=current_user,
        category=request.category,
        tags=request.tags,
        when_to_use=request.when_to_use,
        procedure=request.procedure,
        pitfalls=request.pitfalls,
        verification=request.verification,
    )
    
    return skill.model_dump()


@router.get("/{skill_id}", response_model=Dict[str, Any])
async def get_skill(
    skill_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> Dict[str, Any]:
    """Obtém detalhes de uma skill."""
    skill = manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return skill.model_dump()


@router.put("/{skill_id}", response_model=Dict[str, Any])
async def update_skill(
    skill_id: str,
    request: SkillUpdateRequest,
    manager: SkillManager2 = Depends(get_skill_manager),
    current_user: str = Depends(lambda: "user"),  # Implementar auth real
) -> Dict[str, Any]:
    """Atualiza uma skill."""
    updates = request.model_dump(exclude_unset=True)
    
    skill = manager.update_skill(
        skill_id=skill_id,
        updates=updates,
        updated_by=current_user,
    )
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return skill.model_dump()


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
    current_user: str = Depends(lambda: "user"),  # Implementar auth real
) -> Dict[str, str]:
    """Deleta uma skill."""
    success = manager.delete_skill(skill_id, deleted_by=current_user)
    
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {"message": "Skill deleted successfully"}


@router.post("/{skill_id}/fork", response_model=Dict[str, Any])
async def fork_skill(
    skill_id: str,
    request: SkillForkRequest,
    manager: SkillManager2 = Depends(get_skill_manager),
    current_user: str = Depends(lambda: "user"),  # Implementar auth real
) -> Dict[str, Any]:
    """Cria fork de uma skill."""
    fork = manager.fork_skill(
        skill_id=skill_id,
        new_name=request.new_name,
        forked_by=current_user,
        modifications=request.modifications,
    )
    
    if not fork:
        raise HTTPException(status_code=404, detail="Original skill not found")
    
    return fork.model_dump()


@router.get("/{skill_id}/versions", response_model=List[Dict[str, Any]])
async def get_versions(
    skill_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> List[Dict[str, Any]]:
    """Obtém histórico de versões de uma skill."""
    versions = manager.get_version_history(skill_id)
    
    return [v.model_dump() for v in versions]


@router.post("/{skill_id}/rollback")
async def rollback_version(
    skill_id: str,
    version_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> Dict[str, Any]:
    """Faz rollback para uma versão anterior."""
    skill = manager.rollback_to_version(skill_id, version_id)
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill or version not found")
    
    return skill.model_dump()


@router.post("/{skill_id}/audit", response_model=Dict[str, Any])
async def run_audit(
    skill_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> Dict[str, Any]:
    """Executa auditoria em uma skill."""
    result = manager.run_audit(skill_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return result.model_dump()


@router.get("/{skill_id}/audits", response_model=List[Dict[str, Any]])
async def get_audits(
    skill_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> List[Dict[str, Any]]:
    """Obtém histórico de auditorias de uma skill."""
    audits = manager.get_audit_history(skill_id)
    
    return [a.model_dump() for a in audits]


@router.get("/{skill_id}/evolution", response_model=Dict[str, Any])
async def get_evolution_report(
    skill_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> Dict[str, Any]:
    """Obtém relatório de evolução de uma skill."""
    report = manager.generate_evolution_report(skill_id)
    
    if not report:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return report.model_dump()


@router.get("/{skill_id}/suggestions", response_model=List[str])
async def get_improvement_suggestions(
    skill_id: str,
    manager: SkillManager2 = Depends(get_skill_manager),
) -> List[str]:
    """Obtém sugestões de melhoria para uma skill."""
    suggestions = manager.suggest_improvements(skill_id)
    
    return suggestions


# ============================================================================
# Extractions Endpoints
# ============================================================================

@router.get("/extractions/pending", response_model=List[Dict[str, Any]])
async def list_pending_extractions(
    limit: int = Query(default=10, ge=1, le=50),
    manager: SkillManager2 = Depends(get_skill_manager),
) -> List[Dict[str, Any]]:
    """Lista extrações pendentes de revisão."""
    extractions = manager.get_pending_extractions(limit=limit)
    
    return [e.model_dump() for e in extractions]


@router.post("/extractions/{extraction_id}/review")
async def review_extraction(
    extraction_id: str,
    request: ExtractionReviewRequest,
    manager: SkillManager2 = Depends(get_skill_manager),
    current_user: str = Depends(lambda: "user"),  # Implementar auth real
) -> Dict[str, Any]:
    """Revisa uma extração (aprova ou rejeita)."""
    if request.action == "approve":
        skill = manager.approve_extraction(
            extraction_id=extraction_id,
            reviewed_by=current_user,
        )
        if not skill:
            raise HTTPException(status_code=404, detail="Extraction not found")
        
        return {
            "message": "Extraction approved and converted to skill",
            "skill": skill.model_dump(),
        }
    
    else:  # reject
        success = manager.reject_extraction(
            extraction_id=extraction_id,
            reviewed_by=current_user,
            reason=request.reason or "Rejected by reviewer",
        )
        if not success:
            raise HTTPException(status_code=404, detail="Extraction not found")
        
        return {"message": "Extraction rejected"}


# ============================================================================
# Stats Endpoint
# ============================================================================

@router.get("/stats", response_model=Dict[str, Any])
async def get_stats(
    manager: SkillManager2 = Depends(get_skill_manager),
) -> Dict[str, Any]:
    """Obtém estatísticas do sistema de skills."""
    return manager.get_stats()


# Re-exportar router
__all__ = [
    "router",
    "SkillCreateRequest",
    "SkillUpdateRequest",
    "SkillSearchRequest",
    "SkillForkRequest",
    "ExtractionReviewRequest",
]

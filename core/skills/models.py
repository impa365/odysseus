"""
core/skills/models.py — Skill System 2.0 Models

Pydantic models para o sistema de skills semântico e auto-evolutivo.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillStatus(str, enum.Enum):
    """Status de uma skill no ciclo de vida."""
    DRAFT = "draft"           # Criada, não testada
    PENDING = "pending"       # Aguardando auditoria
    ACTIVE = "active"         # Aprovada e em uso
    DEPRECATED = "deprecated" # Marcada para remoção
    ARCHIVED = "archived"     # Inativa, mantida para histórico


class SkillSource(str, enum.Enum):
    """Origem da skill."""
    MANUAL = "manual"         # Criada manualmente pelo usuário
    EXTRACTED = "extracted"   # Extraída automaticamente de conversa
    IMPORTED = "imported"     # Importada de URL/arquivo
    FORKED = "forked"         # Derivada de outra skill
    SYSTEM = "system"         # Embutida no sistema


class SkillConfidence(BaseModel):
    """Métricas de confiança em uma skill."""
    model_config = ConfigDict(frozen=False)
    
    overall: float = Field(default=0.5, ge=0.0, le=1.0)
    accuracy: float = Field(default=0.5, ge=0.0, le=1.0)
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    test_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    
    uses_count: int = Field(default=0, ge=0)
    successful_uses: int = Field(default=0, ge=0)
    failed_uses: int = Field(default=0, ge=0)


class SkillTag(BaseModel):
    """Tag semântica para categorização."""
    model_config = ConfigDict(frozen=True)
    
    name: str = Field(..., min_length=1, max_length=50)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="manual")  # manual, inferred, extracted


class SkillVector(BaseModel):
    """Representação vetorial da skill para matching semântico."""
    model_config = ConfigDict(frozen=False)
    
    embedding: List[float] = Field(..., min_length=1)
    model: str = Field(default="fastembed")  # nome do modelo usado
    dimensions: int = Field(..., ge=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator('dimensions')
    @classmethod
    def validate_dimensions_match(cls, v: int, info) -> int:
        values = info.data
        if 'embedding' in values and len(values['embedding']) != v:
            raise ValueError('dimensions must match embedding length')
        return v


class SkillVersion(BaseModel):
    """Histórico de versão de uma skill."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+(-[\w.]+)?$')
    skill_data: Dict[str, Any]  # Snapshot da skill nesta versão
    change_summary: str = Field(..., max_length=500)
    changed_by: Optional[str] = None
    parent_version: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SkillAuditResult(BaseModel):
    """Resultado de uma auditoria de skill."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str
    
    # Test execution
    test_input: str
    test_context: Dict[str, Any]
    actual_output: str
    execution_time_ms: int
    
    # Worker evaluation
    worker_model: str
    worker_verdict: str  # pass, fail, partial
    worker_notes: str
    
    # Teacher evaluation
    teacher_model: str
    teacher_verdict: str  # pass, fail, partial
    teacher_notes: str
    teacher_confidence: float = Field(ge=0.0, le=1.0)
    
    # Consensus
    final_verdict: str  # pass, fail, needs_improvement
    score: float = Field(ge=0.0, le=1.0)
    
    # Suggestions
    improvement_suggestions: List[str] = Field(default_factory=list)
    tags_to_add: List[str] = Field(default_factory=list)
    tags_to_remove: List[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SkillExtraction(BaseModel):
    """Uma skill extraída automaticamente de uma conversa."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_conversation_id: str
    source_messages: List[str]  # IDs ou conteúdo das mensagens fonte
    
    # Skill proposta
    name: str
    description: str
    category: str = "general"
    tags: List[SkillTag] = Field(default_factory=list)
    when_to_use: str
    procedure: List[str]
    pitfalls: List[str] = Field(default_factory=list)
    verification: List[str] = Field(default_factory=list)
    
    # Metadados
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: Optional[str] = None
    review_status: str = "pending"  # pending, approved, rejected, modified


class Skill2(BaseModel):
    """
    Modelo principal de Skill para o Skills System 2.0.
    
    Versão semântica e evolutiva da skill, com suporte a:
    - Matching semântico via embeddings
    - Histórico de versões
    - Auditoria contínua
    - Extração automática
    """
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    slug: str = Field(..., min_length=1, max_length=100)
    
    # Identidade e conteúdo
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=1000)
    category: str = Field(default="general", max_length=50)
    
    # Categorização
    tags: List[SkillTag] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    
    # Uso
    when_to_use: str = Field(default="", max_length=2000)
    procedure: List[str] = Field(default_factory=list)
    pitfalls: List[str] = Field(default_factory=list)
    verification: List[str] = Field(default_factory=list)
    examples: List[Dict[str, str]] = Field(default_factory=list)
    
    # Metadados de controle
    status: SkillStatus = Field(default=SkillStatus.DRAFT)
    source: SkillSource = Field(default=SkillSource.MANUAL)
    version: str = Field(default="1.0.0", pattern=r'^\d+\.\d+\.\d+(-[\w.]+)?$')
    
    # Ownership
    owner: Optional[str] = None
    created_by: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    
    # Métricas
    confidence: SkillConfidence = Field(default_factory=SkillConfidence)
    
    # Representação semântica
    vector: Optional[SkillVector] = None
    
    # Histórico
    versions: List[SkillVersion] = Field(default_factory=list)
    parent_version_id: Optional[str] = None
    
    # Auditoria
    audit_results: List[SkillAuditResult] = Field(default_factory=list)
    last_audit: Optional[datetime] = None
    
    # Flags
    is_template: bool = Field(default=False)
    is_forked: bool = Field(default=False)
    forked_from: Optional[str] = None
    
    def to_embedding_text(self) -> str:
        """Gera texto para embedding semântico."""
        parts = [
            f"Name: {self.name}",
            f"Description: {self.description}",
            f"Category: {self.category}",
            f"Tags: {', '.join(t.name for t in self.tags)}",
            f"Keywords: {', '.join(self.keywords)}",
            f"When to use: {self.when_to_use}",
            f"Procedure: {' '.join(self.procedure)}",
        ]
        return "\n".join(parts)
    
    def bump_version(self, change_type: str = "patch") -> str:
        """Incrementa versão semântica."""
        parts = self.version.split("-")[0].split(".")
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        
        if change_type == "major":
            major += 1
            minor = patch = 0
        elif change_type == "minor":
            minor += 1
            patch = 0
        else:  # patch
            patch += 1
        
        return f"{major}.{minor}.{patch}"
    
    def record_usage(self, success: bool = True) -> None:
        """Registra uso da skill."""
        self.confidence.uses_count += 1
        self.last_used = datetime.utcnow()
        
        if success:
            self.confidence.successful_uses += 1
        else:
            self.confidence.failed_uses += 1
        
        # Recalcular taxas
        if self.confidence.uses_count > 0:
            self.confidence.test_pass_rate = (
                self.confidence.successful_uses / self.confidence.uses_count
            )
            self.confidence.overall = 0.3 * self.confidence.accuracy + \
                                      0.3 * self.confidence.reliability + \
                                      0.4 * self.confidence.test_pass_rate
    
    def create_version_snapshot(self, changed_by: Optional[str] = None, 
                                 change_summary: str = "") -> SkillVersion:
        """Cria snapshot da versão atual."""
        version = SkillVersion(
            version=self.version,
            skill_data=self.model_dump(),
            change_summary=change_summary,
            changed_by=changed_by,
            parent_version=self.parent_version_id
        )
        self.versions.append(version)
        return version


class SemanticQuery(BaseModel):
    """Query para busca semântica de skills."""
    model_config = ConfigDict(extra="forbid")
    
    query: str = Field(..., min_length=1, max_length=2000)
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    status: Optional[SkillStatus] = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    owner: Optional[str] = None
    include_deprecated: bool = False
    limit: int = Field(default=10, ge=1, le=100)


class SemanticMatchResult(BaseModel):
    """Resultado de matching semântico."""
    model_config = ConfigDict(frozen=False)
    
    skill: Skill2
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    matched_fields: List[str] = Field(default_factory=list)
    explanation: Optional[str] = None


class SkillEvolutionReport(BaseModel):
    """Relatório de evolução de uma skill."""
    model_config = ConfigDict(frozen=False)
    
    skill_id: str
    skill_name: str
    current_version: str
    
    # Métricas ao longo do tempo
    usage_over_time: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_history: List[Dict[str, Any]] = Field(default_factory=list)
    audit_results: List[SkillAuditResult] = Field(default_factory=list)
    
    # Análise
    improvement_areas: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# Re-exportar tipos úteis para importação direta
__all__ = [
    # Enums
    "SkillStatus",
    "SkillSource", 
    # Models principais
    "Skill2",
    "SkillTag",
    "SkillVector",
    "SkillConfidence",
    "SkillVersion",
    "SkillAuditResult",
    "SkillExtraction",
    # Query/Match
    "SemanticQuery",
    "SemanticMatchResult",
    # Reports
    "SkillEvolutionReport",
]

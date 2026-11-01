"""
core/skills/__init__.py — Skill System 2.0

Sistema de skills semântico e auto-evolutivo.
"""

# Models
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

# Core Components
from .semantic import SemanticMatcher
from .extraction import (
    ConversationAnalyzer,
    SkillExtractor,
    SkillExtractionStorage,
)
from .audit import (
    SkillTester,
    SkillAuditor,
    AuditScheduler,
)
from .manager import SkillManager2

__version__ = "2.0.0"

__all__ = [
    # Version
    "__version__",
    
    # Models
    "Skill2",
    "SkillAuditResult",
    "SkillConfidence",
    "SkillEvolutionReport",
    "SkillExtraction",
    "SkillSource",
    "SkillStatus",
    "SkillTag",
    "SkillVector",
    "SkillVersion",
    "SemanticMatchResult",
    "SemanticQuery",
    
    # Core Components
    "SemanticMatcher",
    "ConversationAnalyzer",
    "SkillExtractor",
    "SkillExtractionStorage",
    "SkillTester",
    "SkillAuditor",
    "AuditScheduler",
    "SkillManager2",
]

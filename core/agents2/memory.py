"""
core/agents2/memory.py — Agent Memory

Sistema de memória para agentes:
- Episódica: eventos específicos (o que aconteceu)
- Semântica: fatos e conhecimentos (o que é verdade)
- Procedural: como fazer coisas (skills)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """Evento episódico (algo que aconteceu)."""
    id: str = field(default_factory=lambda: f"ep_{int(time.time()*1000)}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Conteúdo
    observation: str = ""  # O que foi percebido
    action: str = ""       # O que foi feito
    result: str = ""       # O que aconteceu
    
    # Contexto
    context: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    
    # Embedding para busca semântica
    embedding: Optional[List[float]] = None
    
    # Metadados
    importance: float = 1.0  # 0-10, quão importante é lembrar
    emotional_valence: float = 0.0  # -1 (negativo) a +1 (positivo)
    
    def to_text(self) -> str:
        """Converte para texto para embedding."""
        return f"""
Observation: {self.observation}
Action: {self.action}
Result: {self.result}
Context: {json.dumps(self.context)}
""".strip()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "observation": self.observation,
            "action": self.action,
            "result": self.result,
            "context": self.context,
            "tags": list(self.tags),
            "importance": self.importance,
            "emotional_valence": self.emotional_valence,
        }


@dataclass
class SemanticFact:
    """Fato semântico (conhecimento)."""
    id: str = field(default_factory=lambda: f"fact_{int(time.time()*1000)}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Conteúdo
    subject: str = ""      # Sobre quem/what
    predicate: str = ""    # Relação (é, tem, faz, etc.)
    object: str = ""       # Valor
    
    # Formas alternativas
    natural_language: str = ""  # "Gatos são mamíferos"
    
    # Metadados
    confidence: float = 1.0  # 0-1, quão certo é
    source: str = ""       # De onde veio (observation, inference, user, etc.)
    expiration: Optional[datetime] = None  # Quando expira
    
    # Embedding
    embedding: Optional[List[float]] = None
    
    # Relacionamentos
    related_facts: Set[str] = field(default_factory=set)
    
    def to_text(self) -> str:
        """Converte para texto."""
        if self.natural_language:
            return self.natural_language
        return f"{self.subject} {self.predicate} {self.object}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "natural_language": self.natural_language,
            "confidence": self.confidence,
            "source": self.source,
            "expiration": self.expiration.isoformat() if self.expiration else None,
        }


class EpisodicMemory:
    """
    Memória episódica - eventos específicos.
    
    Características:
    - Esparsa (esquecemos a maioria)
    - Associativa (contexto importa)
    - Temporal (quando importa)
    """
    
    def __init__(
        self,
        max_episodes: int = 1000,
        embedding_dim: int = 384,
        use_semantic_search: bool = True,
    ):
        self.max_episodes = max_episodes
        self.embedding_dim = embedding_dim
        self.use_semantic_search = use_semantic_search
        
        self.episodes: Dict[str, Episode] = {}
        self.index_by_tag: Dict[str, Set[str]] = {}
        self.index_by_time: List[Tuple[datetime, str]] = []
        
        # Para busca semântica (simplificado - em produção usar ChromaDB)
        self.embeddings: Dict[str, np.ndarray] = {}
    
    def store(
        self,
        observation: str,
        action: str = "",
        result: str = "",
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Set[str]] = None,
        importance: float = 1.0,
    ) -> Episode:
        """
        Armazena episódio.
        
        Args:
            observation: O que foi percebido
            action: O que foi feito
            result: O que aconteceu
            context: Contexto adicional
            tags: Tags para indexação
            importance: Importância (0-10)
            
        Returns:
            Episódio criado
        """
        # Verificar se deve consolidar (episódios muito similares)
        # TODO: Implementar consolidação
        
        # Criar episódio
        episode = Episode(
            observation=observation,
            action=action,
            result=result,
            context=context or {},
            tags=tags or set(),
            importance=importance,
        )
        
        # Calcular embedding se necessário
        if self.use_semantic_search:
            episode.embedding = self._compute_embedding(episode.to_text())
            self.embeddings[episode.id] = np.array(episode.embedding)
        
        # Armazenar
        self.episodes[episode.id] = episode
        
        # Indexar
        self._index_episode(episode)
        
        # Verificar limite
        self._enforce_limit()
        
        logger.debug(f"Stored episode {episode.id}")
        return episode
    
    def retrieve(
        self,
        query: str,
        n: int = 5,
        tags: Optional[Set[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
    ) -> List[Episode]:
        """
        Recupera episódios relevantes.
        
        Args:
            query: Consulta em linguagem natural
            n: Número de resultados
            tags: Filtrar por tags
            time_range: Filtrar por tempo
            
        Returns:
            Lista de episódios relevantes
        """
        candidates = list(self.episodes.values())
        
        # Filtrar por tags
        if tags:
            candidates = [e for e in candidates if e.tags & tags]
        
        # Filtrar por tempo
        if time_range:
            start, end = time_range
            candidates = [
                e for e in candidates
                if start <= e.timestamp <= end
            ]
        
        # Ranquear
        if self.use_semantic_search and query:
            # Busca semântica
            scored = []
            query_embedding = self._compute_embedding(query)
            
            for episode in candidates:
                if episode.id in self.embeddings:
                    score = self._cosine_similarity(
                        query_embedding,
                        self.embeddings[episode.id].tolist()
                    )
                    scored.append((score, episode))
            
            # Ordenar por score
            scored.sort(key=lambda x: x[0], reverse=True)
            results = [e for _, e in scored[:n]]
        else:
            # Fallback: busca por tags/palavras-chave
            results = candidates[:n]
        
        return results
    
    def _compute_embedding(self, text: str) -> List[float]:
        """Computa embedding (simplificado)."""
        # Em produção, usar modelo de embedding real (fastembed, sentence-transformers)
        # Aqui apenas placeholder
        import hashlib
        
        # Hash determinístico como "embedding" simplificado
        hash_obj = hashlib.md5(text.encode())
        hash_bytes = hash_obj.digest()
        
        # Converter para vetor de floats
        embedding = []
        for i in range(0, len(hash_bytes), 4):
            if len(embedding) >= self.embedding_dim:
                break
            # Pegar 4 bytes e converter para float
            val = int.from_bytes(hash_bytes[i:i+4], 'little') / (2**32)
            embedding.append(val)
        
        # Preencher se necessário
        while len(embedding) < self.embedding_dim:
            embedding.append(0.0)
        
        return embedding[:self.embedding_dim]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calcula similaridade de cosseno."""
        import numpy as np
        a_arr = np.array(a)
        b_arr = np.array(b)
        
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))
    
    def _index_episode(self, episode: Episode) -> None:
        """Indexa episódio."""
        # Indexar por tags
        for tag in episode.tags:
            if tag not in self.index_by_tag:
                self.index_by_tag[tag] = set()
            self.index_by_tag[tag].add(episode.id)
        
        # Indexar por tempo
        self.index_by_time.append((episode.timestamp, episode.id))
        self.index_by_time.sort(key=lambda x: x[0])
    
    def _enforce_limit(self) -> None:
        """Garante limite de episódios."""
        if len(self.episodes) <= self.max_episodes:
            return
        
        # Remover episódios menos importantes
        # Considerar: importância, recência, acesso recente
        episodes_with_scores = []
        
        for episode in self.episodes.values():
            # Score baseado em importância
            score = episode.importance
            
            # Penalizar por antiguidade (menos relevante)
            age_hours = (datetime.utcnow() - episode.timestamp).total_seconds() / 3600
            score -= age_hours * 0.01  # Pequena penalização por hora
            
            episodes_with_scores.append((score, episode.id))
        
        # Ordenar e remover os de menor score
        episodes_with_scores.sort(key=lambda x: x[0])
        
        to_remove = len(self.episodes) - self.max_episodes
        for _, episode_id in episodes_with_scores[:to_remove]:
            del self.episodes[episode_id]
            if episode_id in self.embeddings:
                del self.embeddings[episode_id]
        
        logger.debug(f"Enforced limit: removed {to_remove} episodes")


class AgentMemory:
    """
    Sistema de memória completo do agente.
    
    Composição:
    - Episódica: eventos específicos
    - Semântica: fatos e conhecimentos
    - Procedural: skills (como fazer)
    - Working: memória de curto prazo
    """
    
    def __init__(
        self,
        max_episodes: int = 1000,
        max_facts: int = 10000,
        embedding_dim: int = 384,
    ):
        # Memórias especializadas
        self.episodic = EpisodicMemory(
            max_episodes=max_episodes,
            embedding_dim=embedding_dim,
        )
        self.semantic = SemanticMemory(
            max_facts=max_facts,
            embedding_dim=embedding_dim,
        )
        
        # Memória de curto prazo (working memory)
        self.working: Dict[str, Any] = {}
        self.working_capacity = 7  # Miller's Law: 7 ± 2 items
        
        # Metadados
        self.creation_time = datetime.utcnow()
        self.access_count = 0
        self.storage_count = 0
    
    # ============== Episódica ==============
    
    async def store_observation(
        self,
        observation: str,
        action: str = "",
        result: str = "",
        **kwargs,
    ) -> Episode:
        """Armazena episódio."""
        self.storage_count += 1
        return self.episodic.store(
            observation=observation,
            action=action,
            result=result,
            **kwargs,
        )
    
    async def recall_episodes(
        self,
        query: str,
        n: int = 5,
        **filters,
    ) -> List[Episode]:
        """Recupera episódios."""
        self.access_count += 1
        return self.episodic.retrieve(query, n, **filters)
    
    # ============== Semântica ==============
    
    async def store_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        **kwargs,
    ) -> SemanticFact:
        """Armazena fato."""
        self.storage_count += 1
        return self.semantic.store(subject, predicate, object, **kwargs)
    
    async def query_knowledge(
        self,
        query: str,
        n: int = 5,
    ) -> List[SemanticFact]:
        """Consulta conhecimento."""
        self.access_count += 1
        return self.semantic.query(query, n)
    
    # ============== Working Memory ==============
    
    def working_set(self, key: str, value: Any) -> None:
        """Armazena na memória de curto prazo."""
        if len(self.working) >= self.working_capacity and key not in self.working:
            # Remove item menos recente (simplificado)
            oldest_key = next(iter(self.working))
            del self.working[oldest_key]
        
        self.working[key] = value
    
    def working_get(self, key: str, default: Any = None) -> Any:
        """Recupera da memória de curto prazo."""
        return self.working.get(key, default)
    
    def working_clear(self) -> None:
        """Limpa memória de curto prazo."""
        self.working.clear()
    
    # ============== Utilitários ==============
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas."""
        return {
            "episodes": len(self.episodic.episodes),
            "facts": len(self.semantic.facts),
            "working_items": len(self.working),
            "access_count": self.access_count,
            "storage_count": self.storage_count,
            "creation_time": self.creation_time.isoformat(),
        }


class SemanticMemory:
    """
    Memória semântica - fatos e conhecimentos.
    """
    
    def __init__(self, max_facts: int = 10000, embedding_dim: int = 384):
        self.max_facts = max_facts
        self.embedding_dim = embedding_dim
        
        self.facts: Dict[str, SemanticFact] = {}
        self.index_by_subject: Dict[str, Set[str]] = {}
        self.index_by_predicate: Dict[str, Set[str]] = {}
        self.embeddings: Dict[str, np.ndarray] = {}
    
    def store(
        self,
        subject: str,
        predicate: str,
        object: str,
        **kwargs,
    ) -> SemanticFact:
        """Armazena fato."""
        # Verificar se já existe fato similar
        existing = self._find_similar(subject, predicate, object)
        if existing:
            # Atualizar confiança
            existing.confidence = max(existing.confidence, kwargs.get("confidence", 1.0))
            return existing
        
        # Criar novo fato
        fact = SemanticFact(
            subject=subject,
            predicate=predicate,
            object=object,
            natural_language=kwargs.get("natural_language", f"{subject} {predicate} {object}"),
            confidence=kwargs.get("confidence", 1.0),
            source=kwargs.get("source", "unknown"),
            expiration=kwargs.get("expiration"),
        )
        
        # Calcular embedding
        fact.embedding = self._compute_embedding(fact.to_text())
        self.embeddings[fact.id] = np.array(fact.embedding)
        
        # Armazenar
        self.facts[fact.id] = fact
        self._index_fact(fact)
        
        # Verificar limite
        self._enforce_limit()
        
        return fact
    
    def query(self, query: str, n: int = 5) -> List[SemanticFact]:
        """Consulta fatos."""
        if not self.use_semantic_search or not query:
            return list(self.facts.values())[:n]
        
        # Busca semântica
        query_embedding = self._compute_embedding(query)
        
        scored = []
        for fact_id, embedding in self.embeddings.items():
            score = self._cosine_similarity(query_embedding, embedding.tolist())
            scored.append((score, fact_id))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [self.facts[fact_id] for _, fact_id in scored[:n]]
    
    def _find_similar(self, subject: str, predicate: str, object: str) -> Optional[SemanticFact]:
        """Busca fato similar."""
        for fact in self.facts.values():
            if (fact.subject.lower() == subject.lower() and
                fact.predicate.lower() == predicate.lower() and
                fact.object.lower() == object.lower()):
                return fact
        return None
    
    def _index_fact(self, fact: SemanticFact) -> None:
        """Indexa fato."""
        # Indexar por subject
        subject_key = fact.subject.lower()
        if subject_key not in self.index_by_subject:
            self.index_by_subject[subject_key] = set()
        self.index_by_subject[subject_key].add(fact.id)
        
        # Indexar por predicate
        pred_key = fact.predicate.lower()
        if pred_key not in self.index_by_predicate:
            self.index_by_predicate[pred_key] = set()
        self.index_by_predicate[pred_key].add(fact.id)
    
    def _enforce_limit(self) -> None:
        """Garante limite de fatos."""
        if len(self.facts) <= self.max_facts:
            return
        
        # Remover fatos menos importantes/confiáveis
        scored = []
        for fact in self.facts.values():
            score = fact.confidence
            # Penalizar por idade
            age_days = (datetime.utcnow() - fact.timestamp).days
            score -= age_days * 0.01
            scored.append((score, fact.id))
        
        scored.sort(key=lambda x: x[0])
        
        to_remove = len(self.facts) - self.max_facts
        for _, fact_id in scored[:to_remove]:
            del self.facts[fact_id]
            if fact_id in self.embeddings:
                del self.embeddings[fact_id]
    
    def _compute_embedding(self, text: str) -> List[float]:
        """Computa embedding (placeholder)."""
        # Em produção, usar modelo real
        import hashlib
        
        hash_obj = hashlib.md5(text.encode())
        hash_bytes = hash_obj.digest()
        
        embedding = []
        for i in range(0, len(hash_bytes), 4):
            if len(embedding) >= self.embedding_dim:
                break
            val = int.from_bytes(hash_bytes[i:i+4], 'little') / (2**32)
            embedding.append(val)
        
        while len(embedding) < self.embedding_dim:
            embedding.append(0.0)
        
        return embedding[:self.embedding_dim]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calcula similaridade de cosseno."""
        import numpy as np
        
        a_arr = np.array(a)
        b_arr = np.array(b)
        
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


class AgentMemory:
    """
    Sistema de memória completo do agente.
    
    Composição:
    - Episódica: eventos específicos
    - Semântica: fatos e conhecimentos
    - Procedural: como fazer coisas (skills)
    - Working: memória de curto prazo
    """
    
    def __init__(
        self,
        max_episodes: int = 1000,
        max_facts: int = 10000,
        embedding_dim: int = 384,
    ):
        # Memórias especializadas
        self.episodic = EpisodicMemory(
            max_episodes=max_episodes,
            embedding_dim=embedding_dim,
        )
        self.semantic = SemanticMemory(
            max_facts=max_facts,
            embedding_dim=embedding_dim,
        )
        
        # Memória de curto prazo (working memory)
        self.working: Dict[str, Any] = {}
        self.working_capacity = 7  # Miller's Law: 7 ± 2 items
        
        # Metadados
        self.creation_time = datetime.utcnow()
        self.access_count = 0
        self.storage_count = 0
    
    # ============== Episódica ==============
    
    async def store_observation(
        self,
        observation: str,
        action: str = "",
        result: str = "",
        **kwargs,
    ) -> Episode:
        """Armazena episódio."""
        self.storage_count += 1
        return self.episodic.store(
            observation=observation,
            action=action,
            result=result,
            **kwargs,
        )
    
    async def recall_episodes(
        self,
        query: str,
        n: int = 5,
        **filters,
    ) -> List[Episode]:
        """Recupera episódios."""
        self.access_count += 1
        return self.episodic.retrieve(query, n, **filters)
    
    # ============== Semântica ==============
    
    async def store_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        **kwargs,
    ) -> SemanticFact:
        """Armazena fato."""
        self.storage_count += 1
        return self.semantic.store(subject, predicate, object, **kwargs)
    
    async def query_knowledge(
        self,
        query: str,
        n: int = 5,
    ) -> List[SemanticFact]:
        """Consulta conhecimento."""
        self.access_count += 1
        return self.semantic.query(query, n)
    
    # ============== Working Memory ==============
    
    def working_set(self, key: str, value: Any) -> None:
        """Armazena na memória de curto prazo."""
        if len(self.working) >= self.working_capacity and key not in self.working:
            # Remove item menos recente (simplificado)
            oldest_key = next(iter(self.working))
            del self.working[oldest_key]
        
        self.working[key] = value
    
    def working_get(self, key: str, default: Any = None) -> Any:
        """Recupera da memória de curto prazo."""
        return self.working.get(key, default)
    
    def working_clear(self) -> None:
        """Limpa memória de curto prazo."""
        self.working.clear()
    
    # ============== Utilitários ==============
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas."""
        return {
            "episodes": len(self.episodic.episodes),
            "facts": len(self.semantic.facts),
            "working_items": len(self.working),
            "access_count": self.access_count,
            "storage_count": self.storage_count,
            "creation_time": self.creation_time.isoformat(),
        }

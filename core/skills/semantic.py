"""
core/skills/semantic.py — Semantic Matching

Sistema de matching semântico de skills usando ChromaDB + embeddings.
Converte queries em embeddings e busca skills por similaridade.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from .models import (
    SemanticMatchResult,
    SemanticQuery,
    Skill2,
    SkillVector,
)

logger = logging.getLogger(__name__)


class SemanticMatcher:
    """
    Matcher semântico para skills usando embeddings.
    
    Usa ChromaDB para armazenamento e busca vetorial,
    com fallback para similaridade por cosseno em memória.
    """
    
    def __init__(
        self,
        embedding_model: Optional[str] = None,
        chroma_client = None,
        collection_name: str = "skills",
        use_chroma: bool = True,
    ):
        """
        Inicializa o matcher semântico.
        
        Args:
            embedding_model: Nome do modelo de embeddings (fastembed por padrão)
            chroma_client: Cliente ChromaDB (opcional)
            collection_name: Nome da coleção no ChromaDB
            use_chroma: Se True, usa ChromaDB; senão, modo memória
        """
        self.embedding_model = embedding_model or "BAAI/bge-small-en-v1.5"
        self.chroma_client = chroma_client
        self.collection_name = collection_name
        self.use_chroma = use_chroma and chroma_client is not None
        
        # Cache de embeddings em memória
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._skills_by_id: Dict[str, Skill2] = {}
        
        # Inicializar modelo de embeddings
        self._embedder = None
        self._init_embedder()
        
        # Inicializar coleção ChromaDB se disponível
        if self.use_chroma:
            self._init_chroma_collection()
    
    def _init_embedder(self):
        """Inicializa o modelo de embeddings."""
        try:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(self.embedding_model)
            logger.info(f"Embedding model loaded: {self.embedding_model}")
        except ImportError:
            logger.error("fastembed not installed. Semantic matching disabled.")
            self._embedder = None
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._embedder = None
    
    def _init_chroma_collection(self):
        """Inicializa coleção no ChromaDB."""
        try:
            self._chroma_collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB collection ready: {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.use_chroma = False
            self._chroma_collection = None
    
    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Gera embedding para um texto.
        
        Args:
            text: Texto para embeddar
            
        Returns:
            Array numpy com embedding ou None se falhar
        """
        if self._embedder is None:
            return None
        
        # Check cache
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self._embedding_cache:
            return self._embedding_cache[text_hash]
        
        try:
            # Generate embedding
            embeddings = list(self._embedder.embed([text]))
            if embeddings:
                embedding = np.array(embeddings[0])
                self._embedding_cache[text_hash] = embedding
                return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
        
        return None
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calcula similaridade por cosseno."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    def index_skill(self, skill: Skill2) -> bool:
        """
        Indexa uma skill para busca semântica.
        
        Args:
            skill: Skill para indexar
            
        Returns:
            True se indexado com sucesso
        """
        # Gerar embedding
        text = skill.to_embedding_text()
        embedding = self._get_embedding(text)
        
        if embedding is None:
            logger.error(f"Failed to generate embedding for skill {skill.id}")
            return False
        
        # Atualizar skill com vector
        skill.vector = SkillVector(
            embedding=embedding.tolist(),
            dimensions=len(embedding),
            model=self.embedding_model
        )
        
        # Armazenar em memória
        self._skills_by_id[skill.id] = skill
        
        # Indexar no ChromaDB se disponível
        if self.use_chroma and hasattr(self, '_chroma_collection'):
            try:
                self._chroma_collection.upsert(
                    ids=[skill.id],
                    embeddings=[embedding.tolist()],
                    metadatas=[{
                        "slug": skill.slug,
                        "name": skill.name,
                        "category": skill.category,
                        "status": skill.status.value,
                        "owner": skill.owner or "",
                    }]
                )
            except Exception as e:
                logger.error(f"Failed to index in ChromaDB: {e}")
        
        return True
    
    def search(self, query: SemanticQuery) -> List[SemanticMatchResult]:
        """
        Busca skills semanticamente.
        
        Args:
            query: Query semântica
            
        Returns:
            Lista de resultados ordenados por relevância
        """
        # Gerar embedding da query
        query_embedding = self._get_embedding(query.query)
        
        if query_embedding is None:
            logger.error("Failed to generate query embedding")
            return []
        
        matches: List[SemanticMatchResult] = []
        
        # Buscar no ChromaDB se disponível
        if self.use_chroma and hasattr(self, '_chroma_collection'):
            try:
                results = self._chroma_collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=query.limit * 2,  # Buscar mais para filtrar
                    include=["metadatas", "distances"]
                )
                
                if results["ids"]:
                    for i, skill_id in enumerate(results["ids"][0]):
                        metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                        distance = results["distances"][0][i] if results["distances"] else 1.0
                        
                        # Filtrar por status, owner, etc
                        if query.status and metadata.get("status") != query.status.value:
                            continue
                        if query.owner and metadata.get("owner") != query.owner:
                            continue
                        
                        # Recuperar skill completa
                        skill = self._skills_by_id.get(skill_id)
                        if skill:
                            similarity = 1.0 - distance  # Converter distância em similaridade
                            matches.append(SemanticMatchResult(
                                skill=skill,
                                similarity_score=max(0.0, min(1.0, similarity)),
                                matched_fields=["semantic"],
                                explanation=f"Matched via semantic similarity ({similarity:.3f})"
                            ))
            except Exception as e:
                logger.error(f"ChromaDB query failed: {e}")
        
        # Fallback: busca em memória
        if not matches:
            for skill in self._skills_by_id.values():
                if skill.vector and skill.vector.embedding:
                    skill_embedding = np.array(skill.vector.embedding)
                    similarity = self._cosine_similarity(query_embedding, skill_embedding)
                    
                    if similarity > 0.5:  # Threshold
                        matches.append(SemanticMatchResult(
                            skill=skill,
                            similarity_score=similarity,
                            matched_fields=["semantic"],
                            explanation=f"Cosine similarity: {similarity:.3f}"
                        ))
        
        # Ordenar por score
        matches.sort(key=lambda x: x.similarity_score, reverse=True)
        
        return matches[:query.limit]
    
    def get_similar_skills(self, skill_id: str, limit: int = 5) -> List[SemanticMatchResult]:
        """
        Encontra skills similares a uma skill existente.
        
        Args:
            skill_id: ID da skill de referência
            limit: Número máximo de resultados
            
        Returns:
            Lista de skills similares
        """
        skill = self._skills_by_id.get(skill_id)
        if not skill or not skill.vector:
            return []
        
        # Criar query a partir da skill
        query = SemanticQuery(
            query=skill.to_embedding_text(),
            limit=limit + 1  # +1 para excluir a própria skill
        )
        
        results = self.search(query)
        
        # Remover a própria skill dos resultados
        return [r for r in results if r.skill.id != skill_id][:limit]
    
    def delete_skill_index(self, skill_id: str) -> bool:
        """
        Remove uma skill do índice semântico.
        
        Args:
            skill_id: ID da skill
            
        Returns:
            True se removido com sucesso
        """
        # Remover da memória
        if skill_id in self._skills_by_id:
            del self._skills_by_id[skill_id]
        
        # Remover do ChromaDB
        if self.use_chroma and hasattr(self, '_chroma_collection'):
            try:
                self._chroma_collection.delete(ids=[skill_id])
            except Exception as e:
                logger.error(f"Failed to delete from ChromaDB: {e}")
                return False
        
        return True
    
    def clear_index(self) -> None:
        """Limpa todo o índice semântico."""
        self._skills_by_id.clear()
        self._embedding_cache.clear()
        
        if self.use_chroma and hasattr(self, '_chroma_collection'):
            try:
                self._chroma_collection.delete(where={})
            except Exception as e:
                logger.error(f"Failed to clear ChromaDB: {e}")
    
    def get_index_stats(self) -> Dict:
        """
        Retorna estatísticas do índice.
        
        Returns:
            Dicionário com estatísticas
        """
        stats = {
            "indexed_skills": len(self._skills_by_id),
            "embedding_cache_size": len(self._embedding_cache),
            "chroma_available": self.use_chroma,
            "embedding_model": self.embedding_model,
        }
        
        if self.use_chroma and hasattr(self, '_chroma_collection'):
            try:
                count = self._chroma_collection.count()
                stats["chroma_count"] = count
            except Exception as e:
                stats["chroma_error"] = str(e)
        
        return stats


# Re-exportar para conveniência
__all__ = [
    "SemanticMatcher",
    "SimilarityCalculator",
]

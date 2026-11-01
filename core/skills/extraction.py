"""
core/skills/extraction.py — Skill Extraction

Extrai skills automaticamente de conversas usando LLM.
Analisa padrões, detecta repetições e sugere novas skills.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any

from .models import (
    Skill2,
    SkillConfidence,
    SkillExtraction,
    SkillSource,
    SkillStatus,
    SkillTag,
)

logger = logging.getLogger(__name__)


class ConversationAnalyzer:
    """Analisa conversas para detectar padrões de skills."""
    
    def __init__(self, min_message_count: int = 5, min_repetition: int = 2):
        """
        Inicializa o analisador.
        
        Args:
            min_message_count: Mínimo de mensagens para análise
            min_repetition: Mínimo de repetições para considerar padrão
        """
        self.min_message_count = min_message_count
        self.min_repetition = min_repetition
    
    def analyze(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analisa uma lista de mensagens.
        
        Args:
            messages: Lista de mensagens com role, content, timestamp
            
        Returns:
            Análise com padrões detectados
        """
        if len(messages) < self.min_message_count:
            return {"patterns": [], "insufficient_data": True}
        
        patterns = []
        
        # Detectar tópicos recorrentes
        topics = self._extract_topics(messages)
        if topics:
            patterns.append({
                "type": "recurring_topics",
                "topics": topics,
                "frequency": len(topics),
            })
        
        # Detectar comandos repetidos
        commands = self._extract_commands(messages)
        if commands:
            patterns.append({
                "type": "repeated_commands",
                "commands": commands,
                "frequency": sum(commands.values()),
            })
        
        # Detectar padrões de solução
        solutions = self._extract_solution_patterns(messages)
        if solutions:
            patterns.append({
                "type": "solution_patterns",
                "solutions": solutions,
                "frequency": len(solutions),
            })
        
        return {
            "patterns": patterns,
            "message_count": len(messages),
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }
    
    def _extract_topics(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extrai tópicos recorrentes das mensagens."""
        # Implementação simplificada - em produção usaria NLP
        topics = []
        topic_keywords = {
            "coding": ["code", "programming", "function", "bug", "error"],
            "writing": ["write", "draft", "email", "document", "text"],
            "analysis": ["analyze", "data", "report", "metrics", "statistics"],
            "planning": ["plan", "schedule", "timeline", "deadline", "project"],
            "communication": ["meeting", "call", "message", "chat", "discuss"],
        }
        
        topic_counts = {topic: 0 for topic in topic_keywords}
        
        for msg in messages:
            content = msg.get("content", "").lower()
            for topic, keywords in topic_keywords.items():
                if any(kw in content for kw in keywords):
                    topic_counts[topic] += 1
        
        # Retornar tópicos com contagem suficiente
        for topic, count in topic_counts.items():
            if count >= self.min_repetition:
                topics.append(topic)
        
        return topics
    
    def _extract_commands(self, messages: List[Dict[str, Any]]) -> Dict[str, int]:
        """Extrai comandos repetidos."""
        commands = {}
        
        for msg in messages:
            content = msg.get("content", "")
            # Procurar padrões de comando
            cmd_patterns = [
                r"/\w+",
                r"!\w+",
                r"\b(run|execute|call|invoke)\s+(\w+)",
            ]
            
            for pattern in cmd_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    cmd = match[0] if isinstance(match, tuple) else match
                    commands[cmd] = commands.get(cmd, 0) + 1
        
        # Filtrar apenas comandos repetidos
        return {k: v for k, v in commands.items() if v >= self.min_repetition}
    
    def _extract_solution_patterns(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extrai padrões de solução de problemas."""
        patterns = []
        
        # Procurar por mensagens do assistente que parecem soluções
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
            
            content = msg.get("content", "")
            
            # Verificar se parece uma solução passo-a-passo
            if self._looks_like_solution(content):
                # Encontrar o problema correspondente
                problem = None
                for j in range(i-1, max(-1, i-5), -1):
                    if messages[j].get("role") == "user":
                        problem = messages[j].get("content", "")
                        break
                
                if problem:
                    patterns.append({
                        "problem": problem[:200],  # Limitar tamanho
                        "solution": content[:500],
                        "steps_count": content.count("\n") + 1,
                    })
        
        return patterns
    
    def _looks_like_solution(self, content: str) -> bool:
        """Verifica se o conteúdo parece ser uma solução."""
        solution_indicators = [
            "step", "passo", "first", "primeiro",
            "1.", "2.", "- ", "* ",
            "solution", "solução",
            "here's how", "aqui está",
        ]
        
        content_lower = content.lower()
        return any(ind in content_lower for ind in solution_indicators)


class SkillExtractor:
    """Extrai skills automaticamente de conversas."""
    
    def __init__(
        self,
        llm_client=None,
        analyzer: Optional[ConversationAnalyzer] = None,
        min_confidence: float = 0.6,
    ):
        """
        Inicializa o extrator.
        
        Args:
            llm_client: Cliente LLM para extração (OpenAI, Anthropic, etc.)
            analyzer: Analisador de conversas (opcional)
            min_confidence: Confiança mínima para aceitar extração
        """
        self.llm_client = llm_client
        self.analyzer = analyzer or ConversationAnalyzer()
        self.min_confidence = min_confidence
    
    def extract_from_conversation(
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
        # Analisar conversa
        analysis = self.analyzer.analyze(messages)
        
        extractions = []
        
        # Extrair de padrões detectados
        for pattern in analysis.get("patterns", []):
            if pattern["type"] == "solution_patterns":
                for solution in pattern.get("solutions", []):
                    extraction = self._extraction_from_solution(
                        solution, conversation_id, messages
                    )
                    if extraction:
                        extractions.append(extraction)
        
        # Extrair usando LLM se disponível
        if self.llm_client and len(messages) >= 5:
            llm_extractions = self._extract_with_llm(conversation_id, messages)
            extractions.extend(llm_extractions)
        
        # Filtrar por confiança
        extractions = [e for e in extractions if e.confidence >= self.min_confidence]
        
        # Remover duplicatas
        seen_names = set()
        unique = []
        for e in extractions:
            if e.name.lower() not in seen_names:
                seen_names.add(e.name.lower())
                unique.append(e)
        
        return unique
    
    def _extraction_from_solution(
        self,
        solution: Dict[str, Any],
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> Optional[SkillExtraction]:
        """Cria extração a partir de um padrão de solução."""
        problem = solution.get("problem", "")
        solution_text = solution.get("solution", "")
        
        if not problem or not solution_text:
            return None
        
        # Gerar nome baseado no problema
        name = self._generate_skill_name(problem)
        
        # Extrair tags
        tags = self._extract_tags(problem + " " + solution_text)
        
        # Extrair procedimento
        procedure = self._extract_procedure(solution_text)
        
        return SkillExtraction(
            source_conversation_id=conversation_id,
            source_messages=[m.get("id", str(i)) for i, m in enumerate(messages[-5:])],
            name=name,
            description=f"Skill auto-extracted from conversation: {problem[:100]}",
            category="auto-extracted",
            tags=tags,
            when_to_use=problem[:200],
            procedure=procedure,
            confidence=0.6,  # Base confidence for pattern-based extraction
        )
    
    def _extract_with_llm(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> List[SkillExtraction]:
        """Extrai skills usando LLM."""
        if not self.llm_client:
            return []
        
        # Preparar contexto
        conversation_text = self._format_conversation(messages)
        
        prompt = f"""
Analise a seguinte conversa e identifique possíveis skills (habilidades/procedimentos) 
que poderiam ser extraídas e reutilizadas no futuro.

Conversa:
{conversation_text}

Para cada skill identificada, forneça:
1. Nome curto e descritivo
2. Descrição do que faz
3. Categoria (ex: coding, writing, analysis, communication)
4. Tags relevantes
5. Quando usar (contexto)
6. Procedimento passo-a-passo
7. Nível de confiança (0.0-1.0)

Responda em formato JSON:
{{
  "skills": [
    {{
      "name": "...",
      "description": "...",
      "category": "...",
      "tags": ["..."],
      "when_to_use": "...",
      "procedure": ["..."],
      "confidence": 0.8
    }}
  ]
}}

Se não identificar nenhuma skill clara, retorne {{"skills": []}}.
"""
        
        try:
            # Chamar LLM
            response = self._call_llm(prompt)
            
            # Parse JSON
            data = json.loads(response)
            skills_data = data.get("skills", [])
            
            extractions = []
            for skill_data in skills_data:
                extraction = SkillExtraction(
                    source_conversation_id=conversation_id,
                    source_messages=[m.get("id", str(i)) for i, m in enumerate(messages[-5:])],
                    name=skill_data["name"],
                    description=skill_data["description"],
                    category=skill_data.get("category", "general"),
                    tags=[SkillTag(name=t) for t in skill_data.get("tags", [])],
                    when_to_use=skill_data.get("when_to_use", ""),
                    procedure=skill_data.get("procedure", []),
                    confidence=skill_data.get("confidence", 0.5),
                )
                extractions.append(extraction)
            
            return extractions
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []
    
    def _generate_skill_name(self, problem: str) -> str:
        """Gera nome de skill a partir de descrição do problema."""
        # Pegar primeiras palavras significativas
        words = problem.split()[:5]
        name = " ".join(words).lower()
        
        # Limpar e formatar
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'\s+', '-', name)
        name = name[:50]  # Limitar tamanho
        
        return name or "auto-extracted-skill"
    
    def _extract_tags(self, text: str) -> List[SkillTag]:
        """Extrai tags de texto."""
        # Palavras-chave comuns para categorização
        keyword_tags = {
            "code": ["code", "program", "function", "script", "debug"],
            "write": ["write", "draft", "compose", "text", "document"],
            "analyze": ["analyze", "data", "report", "metric", "statistic"],
            "plan": ["plan", "schedule", "timeline", "project", "organize"],
            "search": ["search", "find", "lookup", "research", "query"],
            "convert": ["convert", "transform", "format", "parse"],
        }
        
        text_lower = text.lower()
        tags = []
        
        for tag_name, keywords in keyword_tags.items():
            if any(kw in text_lower for kw in keywords):
                tags.append(SkillTag(name=tag_name, confidence=0.7))
        
        return tags[:5]  # Limitar a 5 tags
    
    def _extract_procedure(self, solution: str) -> List[str]:
        """Extrai procedimento passo-a-passo de solução."""
        # Tentar dividir em passos numerados
        steps = []
        
        # Procurar por números ou bullets
        numbered_pattern = r'(?:^|\n)\s*(?:\d+[.):\-]\s+|[-•*]\s+)(.+?)(?=\n|$)'
        matches = re.findall(numbered_pattern, solution, re.MULTILINE)
        
        if matches:
            steps = [s.strip() for s in matches if len(s.strip()) > 5]
        else:
            # Se não encontrou passos, dividir em sentenças
            sentences = re.split(r'[.!?]+', solution)
            steps = [s.strip() for s in sentences if len(s.strip()) > 10]
        
        return steps[:10]  # Limitar a 10 passos
    
    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Formata conversa para prompt."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role.upper()}: {content}")
        return "\n\n".join(lines)
    
    def _call_llm(self, prompt: str) -> str:
        """Chama LLM com prompt."""
        # Implementação depende do cliente LLM disponível
        # Por enquanto, retornar JSON vazio se não tiver LLM
        if not self.llm_client:
            return '{"skills": []}'
        
        # Aqui seria a chamada real ao LLM
        # response = self.llm_client.chat.completions.create(...)
        # return response.choices[0].message.content
        
        # Placeholder
        return '{"skills": []}'


class SkillExtractionStorage:
    """Armazena extrações de skills pendentes de revisão."""
    
    def __init__(self, db_connection=None):
        """
        Inicializa o storage.
        
        Args:
            db_connection: Conexão com banco de dados (SQLAlchemy ou similar)
        """
        self.db = db_connection
        self._memory_storage: Dict[str, SkillExtraction] = {}  # Fallback em memória
    
    def save(self, extraction: SkillExtraction) -> bool:
        """
        Salva uma extração.
        
        Args:
            extraction: Extração para salvar
            
        Returns:
            True se salvo com sucesso
        """
        try:
            if self.db:
                # Salvar no banco de dados
                # Implementação depende do modelo SQLAlchemy
                pass
            else:
                # Fallback: salvar em memória
                self._memory_storage[extraction.id] = extraction
            
            return True
        except Exception as e:
            logger.error(f"Failed to save extraction: {e}")
            return False
    
    def get(self, extraction_id: str) -> Optional[SkillExtraction]:
        """
        Recupera uma extração pelo ID.
        
        Args:
            extraction_id: ID da extração
            
        Returns:
            Extração ou None se não encontrada
        """
        if self.db:
            # Buscar no banco de dados
            pass
        
        return self._memory_storage.get(extraction_id)
    
    def list_pending(
        self,
        owner: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[SkillExtraction]:
        """
        Lista extrações pendentes de revisão.
        
        Args:
            owner: Filtrar por owner
            limit: Limite de resultados
            offset: Offset para paginação
            
        Returns:
            Lista de extrações pendentes
        """
        # Filtrar da memória
        pending = [
            e for e in self._memory_storage.values()
            if e.review_status == "pending"
            and (owner is None or True)  # Adicionar filtro de owner se necessário
        ]
        
        # Ordenar por data de extração (mais recentes primeiro)
        pending.sort(key=lambda x: x.extracted_at, reverse=True)
        
        return pending[offset:offset + limit]
    
    def update_status(
        self,
        extraction_id: str,
        status: str,
        reviewed_by: Optional[str] = None,
    ) -> bool:
        """
        Atualiza status de revisão.
        
        Args:
            extraction_id: ID da extração
            status: Novo status (approved, rejected, modified)
            reviewed_by: Quem revisou
            
        Returns:
            True se atualizado com sucesso
        """
        extraction = self.get(extraction_id)
        if not extraction:
            return False
        
        extraction.review_status = status
        extraction.reviewed_by = reviewed_by
        
        return self.save(extraction)
    
    def convert_to_skill(
        self,
        extraction_id: str,
        created_by: Optional[str] = None,
    ) -> Optional[Skill2]:
        """
        Converte uma extração aprovada em Skill2.
        
        Args:
            extraction_id: ID da extração
            created_by: Quem está criando
            
        Returns:
            Skill2 criada ou None se falhou
        """
        extraction = self.get(extraction_id)
        if not extraction or extraction.review_status != "approved":
            return None
        
        skill = Skill2(
            slug=extraction.name.lower().replace(" ", "-"),
            name=extraction.name,
            description=extraction.description,
            category=extraction.category,
            tags=extraction.tags,
            when_to_use=extraction.when_to_use,
            procedure=extraction.procedure,
            pitfalls=extraction.pitfalls,
            verification=extraction.verification,
            status=SkillStatus.DRAFT,
            source=SkillSource.EXTRACTED,
            created_by=created_by,
            confidence=SkillConfidence(overall=extraction.confidence),
        )
        
        return skill
    
    def delete(self, extraction_id: str) -> bool:
        """
        Deleta uma extração.
        
        Args:
            extraction_id: ID da extração
            
        Returns:
            True se deletado com sucesso
        """
        if extraction_id in self._memory_storage:
            del self._memory_storage[extraction_id]
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas das extrações.
        
        Returns:
            Dicionário com estatísticas
        """
        all_extractions = list(self._memory_storage.values())
        
        total = len(all_extractions)
        pending = sum(1 for e in all_extractions if e.review_status == "pending")
        approved = sum(1 for e in all_extractions if e.review_status == "approved")
        rejected = sum(1 for e in all_extractions if e.review_status == "rejected")
        
        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "conversion_rate": approved / total if total > 0 else 0.0,
        }


# Re-exportar para conveniência
__all__ = [
    "ConversationAnalyzer",
    "SkillExtractor",
    "SkillExtractionStorage",
]

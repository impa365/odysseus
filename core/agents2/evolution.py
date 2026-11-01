"""
core/agents2/evolution.py — Agent Evolution System

Sistema de evolução de agentes através de:
- Mutação de parâmetros
- Crossover de estratégias
- Seleção por fitness
- Learning de execuções
"""

from __future__ import annotations

import copy
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Type

logger = logging.getLogger(__name__)


@dataclass
class AgentGene:
    """
    Gene representando características do agente.
    
    Os genes são codificações de comportamentos e estratégias
    que podem ser mutadas e combinadas.
    """
    id: str = field(default_factory=lambda: f"gene_{datetime.utcnow().timestamp()}")
    generation: int = 0
    
    # Genes comportamentais
    proactivity: float = 0.5  # 0-1, quão proativo é
    risk_tolerance: float = 0.5  # 0-1, tolerância a risco
    exploration_rate: float = 0.3  # 0-1, taxa de exploração
    planning_depth: int = 3  # 1-10, profundidade de planejamento
    reflection_frequency: int = 5  # a cada N ações
    
    # Genes de aprendizado
    learning_rate: float = 0.1  # taxa de aprendizado
    memory_importance_decay: float = 0.95  # decaimento de importância
    pattern_recognition_threshold: float = 0.7  # threshold para reconhecer padrões
    
    # Histórico
    parent_ids: List[str] = field(default_factory=list)
    mutation_history: List[Dict[str, Any]] = field(default_factory=list)
    fitness_history: List[Tuple[int, float]] = field(default_factory=list)  # (generation, fitness)
    
    def mutate(
        self,
        mutation_rate: float = 0.1,
        mutation_strength: float = 0.2,
    ) -> AgentGene:
        """
        Cria nova versão mutada do gene.
        
        Args:
            mutation_rate: Probabilidade de mutar cada gene
            mutation_strength: Intensidade da mutação
            
        Returns:
            Gene mutado
        """
        child = copy.deepcopy(self)
        child.id = f"gene_{datetime.utcnow().timestamp()}"
        child.generation = self.generation + 1
        child.parent_ids = [self.id]
        
        mutations = []
        
        # Função auxiliar para mutar valor
        def mutate_value(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
            if random.random() < mutation_rate:
                mutation = random.gauss(0, mutation_strength)
                new_val = value + mutation * (max_val - min_val)
                return max(min_val, min(max_val, new_val))
            return value
        
        def mutate_int(value: int, min_val: int, max_val: int) -> int:
            if random.random() < mutation_rate:
                mutation = random.randint(-max(1, int(mutation_strength * (max_val - min_val))), 
                                         max(1, int(mutation_strength * (max_val - min_val))))
                new_val = value + mutation
                return max(min_val, min(max_val, new_val))
            return value
        
        # Mutar genes comportamentais
        old_proactivity = child.proactivity
        child.proactivity = mutate_value(child.proactivity)
        if child.proactivity != old_proactivity:
            mutations.append({"gene": "proactivity", "old": old_proactivity, "new": child.proactivity})
        
        old_risk = child.risk_tolerance
        child.risk_tolerance = mutate_value(child.risk_tolerance)
        if child.risk_tolerance != old_risk:
            mutations.append({"gene": "risk_tolerance", "old": old_risk, "new": child.risk_tolerance})
        
        old_exploration = child.exploration_rate
        child.exploration_rate = mutate_value(child.exploration_rate)
        if child.exploration_rate != old_exploration:
            mutations.append({"gene": "exploration_rate", "old": old_exploration, "new": child.exploration_rate})
        
        old_depth = child.planning_depth
        child.planning_depth = mutate_int(child.planning_depth, 1, 10)
        if child.planning_depth != old_depth:
            mutations.append({"gene": "planning_depth", "old": old_depth, "new": child.planning_depth})
        
        old_reflection = child.reflection_frequency
        child.reflection_frequency = mutate_int(child.reflection_frequency, 1, 50)
        if child.reflection_frequency != old_reflection:
            mutations.append({"gene": "reflection_frequency", "old": old_reflection, "new": child.reflection_frequency})
        
        # Mutar genes de aprendizado
        old_learning = child.learning_rate
        child.learning_rate = mutate_value(child.learning_rate, 0.001, 1.0)
        if child.learning_rate != old_learning:
            mutations.append({"gene": "learning_rate", "old": old_learning, "new": child.learning_rate})
        
        child.mutation_history = mutations
        
        logger.debug(f"Created mutated gene {child.id} with {len(mutations)} mutations")
        
        return child
    
    def crossover(self, other: AgentGene, crossover_points: int = 2) -> AgentGene:
        """
        Realiza crossover com outro gene.
        
        Args:
            other: Outro gene para crossover
            crossover_points: Número de pontos de crossover
            
        Returns:
            Novo gene resultado do crossover
        """
        child = AgentGene(
            generation=max(self.generation, other.generation) + 1,
            parent_ids=[self.id, other.id],
        )
        
        # Lista de atributos para crossover
        attributes = [
            "proactivity",
            "risk_tolerance",
            "exploration_rate",
            "planning_depth",
            "reflection_frequency",
            "learning_rate",
            "memory_importance_decay",
            "pattern_recognition_threshold",
        ]
        
        # Realizar crossover
        for i, attr in enumerate(attributes):
            # Alternar entre pais
            parent = self if i % 2 == 0 else other
            value = getattr(parent, attr)
            setattr(child, attr, value)
        
        logger.debug(f"Created crossover gene {child.id} from {self.id} and {other.id}")
        
        return child
    
    def calculate_fitness(
        self,
        performance_score: float,
        survival_time: float,
        tasks_completed: int,
        error_rate: float,
    ) -> float:
        """
        Calcula fitness do gene.
        
        Args:
            performance_score: Score de desempenho (0-1)
            survival_time: Tempo de sobrevivência
            tasks_completed: Tarefas completadas
            error_rate: Taxa de erro (0-1)
            
        Returns:
            Score de fitness
        """
        # Componentes do fitness
        perf_weight = 0.4
        survival_weight = 0.2
        tasks_weight = 0.2
        reliability_weight = 0.2
        
        # Normalizar survival (assumir max 1 hora = 3600s)
        survival_score = min(survival_time / 3600, 1.0)
        
        # Normalizar tasks (assumir max 100)
        tasks_score = min(tasks_completed / 100, 1.0)
        
        # Reliability (1 - error_rate)
        reliability_score = 1.0 - error_rate
        
        # Calcular fitness
        fitness = (
            performance_score * perf_weight +
            survival_score * survival_weight +
            tasks_score * tasks_weight +
            reliability_score * reliability_weight
        )
        
        return fitness
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "generation": self.generation,
            "proactivity": self.proactivity,
            "risk_tolerance": self.risk_tolerance,
            "exploration_rate": self.exploration_rate,
            "planning_depth": self.planning_depth,
            "reflection_frequency": self.reflection_frequency,
            "learning_rate": self.learning_rate,
            "memory_importance_decay": self.memory_importance_decay,
            "pattern_recognition_threshold": self.pattern_recognition_threshold,
            "parent_ids": self.parent_ids,
            "mutation_history": self.mutation_history,
            "fitness_history": self.fitness_history,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentGene:
        """Cria gene a partir de dicionário."""
        gene = cls()
        
        for key in ["id", "generation", "parent_ids", "mutation_history", "fitness_history"]:
            if key in data:
                setattr(gene, key, data[key])
        
        for key in [
            "proactivity", "risk_tolerance", "exploration_rate",
            "planning_depth", "reflection_frequency", "learning_rate",
            "memory_importance_decay", "pattern_recognition_threshold",
        ]:
            if key in data:
                setattr(gene, key, data[key])
        
        return gene


class EvolutionEngine:
    """
    Motor de evolução de agentes.
    
    Implementa:
- Seleção natural (fitness)
    - Mutação de genes
    - Crossover (recombinação)
    - Elitismo (preservar melhores)
    """
    
    def __init__(
        self,
        population_size: int = 20,
        elite_ratio: float = 0.2,
        mutation_rate: float = 0.1,
        mutation_strength: float = 0.2,
        crossover_rate: float = 0.7,
    ):
        """
        Inicializa motor de evolução.
        
        Args:
            population_size: Tamanho da população
            elite_ratio: Proporção de elites a preservar
            mutation_rate: Taxa de mutação
            mutation_strength: Intensidade da mutação
            crossover_rate: Taxa de crossover
        """
        self.population_size = population_size
        self.elite_ratio = elite_ratio
        self.mutation_rate = mutation_rate
        self.mutation_strength = mutation_strength
        self.crossover_rate = crossover_rate
        
        self.population: List[AgentGene] = []
        self.generation = 0
        self.fitness_history: List[Dict[str, float]] = []
    
    def initialize_population(self, seed_genes: Optional[List[AgentGene]] = None) -> None:
        """
        Inicializa população.
        
        Args:
            seed_genes: Genes semente (opcional)
        """
        if seed_genes:
            self.population = seed_genes[:self.population_size]
        else:
            # Criar genes aleatórios
            self.population = []
            for _ in range(self.population_size):
                gene = AgentGene(
                    generation=0,
                    proactivity=random.uniform(0.2, 0.8),
                    risk_tolerance=random.uniform(0.2, 0.8),
                    exploration_rate=random.uniform(0.1, 0.5),
                    planning_depth=random.randint(1, 5),
                )
                self.population.append(gene)
        
        logger.info(f"Initialized population with {len(self.population)} genes")
    
    def evaluate_fitness(
        self,
        fitness_fn: callable,
    ) -> Dict[str, float]:
        """
        Avalia fitness da população.
        
        Args:
            fitness_fn: Função de fitness (gene) -> float
            
        Returns:
            Estatísticas de fitness
        """
        fitness_scores = []
        
        for gene in self.population:
            fitness = fitness_fn(gene)
            gene.fitness_history.append((self.generation, fitness))
            fitness_scores.append(fitness)
        
        stats = {
            "min": min(fitness_scores),
            "max": max(fitness_scores),
            "mean": sum(fitness_scores) / len(fitness_scores),
            "median": sorted(fitness_scores)[len(fitness_scores) // 2],
        }
        
        self.fitness_history.append({"generation": self.generation, **stats})
        
        return stats
    
    def select_parent(self, tournament_size: int = 3) -> AgentGene:
        """
        Seleciona pai usando tournament selection.
        
        Args:
            tournament_size: Tamanho do torneio
            
        Returns:
            Gene selecionado
        """
        tournament = random.sample(self.population, min(tournament_size, len(self.population)))
        
        # Selecionar o com maior fitness (último registro)
        def get_fitness(gene):
            if gene.fitness_history:
                return gene.fitness_history[-1][1]
            return 0.0
        
        return max(tournament, key=get_fitness)
    
    def evolve_generation(self) -> None:
        """Evolui para próxima geração."""
        # Ordenar por fitness
        def get_fitness(gene):
            if gene.fitness_history:
                return gene.fitness_history[-1][1]
            return 0.0
        
        sorted_population = sorted(self.population, key=get_fitness, reverse=True)
        
        # Elitismo: preservar melhores
        elite_count = max(1, int(self.elite_ratio * self.population_size))
        new_population = sorted_population[:elite_count]
        
        # Gerar restante da população
        while len(new_population) < self.population_size:
            # Crossover
            if random.random() < self.crossover_rate:
                parent1 = self.select_parent()
                parent2 = self.select_parent()
                child = parent1.crossover(parent2)
            else:
                # Clonar e mutar
                parent = self.select_parent()
                child = parent.mutate(self.mutation_rate, self.mutation_strength)
            
            # Atualizar geração
            child.generation = self.generation + 1
            
            new_population.append(child)
        
        self.population = new_population[:self.population_size]
        self.generation += 1
        
        logger.info(f"Evolved to generation {self.generation}")
    
    def get_best_gene(self) -> Optional[AgentGene]:
        """Retorna melhor gene da população."""
        if not self.population:
            return None
        
        def get_fitness(gene):
            if gene.fitness_history:
                return gene.fitness_history[-1][1]
            return 0.0
        
        return max(self.population, key=get_fitness)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas da evolução."""
        best = self.get_best_gene()
        
        return {
            "generation": self.generation,
            "population_size": len(self.population),
            "best_gene_id": best.id if best else None,
            "best_fitness": best.fitness_history[-1][1] if best and best.fitness_history else 0,
            "fitness_history": self.fitness_history,
        }

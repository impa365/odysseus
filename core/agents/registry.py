"""
Subagent Registry

Sistema de registro e gerenciamento de subagentes.
Inspirado no OpenClaw, adaptado para Odysseus.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, AsyncIterator
from contextlib import asynccontextmanager
import json

# Configurar logging
logger = logging.getLogger(__name__)


class SubagentRegistry:
    """
    Registry central para gerenciar execuções de subagentes.
    
    Responsabilidades:
    - Registrar novas execuções de subagentes
    - Gerenciar lifecycle (spawn, resume, complete)
    - Rastrear status e resultados
    - Recuperar execuções órfãs
    - Limpeza periódica
    """
    
    def __init__(
        self,
        db_session_factory: Callable,
        cleanup_interval: int = 300,  # 5 minutos
        orphan_timeout: int = 600,    # 10 minutos
        max_history: int = 1000       # Máximo de runs mantidas
    ):
        """
        Inicializa o registry.
        
        Args:
            db_session_factory: Factory para criar sessões de DB
            cleanup_interval: Intervalo entre limpezas (segundos)
            orphan_timeout: Timeout para considerar órfão (segundos)
            max_history: Máximo de runs históricas mantidas
        """
        self._db_factory = db_session_factory
        self._cleanup_interval = cleanup_interval
        self._orphan_timeout = orphan_timeout
        self._max_history = max_history
        
        # Estado em memória (cache)
        self._active_runs: Dict[str, Any] = {}  # run_id -> SubagentRun
        self._locks: Dict[str, asyncio.Lock] = {}  # run_id -> Lock
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._orphan_recovery_task: Optional[asyncio.Task] = None
        
        # Handlers de eventos
        self._event_handlers: Dict[str, List[Callable]] = {}
        
        self._initialized = False
        
        logger.info("SubagentRegistry initialized")
    
    async def initialize(self):
        """Inicializa o registry e inicia tarefas de background."""
        if self._initialized:
            return
        
        logger.info("Initializing SubagentRegistry...")
        
        # Carregar runs ativas do banco
        await self._load_active_runs()
        
        # Iniciar tarefas de background
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="subagent_cleanup"
        )
        self._orphan_recovery_task = asyncio.create_task(
            self._orphan_recovery_loop(),
            name="subagent_orphan_recovery"
        )
        
        self._initialized = True
        logger.info("SubagentRegistry fully initialized")
    
    async def shutdown(self):
        """Encerra o registry gracefulmente."""
        logger.info("Shutting down SubagentRegistry...")
        
        # Cancelar tarefas de background
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._orphan_recovery_task:
            self._orphan_recovery_task.cancel()
            try:
                await self._orphan_recovery_task
            except asyncio.CancelledError:
                pass
        
        # Persistir estado final
        await self._persist_all_runs()
        
        self._initialized = False
        logger.info("SubagentRegistry shut down complete")
    
    # =========================================================================
    # REGISTRY OPERATIONS
    # =========================================================================
    
    async def spawn(
        self,
        config: 'SubagentConfig',
        task_description: str,
        input_data: Optional[Dict[str, Any]] = None,
        parent_run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> 'SubagentRun':
        """
        Registra e inicia um novo subagente.
        
        Args:
            config: Configuração do subagente
            task_description: Descrição da tarefa
            input_data: Dados de entrada
            parent_run_id: ID do run pai (se houver)
            session_id: ID da sessão do usuário
            user_id: ID do usuário
        
        Returns:
            SubagentRun: O run registrado
        """
        from .models import SubagentRun, SubagentStatus
        
        # Criar o run
        run = SubagentRun(
            name=config.name,
            config=config,
            task_description=task_description,
            input_data=input_data or {},
            parent_id=parent_run_id,
            session_id=session_id or "",
            user_id=user_id or "",
            status=SubagentStatus.PENDING
        )
        
        # Persistir no banco
        await self._persist_run(run)
        
        # Adicionar ao cache
        self._active_runs[run.id] = run
        self._locks[run.id] = asyncio.Lock()
        
        # Emitir evento
        await self._emit_event('spawned', run)
        
        logger.info(f"Spawned subagent {run.id} ({run.name})")
        
        # Iniciar execução se não tiver parent (parents iniciam filhos manualmente)
        if not parent_run_id:
            asyncio.create_task(self._execute_run(run.id))
        
        return run
    
    async def resume(
        self,
        run_id: str,
        context_update: Optional[Dict[str, Any]] = None
    ) -> 'SubagentRun':
        """
        Retoma um subagente pausado.
        
        Args:
            run_id: ID do run
            context_update: Dados adicionais para contexto
        
        Returns:
            SubagentRun atualizado
        """
        from .models import SubagentStatus
        
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        if run.status != SubagentStatus.PAUSED:
            raise ValueError(f"Cannot resume run with status {run.status}")
        
        # Atualizar contexto se fornecido
        if context_update:
            run.input_data.update(context_update)
        
        # Atualizar status
        run.status = SubagentStatus.RUNNING
        run.checkpoints.append({
            'type': 'resume',
            'timestamp': datetime.utcnow().isoformat(),
            'context_keys': list(context_update.keys()) if context_update else []
        })
        
        await self._persist_run(run)
        await self._emit_event('resumed', run)
        
        # Retomar execução
        asyncio.create_task(self._execute_run(run.id))
        
        logger.info(f"Resumed subagent {run_id}")
        
        return run
    
    async def complete(
        self,
        run_id: str,
        outcome: 'SubagentOutcome',
        result_data: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None
    ) -> 'SubagentRun':
        """
        Completa um subagente com resultado.
        
        Args:
            run_id: ID do run
            outcome: Resultado (success, failure, etc.)
            result_data: Dados do resultado
            summary: Resumo do que foi feito
        
        Returns:
            SubagentRun completado
        """
        from .models import SubagentStatus
        
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        # Atualizar run
        run.status = SubagentStatus.COMPLETED
        run.outcome = outcome
        run.output_data = result_data or {}
        run.result_summary = summary or ""
        run.completed_at = datetime.utcnow()
        
        # Calcular duração se tiver started_at
        if run.started_at:
            duration = (run.completed_at - run.started_at).total_seconds()
            run.output_data['_meta_duration_seconds'] = duration
        
        await self._persist_run(run)
        
        # Remover do cache ativo (manter em cache secundário para consulta)
        if run_id in self._active_runs:
            del self._active_runs[run_id]
        if run_id in self._locks:
            del self._locks[run_id]
        
        await self._emit_event('completed', run)
        
        # Notificar parent se houver
        if run.parent_id:
            await self._notify_parent(run.parent_id, run)
        
        logger.info(f"Completed subagent {run_id} with outcome {outcome.value}")
        
        return run
    
    async def cancel(
        self,
        run_id: str,
        reason: Optional[str] = None
    ) -> 'SubagentRun':
        """
        Cancela um subagente em execução.
        
        Args:
            run_id: ID do run
            reason: Motivo do cancelamento
        
        Returns:
            SubagentRun cancelado
        """
        from .models import SubagentStatus, SubagentOutcome
        
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        if run.status in [SubagentStatus.COMPLETED, SubagentStatus.FAILED, SubagentStatus.CANCELLED]:
            raise ValueError(f"Cannot cancel run with status {run.status}")
        
        # Atualizar status
        run.status = SubagentStatus.CANCELLED
        run.outcome = SubagentOutcome.ABORTED
        run.error_message = reason or "Cancelled by user"
        run.completed_at = datetime.utcnow()
        
        await self._persist_run(run)
        await self._emit_event('cancelled', run)
        
        logger.info(f"Cancelled subagent {run_id}: {reason}")
        
        return run

    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    async def get_run(
        self,
        run_id: str,
        include_messages: bool = False
    ) -> Optional['SubagentRun']:
        """
        Recupera um run pelo ID.
        
        Args:
            run_id: ID do run
            include_messages: Se deve carregar mensagens
        
        Returns:
            SubagentRun ou None
        """
        # Verificar cache primeiro
        if run_id in self._active_runs:
            return self._active_runs[run_id]
        
        # Buscar no banco
        run = await self._load_run_from_db(run_id, include_messages)
        
        # Adicionar ao cache se ainda ativo
        if run and run.status in [
            'pending', 'spawning', 'running', 'paused', 'recovering'
        ]:
            self._active_runs[run_id] = run
            if run_id not in self._locks:
                self._locks[run_id] = asyncio.Lock()
        
        return run
    
    async def list_runs(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        status: Optional[List[str]] = None,
        agent_type: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_dir: str = "desc"
    ) -> Dict[str, Any]:
        """
        Lista runs com filtros.
        
        Returns:
            Dict com 'items', 'total', 'page', 'pages'
        """
        # Construir query
        filters = []
        
        if user_id:
            filters.append(('user_id', '=', user_id))
        if session_id:
            filters.append(('session_id', '=', session_id))
        if parent_id is not None:  # None = raiz, string = filtro
            filters.append(('parent_id', '=', parent_id))
        if status:
            filters.append(('status', 'in', status))
        if agent_type:
            filters.append(('agent_type', '=', agent_type))
        if created_after:
            filters.append(('created_at', '>=', created_after))
        if created_before:
            filters.append(('created_at', '<=', created_before))
        
        # Executar query via DB session
        async with self._db_factory() as db:
            # Count total
            total = await self._count_runs(db, filters)
            
            # Query items
            items = await self._query_runs(
                db, filters, limit, offset, order_by, order_dir
            )
        
        pages = (total + limit - 1) // limit if limit > 0 else 1
        page = (offset // limit) + 1 if limit > 0 else 1
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'pages': pages,
            'limit': limit,
            'offset': offset
        }
    
    async def get_tree(
        self,
        root_id: str,
        max_depth: int = 10
    ) -> Dict[str, Any]:
        """
        Recupera árvore de execuções a partir de um root.
        
        Args:
            root_id: ID do run raiz
            max_depth: Profundidade máxima
        
        Returns:
            Dict com estrutura de árvore
        """
        root = await self.get_run(root_id)
        if not root:
            return None
        
        async def build_tree(run_id: str, depth: int) -> Dict:
            if depth > max_depth:
                return {'id': run_id, 'truncated': True}
            
            run = await self.get_run(run_id)
            if not run:
                return {'id': run_id, 'missing': True}
            
            node = {
                'id': run.id,
                'name': run.name,
                'status': run.status.value,
                'outcome': run.outcome.value if run.outcome else None,
                'agent_type': run.config.agent_type,
                'created_at': run.created_at.isoformat(),
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                'children': []
            }
            
            # Recursivamente adicionar filhos
            for child_id in run.child_ids:
                child_node = await build_tree(child_id, depth + 1)
                node['children'].append(child_node)
            
            return node
        
        return await build_tree(root_id, 0)

    # =========================================================================
    # LIFECYCLE MANAGEMENT
    # =========================================================================

    async def pause(
        self,
        run_id: str,
        reason: Optional[str] = None
    ) -> 'SubagentRun':
        """Pausa um subagente em execução."""
        from .models import SubagentStatus
        
        async with self._get_lock(run_id):
            run = await self.get_run(run_id)
            if not run:
                raise ValueError(f"Run {run_id} not found")
            
            if run.status != SubagentStatus.RUNNING:
                raise ValueError(f"Cannot pause run with status {run.status}")
            
            run.status = SubagentStatus.PAUSED
            run.checkpoints.append({
                'type': 'pause',
                'timestamp': datetime.utcnow().isoformat(),
                'reason': reason
            })
            
            await self._persist_run(run)
            await self._emit_event('paused', run)
        
        logger.info(f"Paused subagent {run_id}: {reason}")
        return run

    async def steer(
        self,
        run_id: str,
        direction: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> 'SubagentRun':
        """
        Altera direção/modo de um subagente em execução.
        
        Args:
            run_id: ID do run
            direction: Nova direção (e.g., 'focus', 'explore', 'speed')
            parameters: Parâmetros adicionais
        """
        from .models import SubagentStatus, SubagentMessage, MessageType
        
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        if run.status not in [SubagentStatus.RUNNING, SubagentStatus.PAUSED]:
            raise ValueError(f"Cannot steer run with status {run.status}")
        
        # Enviar mensagem de steer
        message = SubagentMessage(
            run_id=run_id,
            parent_run_id=run.parent_id,
            message_type=MessageType.STEER,
            content=f"Steer to: {direction}",
            payload={
                'direction': direction,
                'parameters': parameters or {}
            }
        )
        
        await self._send_message(message)
        
        # Adicionar checkpoint
        run.checkpoints.append({
            'type': 'steer',
            'timestamp': datetime.utcnow().isoformat(),
            'direction': direction,
            'parameters': parameters
        })
        
        await self._persist_run(run)
        await self._emit_event('steered', run)
        
        logger.info(f"Steered subagent {run_id} to {direction}")
        
        return run

    async def restart_after_steering(
        self,
        run_id: str,
        resume_params: Optional[Dict[str, Any]] = None
    ) -> 'SubagentRun':
        """Reinicia um subagente após steering."""
        from .models import SubagentStatus
        
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        # Verificar se está em estado válido para restart
        if run.status not in [SubagentStatus.PAUSED, SubagentStatus.RUNNING]:
            raise ValueError(f"Cannot restart run with status {run.status}")
        
        # Adicionar checkpoint
        run.checkpoints.append({
            'type': 'restart_after_steering',
            'timestamp': datetime.utcnow().isoformat(),
            'resume_params': resume_params
        })
        
        # Se estiver pausado, resumir
        if run.status == SubagentStatus.PAUSED:
            return await self.resume(run_id, context_update={"_restart_reason": "Restart after steering"})
        
        await self._persist_run(run)
        await self._emit_event('restarted_after_steering', run)
        
        logger.info(f"Restarted subagent {run_id} after steering")
        
        return run

    async def finalize_after_interruption(
        self,
        run_id: str,
        outcome: 'SubagentOutcome',
        partial_results: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None
    ) -> 'SubagentRun':
        """
        Finaliza um subagente que foi interrompido.
        
        Usado quando ocorre um erro, crash, ou interrupção externa.
        """
        from .models import SubagentStatus
        
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        # Só pode finalizar se não estiver já completado
        if run.status in [SubagentStatus.COMPLETED, SubagentStatus.FAILED, SubagentStatus.CANCELLED]:
            raise ValueError(f"Cannot finalize run with status {run.status}")
        
        # Atualizar status
        run.status = SubagentStatus.COMPLETED
        run.outcome = outcome
        run.completed_at = datetime.utcnow()
        
        # Adicionar resultados parciais se houver
        if partial_results:
            run.output_data.update(partial_results)
            run.output_data['_interruption_partial_results'] = True
        
        # Adicionar checkpoint de finalização
        run.checkpoints.append({
            'type': 'finalize_after_interruption',
            'timestamp': datetime.utcnow().isoformat(),
            'outcome': outcome.value,
            'reason': reason,
            'had_partial_results': partial_results is not None
        })
        
        await self._persist_run(run)
        await self._emit_event('finalized_after_interruption', run)
        
        logger.info(f"Finalized subagent {run_id} after interruption: {outcome.value}")
        
        return run

    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    async def _load_active_runs(self):
        """Carrega runs ativas do banco para memória."""
        # Implementação depende do seu ORM (SQLAlchemy, etc.)
        # Aqui é um placeholder
        logger.info("Loading active runs from database...")
        # TODO: Implementar query real
        pass
    
    async def _persist_run(self, run: 'SubagentRun'):
        """Persiste um run no banco."""
        # TODO: Implementar persistência real
        logger.debug(f"Persisting run {run.id}")
        pass
    
    async def _persist_all_runs(self):
        """Persiste todos os runs ativos."""
        for run in self._active_runs.values():
            await self._persist_run(run)
    
    async def _count_runs(self, db, filters: List[tuple]) -> int:
        """Conta runs com filtros."""
        # TODO: Implementar query real
        return 0
    
    async def _query_runs(
        self,
        db,
        filters: List[tuple],
        limit: int,
        offset: int,
        order_by: str,
        order_dir: str
    ) -> List['SubagentRun']:
        """Query runs com filtros."""
        # TODO: Implementar query real
        return []
    
    async def _load_run_from_db(
        self,
        run_id: str,
        include_messages: bool
    ) -> Optional['SubagentRun']:
        """Carrega um run do banco."""
        # TODO: Implementar query real
        return None
    
    def _get_lock(self, run_id: str) -> asyncio.Lock:
        """Obtém lock para um run."""
        if run_id not in self._locks:
            self._locks[run_id] = asyncio.Lock()
        return self._locks[run_id]
    
    async def _execute_run(self, run_id: str):
        """Executa um run (implementação real)."""
        from .models import SubagentStatus, SubagentOutcome
        
        try:
            run = await self.get_run(run_id)
            if not run:
                logger.error(f"Run {run_id} not found for execution")
                return
            
            # Atualizar status
            run.status = SubagentStatus.RUNNING
            run.started_at = datetime.utcnow()
            await self._persist_run(run)
            await self._emit_event('started', run)
            
            # TODO: Implementar execução real do subagente
            # Isso envolveria:
            # 1. Preparar contexto e prompt
            # 2. Chamar LLM
            # 3. Processar resposta
            # 4. Executar tools se necessário
            # 5. Loop até completion
            
            logger.info(f"Executing subagent {run_id}...")
            
            # Placeholder: simular execução
            await asyncio.sleep(2)
            
            # Completar com sucesso (placeholder)
            await self.complete(
                run_id=run_id,
                outcome=SubagentOutcome.SUCCESS,
                result_data={'placeholder': True, 'result': 'Simulated execution'},
                summary="Simulated execution completed successfully"
            )
            
        except Exception as e:
            logger.exception(f"Error executing subagent {run_id}")
            
            # Finalizar com erro
            try:
                await self.finalize_after_interruption(
                    run_id=run_id,
                    outcome=SubagentOutcome.ERROR,
                    reason=str(e)
                )
            except Exception as finalize_error:
                logger.exception(f"Error finalizing subagent after execution error: {finalize_error}")
    
    async def _send_message(self, message: 'SubagentMessage'):
        """Envia mensagem para um subagente."""
        # Persistir mensagem
        await self._persist_message(message)
        
        # Emitir evento
        await self._emit_event('message', message)
        
        logger.debug(f"Message sent to {message.run_id}: {message.message_type.value}")
    
    async def _persist_message(self, message: 'SubagentMessage'):
        """Persiste mensagem no banco."""
        # TODO: Implementar persistência real
        pass
    
    async def _notify_parent(self, parent_id: str, child_run: 'SubagentRun'):
        """Notifica parent sobre completion de child."""
        from .models import SubagentMessage, MessageType
        
        message = SubagentMessage(
            run_id=parent_id,
            parent_run_id=child_run.parent_id,
            message_type=MessageType.COMPLETE,
            content=f"Child {child_run.id} completed with outcome {child_run.outcome.value}",
            payload={
                'child_run_id': child_run.id,
                'child_outcome': child_run.outcome.value if child_run.outcome else None,
                'child_result': child_run.output_data,
                'child_summary': child_run.result_summary
            }
        )
        
        await self._send_message(message)
    
    # =========================================================================
    # BACKGROUND TASKS
    # =========================================================================
    
    async def _cleanup_loop(self):
        """Loop periódico de limpeza."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_runs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in cleanup loop")
    
    async def _cleanup_old_runs(self):
        """Remove runs antigos do cache e banco."""
        # TODO: Implementar limpeza real
        logger.debug("Running cleanup of old subagent runs...")
        
        # Calcular cutoff
        cutoff = datetime.utcnow() - timedelta(days=7)
        
        # Limpar do cache
        to_remove = []
        for run_id, run in self._active_runs.items():
            if run.created_at < cutoff and run.status in [
                'completed', 'failed', 'cancelled', 'timeout'
            ]:
                to_remove.append(run_id)
        
        for run_id in to_remove:
            del self._active_runs[run_id]
            if run_id in self._locks:
                del self._locks[run_id]
        
        logger.info(f"Cleanup removed {len(to_remove)} old runs from cache")
    
    async def _orphan_recovery_loop(self):
        """Loop de recuperação de órfãos."""
        while True:
            try:
                # Verificar a cada 30 segundos
                await asyncio.sleep(30)
                await self._recover_orphans()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in orphan recovery loop")
    
    async def _recover_orphans(self):
        """Recupera runs órfãos (parent morreu)."""
        # TODO: Implementar recuperação real
        logger.debug("Checking for orphaned subagent runs...")
        
        # Buscar runs com parent_id que não existem mais
        # ou que estão em estado inconsistente por muito tempo
        
        # Marcar como orphaned e tentar finalizar gracefully
        pass

    # =========================================================================
    # EVENT SYSTEM
    # =========================================================================
    
    def on_event(self, event_type: str, handler: Callable):
        """Registra handler para um tipo de evento."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    def off_event(self, event_type: str, handler: Callable):
        """Remove handler de um tipo de evento."""
        if event_type in self._event_handlers:
            self._event_handlers[event_type] = [
                h for h in self._event_handlers[event_type]
                if h != handler
            ]
    
    async def _emit_event(self, event_type: str, data: Any):
        """Emite um evento para todos os handlers registrados."""
        if event_type not in self._event_handlers:
            return
        
        for handler in self._event_handlers[event_type]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.exception(f"Error in event handler for {event_type}")


# Singleton instance
_registry_instance: Optional[SubagentRegistry] = None


def get_registry() -> SubagentRegistry:
    """Obtém a instância singleton do registry."""
    global _registry_instance
    if _registry_instance is None:
        raise RuntimeError("SubagentRegistry not initialized. Call initialize() first.")
    return _registry_instance


def set_registry(registry: SubagentRegistry):
    """Define a instância singleton do registry."""
    global _registry_instance
    _registry_instance = registry


async def create_registry(
    db_session_factory: Callable,
    **kwargs
) -> SubagentRegistry:
    """
    Factory para criar e inicializar o registry.
    
    Args:
        db_session_factory: Factory de sessões DB
        **kwargs: Parâmetros adicionais para SubagentRegistry
    
    Returns:
        SubagentRegistry inicializado
    """
    registry = SubagentRegistry(
        db_session_factory=db_session_factory,
        **kwargs
    )
    
    await registry.initialize()
    
    set_registry(registry)
    
    return registry

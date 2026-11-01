"""
REST API for Subagent System

FastAPI routes para gerenciar subagentes.
Integrado ao Odysseus existente.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Router
router = APIRouter(
    prefix="/api/subagents",
    tags=["subagents"],
    responses={404: {"description": "Not found"}},
)


# ============================================================================
# DEPENDENCIES
# ============================================================================

async def get_registry():
    """Dependency para obter o registry"""
    from . import get_registry
    try:
        return get_registry()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Subagent system not initialized")


async def get_current_user():
    """Dependency para obter usuário atual (integrar com auth do Odysseus)"""
    # TODO: Integrar com sistema de auth do Odysseus
    # Por agora retorna mock
    return {
        "id": "user_123",
        "username": "testuser",
        "is_admin": True
    }


# ============================================================================
# DTOs (Data Transfer Objects)
# ============================================================================

from pydantic import BaseModel, Field


class SubagentConfigDTO(BaseModel):
    """DTO para configuração de subagente"""
    name: str = Field(..., description="Nome do subagente")
    description: Optional[str] = Field(None, description="Descrição")
    agent_type: str = Field("general", description="Tipo: general, research, code, etc.")
    capabilities: List[str] = Field(default_factory=list, description="Capacidades")
    allowed_tools: List[str] = Field(default_factory=list, description="Tools permitidas")
    blocked_tools: List[str] = Field(default_factory=list, description="Tools bloqueadas")
    max_iterations: int = Field(50, ge=1, le=1000, description="Máximo de iterações")
    timeout_seconds: int = Field(600, ge=10, le=36000, description="Timeout em segundos")
    max_tokens: int = Field(100000, ge=1000, description="Máximo de tokens")
    reasoning_level: str = Field("normal", description="Nível de raciocínio")
    bootstrap_mode: str = Field("full", description="Modo bootstrap")
    can_spawn_subagents: bool = Field(False, description="Pode spawnar subagentes")
    system_prompt_addition: Optional[str] = Field(None, description="Adição ao system prompt")
    context_files: List[str] = Field(default_factory=list, description="Arquivos de contexto")
    save_results: bool = Field(True, description="Salvar resultados")
    save_conversation: bool = Field(True, description="Salvar conversa")


class SpawnRequestDTO(BaseModel):
    """DTO para spawn de subagente"""
    config: SubagentConfigDTO = Field(..., description="Configuração do subagente")
    task_description: str = Field(..., min_length=1, max_length=10000, description="Descrição da tarefa")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Dados de entrada")
    parent_run_id: Optional[str] = Field(None, description="ID do run pai (se houver)")


class SubagentRunResponseDTO(BaseModel):
    """DTO para resposta de run"""
    id: str
    name: str
    parent_id: Optional[str]
    session_id: str
    user_id: str
    status: str
    outcome: Optional[str]
    agent_type: str
    task_description: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    iteration_count: int
    token_usage: int
    cost_estimate: float
    result_summary: Optional[str]
    child_ids: List[str]
    can_recover: bool
    is_orphaned: bool
    
    class Config:
        from_attributes = True


class SubagentRunDetailDTO(SubagentRunResponseDTO):
    """DTO detalhado com tudo"""
    config: SubagentConfigDTO
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error_message: Optional[str]
    error_traceback: Optional[str]
    checkpoints: List[Dict[str, Any]]
    is_checkpointed: bool
    messages: List[Dict[str, Any]]  # Simplified messages


class ListRunsResponseDTO(BaseModel):
    """DTO para listagem"""
    items: List[SubagentRunResponseDTO]
    total: int
    page: int
    pages: int
    limit: int
    offset: int


class TreeResponseDTO(BaseModel):
    """DTO para árvore"""
    id: str
    name: str
    status: str
    outcome: Optional[str]
    agent_type: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    children: List['TreeResponseDTO']


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/spawn", response_model=SubagentRunResponseDTO, status_code=201)
async def spawn_subagent(
    request: SpawnRequestDTO,
    background_tasks: BackgroundTasks,
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """
    Spawn a new subagent.
    
    Creates and starts a new subagent run with the given configuration
    and task description.
    """
    try:
        from .models import SubagentConfig
        
        # Convert DTO to internal config
        config = SubagentConfig(
            name=request.config.name,
            description=request.config.description,
            agent_type=request.config.agent_type,
            capabilities=request.config.capabilities,
            allowed_tools=request.config.allowed_tools,
            blocked_tools=request.config.blocked_tools,
            max_iterations=request.config.max_iterations,
            timeout_seconds=request.config.timeout_seconds,
            max_tokens=request.config.max_tokens,
            reasoning_level=request.config.reasoning_level,
            bootstrap_mode=request.config.bootstrap_mode,
            can_spawn_subagents=request.config.can_spawn_subagents,
            system_prompt_addition=request.config.system_prompt_addition,
            context_files=request.config.context_files,
            save_results=request.config.save_results,
            save_conversation=request.config.save_conversation,
        )
        
        # Spawn the subagent
        run = await registry.spawn(
            config=config,
            task_description=request.task_description,
            input_data=request.input_data,
            parent_run_id=request.parent_run_id,
            session_id=user.get('session_id', 'default'),
            user_id=user['id']
        )
        
        # Return response
        return SubagentRunResponseDTO(
            id=run.id,
            name=run.name,
            parent_id=run.parent_id,
            session_id=run.session_id,
            user_id=run.user_id,
            status=run.status.value,
            outcome=run.outcome.value if run.outcome else None,
            agent_type=run.config.agent_type,
            task_description=run.task_description,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            iteration_count=run.iteration_count,
            token_usage=run.token_usage,
            cost_estimate=run.cost_estimate,
            result_summary=run.result_summary,
            child_ids=run.child_ids,
            can_recover=run.can_recover,
            is_orphaned=run.is_orphaned,
        )
        
    except Exception as e:
        logger.exception("Error spawning subagent")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=ListRunsResponseDTO)
async def list_runs(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    parent_id: Optional[str] = Query(None, description="Filter by parent run ID"),
    status: Optional[List[str]] = Query(None, description="Filter by status(es)"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    created_after: Optional[datetime] = Query(None, description="Created after timestamp"),
    created_before: Optional[datetime] = Query(None, description="Created before timestamp"),
    limit: int = Query(100, ge=1, le=1000, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    order_by: str = Query("created_at", description="Field to order by"),
    order_dir: str = Query("desc", description="Order direction (asc/desc)"),
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """
    List subagent runs with filtering and pagination.
    
    Returns a paginated list of subagent runs matching the specified filters.
    """
    try:
        # Se não especificou user_id, usar o do usuário atual
        if not user_id:
            user_id = user['id']
        
        # Verificar permissões (só admin pode ver runs de outros)
        if user_id != user['id'] and not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Cannot access runs from other users")
        
        result = await registry.list_runs(
            user_id=user_id,
            session_id=session_id,
            parent_id=parent_id,
            status=status,
            agent_type=agent_type,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir
        )
        
        # Converter items para DTOs
        items = []
        for run in result['items']:
            items.append(SubagentRunResponseDTO(
                id=run.id,
                name=run.name,
                parent_id=run.parent_id,
                session_id=run.session_id,
                user_id=run.user_id,
                status=run.status.value,
                outcome=run.outcome.value if run.outcome else None,
                agent_type=run.config.agent_type,
                task_description=run.task_description,
                created_at=run.created_at,
                started_at=run.started_at,
                completed_at=run.completed_at,
                iteration_count=run.iteration_count,
                token_usage=run.token_usage,
                cost_estimate=run.cost_estimate,
                result_summary=run.result_summary,
                child_ids=run.child_ids,
                can_recover=run.can_recover,
                is_orphaned=run.is_orphaned,
            ))
        
        return ListRunsResponseDTO(
            items=items,
            total=result['total'],
            page=result['page'],
            pages=result['pages'],
            limit=result['limit'],
            offset=result['offset']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error listing runs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}", response_model=SubagentRunDetailDTO)
async def get_run(
    run_id: str,
    include_messages: bool = Query(True, description="Include message history"),
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """
    Get detailed information about a specific subagent run.
    
    Returns complete details including configuration, results, and message history.
    """
    try:
        run = await registry.get_run(run_id, include_messages=include_messages)
        
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        # Verificar permissões
        if run.user_id != user['id'] and not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Cannot access this run")
        
        # Converter mensagens se houver
        messages = []
        if include_messages and hasattr(run, 'messages'):
            for msg in run.messages:
                messages.append({
                    'id': msg.id,
                    'message_type': msg.message_type.value,
                    'direction': msg.direction,
                    'content': msg.content,
                    'payload': msg.payload,
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                    'sequence_number': msg.sequence_number,
                })
        
        return SubagentRunDetailDTO(
            id=run.id,
            name=run.name,
            parent_id=run.parent_id,
            session_id=run.session_id,
            user_id=run.user_id,
            status=run.status.value,
            outcome=run.outcome.value if run.outcome else None,
            agent_type=run.config.agent_type,
            task_description=run.task_description,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            iteration_count=run.iteration_count,
            token_usage=run.token_usage,
            cost_estimate=run.cost_estimate,
            result_summary=run.result_summary,
            child_ids=run.child_ids,
            can_recover=run.can_recover,
            is_orphaned=run.is_orphaned,
            # Detail fields
            config=SubagentConfigDTO(
                name=run.config.name,
                description=run.config.description,
                agent_type=run.config.agent_type,
                capabilities=run.config.capabilities,
                allowed_tools=run.config.allowed_tools,
                blocked_tools=run.config.blocked_tools,
                max_iterations=run.config.max_iterations,
                timeout_seconds=run.config.timeout_seconds,
                max_tokens=run.config.max_tokens,
                reasoning_level=run.config.reasoning_level,
                bootstrap_mode=run.config.bootstrap_mode,
                can_spawn_subagents=run.config.can_spawn_subagents,
                system_prompt_addition=run.config.system_prompt_addition,
                context_files=run.config.context_files,
                save_results=run.config.save_results,
                save_conversation=run.config.save_conversation,
            ),
            input_data=run.input_data,
            output_data=run.output_data,
            error_message=run.error_message,
            error_traceback=run.error_traceback,
            checkpoints=run.checkpoints,
            is_checkpointed=run.is_checkpointed,
            messages=messages,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting run {run_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/pause")
async def pause_run(
    run_id: str,
    reason: Optional[str] = None,
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """Pause a running subagent."""
    try:
        run = await registry.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        if run.user_id != user['id'] and not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Cannot modify this run")
        
        paused_run = await registry.pause(run_id, reason)
        
        return {
            "status": "success",
            "run_id": run_id,
            "new_status": paused_run.status.value,
            "reason": reason
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error pausing run {run_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    context_update: Optional[Dict[str, Any]] = None,
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """Resume a paused subagent."""
    try:
        run = await registry.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        if run.user_id != user['id'] and not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Cannot modify this run")
        
        resumed_run = await registry.resume(run_id, context_update)
        
        return {
            "status": "success",
            "run_id": run_id,
            "new_status": resumed_run.status.value
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error resuming run {run_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    reason: Optional[str] = None,
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """Cancel a running or paused subagent."""
    try:
        run = await registry.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        if run.user_id != user['id'] and not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Cannot modify this run")
        
        cancelled_run = await registry.cancel(run_id, reason)
        
        return {
            "status": "success",
            "run_id": run_id,
            "new_status": cancelled_run.status.value,
            "reason": reason
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error cancelling run {run_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/tree", response_model=TreeResponseDTO)
async def get_run_tree(
    run_id: str,
    max_depth: int = Query(10, ge=1, le=50),
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """Get the execution tree starting from a run."""
    try:
        run = await registry.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        if run.user_id != user['id'] and not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Cannot access this run")
        
        tree = await registry.get_tree(run_id, max_depth)
        
        if not tree:
            raise HTTPException(status_code=404, detail=f"Could not build tree for run {run_id}")
        
        return tree
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting tree for run {run_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(
    user_id: Optional[str] = None,
    registry=Depends(get_registry),
    user=Depends(get_current_user)
):
    """Get statistics about subagent executions."""
    try:
        # Se não especificou user_id, usar o atual
        if not user_id:
            user_id = user['id']
        
        # Verificar permissões
        if user_id != user['id'] and not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Cannot access stats for other users")
        
        # Buscar stats
        # TODO: Implementar query real de estatísticas
        stats = {
            "total_runs": 0,
            "active_runs": 0,
            "completed_runs": 0,
            "failed_runs": 0,
            "by_status": {},
            "by_agent_type": {},
            "average_duration_seconds": 0,
            "total_tokens_used": 0,
            "total_cost_estimate": 0.0,
            "period": "all_time"
        }
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting stats")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket, run_id: str):
    """WebSocket for real-time updates on a run."""
    # TODO: Implementar WebSocket para updates em tempo real
    pass


# ============================================================================
# EVENT STREAM (SSE)
# ============================================================================

@router.get("/events")
async def event_stream(
    request,
    user=Depends(get_current_user)
):
    """Server-Sent Events for real-time subagent events."""
    # TODO: Implementar SSE para eventos em tempo real
    pass


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@router.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )

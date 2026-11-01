"""
core/agents2/executor.py — Tool Executor

Executa ferramentas (tools) de forma segura:
- Shell commands
- File operations
- API requests
- Python execution
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Union

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Resultado da execução de uma tool."""
    success: bool
    output: Any
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata or {},
        }


class Tool:
    """Base para tools."""
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        timeout: int = 30,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.timeout = timeout
    
    async def execute(self, **kwargs) -> ToolResult:
        """Executa a tool."""
        raise NotImplementedError
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Valida parâmetros."""
        # Validação básica
        required = self.parameters.get("required", [])
        for param in required:
            if param not in params:
                return False
        return True
    
    def get_schema(self) -> Dict[str, Any]:
        """Retorna schema da tool."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ShellTool(Tool):
    """Executa comandos shell."""
    
    def __init__(self, timeout: int = 30, allowed_commands: Optional[Set[str]] = None):
        super().__init__(
            name="shell",
            description="Executa comandos shell",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Comando a executar"},
                    "cwd": {"type": "string", "description": "Diretório de trabalho"},
                    "timeout": {"type": "integer", "description": "Timeout em segundos"},
                },
                "required": ["command"],
            },
            timeout=timeout,
        )
        self.allowed_commands = allowed_commands
        self.blocked_patterns = [
            "rm -rf /",
            "mkfs",
            "dd if",
            ":(){:|:&};:",  # Fork bomb
        ]
    
    def _is_safe(self, command: str) -> Tuple[bool, Optional[str]]:
        """Verifica se comando é seguro."""
        # Verificar padrões bloqueados
        for pattern in self.blocked_patterns:
            if pattern in command:
                return False, f"Blocked pattern: {pattern}"
        
        # Verificar lista de comandos permitidos
        if self.allowed_commands:
            cmd = command.split()[0]
            if cmd not in self.allowed_commands:
                return False, f"Command not in allowed list: {cmd}"
        
        return True, None
    
    async def execute(self, **kwargs) -> ToolResult:
        """Executa comando shell."""
        start_time = time.time()
        
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd")
        timeout = kwargs.get("timeout", self.timeout)
        
        # Verificar segurança
        is_safe, error_msg = self._is_safe(command)
        if not is_safe:
            return ToolResult(
                success=False,
                output=None,
                error_message=f"Security check failed: {error_msg}",
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
        
        try:
            # Executar subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            
            # Aguardar com timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    output=None,
                    error_message=f"Command timed out after {timeout}s",
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
            
            # Processar resultado
            stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""
            
            success = process.returncode == 0
            
            output = {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": process.returncode,
            }
            
            return ToolResult(
                success=success,
                output=output,
                error_message=stderr_str if not success else None,
                execution_time_ms=int((time.time() - start_time) * 1000),
                metadata={"command": command, "cwd": cwd},
            )
            
        except Exception as e:
            logger.exception(f"Shell execution error: {e}")
            return ToolResult(
                success=False,
                output=None,
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )


class FileTool(Tool):
    """Operações de arquivo."""
    
    def __init__(self, base_dir: str = "."):
        super().__init__(
            name="file",
            description="Operações de leitura e escrita de arquivos",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["read", "write", "append", "list", "exists"],
                        "description": "Operação a executar",
                    },
                    "path": {"type": "string", "description": "Caminho do arquivo"},
                    "content": {"type": "string", "description": "Conteúdo para escrita"},
                },
                "required": ["operation", "path"],
            },
        )
        self.base_dir = base_dir
    
    def _resolve_path(self, path: str) -> str:
        """Resolve caminho seguro."""
        import os
        full_path = os.path.join(self.base_dir, path)
        full_path = os.path.normpath(full_path)
        
        # Verificar se está dentro de base_dir
        if not full_path.startswith(os.path.normpath(self.base_dir)):
            raise ValueError(f"Path {path} escapes base directory")
        
        return full_path
    
    async def execute(self, **kwargs) -> ToolResult:
        """Executa operação de arquivo."""
        import os
        
        operation = kwargs.get("operation")
        path = kwargs.get("path", "")
        
        try:
            full_path = self._resolve_path(path)
            
            if operation == "read":
                if not os.path.exists(full_path):
                    return ToolResult(success=False, output=None, error_message=f"File not found: {path}")
                
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
                return ToolResult(success=True, output={"content": content, "path": path})
            
            elif operation == "write":
                content = kwargs.get("content", "")
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return ToolResult(success=True, output={"path": path, "bytes_written": len(content.encode())})
            
            elif operation == "append":
                content = kwargs.get("content", "")
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                with open(full_path, 'a', encoding='utf-8') as f:
                    f.write(content)
                
                return ToolResult(success=True, output={"path": path, "bytes_appended": len(content.encode())})
            
            elif operation == "list":
                if not os.path.exists(full_path):
                    return ToolResult(success=False, output=None, error_message=f"Directory not found: {path}")
                
                items = []
                for item in os.listdir(full_path):
                    item_path = os.path.join(full_path, item)
                    items.append({
                        "name": item,
                        "type": "directory" if os.path.isdir(item_path) else "file",
                        "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None,
                    })
                
                return ToolResult(success=True, output={"path": path, "items": items})
            
            elif operation == "exists":
                exists = os.path.exists(full_path)
                return ToolResult(success=True, output={"path": path, "exists": exists})
            
            else:
                return ToolResult(success=False, output=None, error_message=f"Unknown operation: {operation}")
        
        except Exception as e:
            logger.exception(f"File operation error: {e}")
            return ToolResult(success=False, output=None, error_message=str(e))


class APITool(Tool):
    """Faz requisições HTTP."""
    
    def __init__(self, timeout: int = 30):
        super().__init__(
            name="api_request",
            description="Faz requisições HTTP/HTTPS",
            parameters={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                        "default": "GET",
                    },
                    "url": {"type": "string", "description": "URL completa"},
                    "headers": {"type": "object", "description": "Headers HTTP"},
                    "body": {"type": "string", "description": "Corpo da requisição"},
                    "timeout": {"type": "integer", "description": "Timeout em segundos"},
                },
                "required": ["url"],
            },
            timeout=timeout,
        )
    
    async def execute(self, **kwargs) -> ToolResult:
        """Executa requisição HTTP."""
        start_time = time.time()
        
        method = kwargs.get("method", "GET").upper()
        url = kwargs.get("url", "")
        headers = kwargs.get("headers", {})
        body = kwargs.get("body")
        timeout = kwargs.get("timeout", self.timeout)
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                )
                
                execution_time = int((time.time() - start_time) * 1000)
                
                return ToolResult(
                    success=response.status_code < 400,
                    output={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text,
                    },
                    execution_time_ms=execution_time,
                    metadata={
                        "method": method,
                        "url": url,
                    },
                )
        
        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output=None,
                error_message=f"Request timed out after {timeout}s",
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            logger.exception(f"API request error: {e}")
            return ToolResult(
                success=False,
                output=None,
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )


class ToolExecutor:
    """
    Executador de tools.
    
    Responsabilidades:
    - Gerenciar coleção de tools
    - Executar tools com segurança
    - Validar parâmetros
    - Gerenciar timeouts
    """
    
    def __init__(self, default_timeout: int = 30):
        """
        Inicializa executador.
        
        Args:
            default_timeout: Timeout padrão em segundos
        """
        self.default_timeout = default_timeout
        self.tools: Dict[str, Tool] = {}
        self.execution_history: List[Dict[str, Any]] = []
        
        # Registrar tools padrão
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Registra tools padrão."""
        self.register(ShellTool())
        self.register(FileTool())
        self.register(APITool())
    
    def register(self, tool: Tool) -> None:
        """
        Registra uma tool.
        
        Args:
            tool: Tool a registrar
        """
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def unregister(self, name: str) -> bool:
        """
        Remove uma tool.
        
        Args:
            name: Nome da tool
            
        Returns:
            True se removida
        """
        if name in self.tools:
            del self.tools[name]
            return True
        return False
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Retorna tool por nome."""
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Lista todas as tools."""
        return [tool.get_schema() for tool in self.tools.values()]
    
    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Executa uma tool.
        
        Args:
            tool_name: Nome da tool
            **kwargs: Parâmetros
            
        Returns:
            Resultado da execução
        """
        start_time = time.time()
        
        # Buscar tool
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error_message=f"Tool not found: {tool_name}",
                execution_time_ms=0,
            )
        
        # Validar parâmetros
        if not tool.validate_params(kwargs):
            return ToolResult(
                success=False,
                output=None,
                error_message="Invalid parameters",
                execution_time_ms=0,
            )
        
        # Executar
        try:
            result = await tool.execute(**kwargs)
            
            # Registrar no histórico
            self.execution_history.append({
                "tool": tool_name,
                "params": kwargs,
                "result": result.to_dict(),
                "timestamp": time.time(),
            })
            
            return result
            
        except Exception as e:
            logger.exception(f"Tool execution error: {e}")
            return ToolResult(
                success=False,
                output=None,
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

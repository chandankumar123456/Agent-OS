from typing import Dict, Any, List, Optional
import httpx
from ..memory.long_term import mcp_server_repo
from ..logs.logger import logger


class MCPServerRegistry:
    """Registry for MCP servers with discovery and health tracking."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def register(
        self,
        name: str,
        endpoint: str,
        tools_list: Optional[List[Dict[str, Any]]] = None,
        auth_scope: Optional[str] = None,
        version: str = "1.0.0",
    ) -> Dict[str, Any]:
        server = await mcp_server_repo.create(
            name=name,
            endpoint=endpoint,
            tools_list=tools_list,
            auth_scope=auth_scope,
            version=version,
            status="active",
        )
        self._cache[name] = {
            "id": str(server.id),
            "name": server.name,
            "endpoint": server.endpoint,
            "tools_list": server.tools_list,
            "auth_scope": server.auth_scope,
            "health_status": server.health_status,
            "version": server.version,
            "status": server.status,
            "updated_at": server.updated_at.isoformat() if server.updated_at else None,
        }
        logger.info(f"Registered MCP server: {name} at {endpoint}")
        return self._cache[name]

    async def update(
        self,
        server_id: str,
        endpoint: Optional[str] = None,
        tools_list: Optional[List[Dict[str, Any]]] = None,
        auth_scope: Optional[str] = None,
        health_status: Optional[str] = None,
        version: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        server = await mcp_server_repo.update(
            server_id=server_id,
            endpoint=endpoint,
            tools_list=tools_list,
            auth_scope=auth_scope,
            health_status=health_status,
            version=version,
            status=status,
        )
        if server:
            self._cache[server.name] = {
                "id": str(server.id),
                "name": server.name,
                "endpoint": server.endpoint,
                "tools_list": server.tools_list,
                "auth_scope": server.auth_scope,
                "health_status": server.health_status,
                "version": server.version,
                "status": server.status,
                "updated_at": server.updated_at.isoformat() if server.updated_at else None,
            }
            return self._cache[server.name]
        return None

    async def get(self, name: str) -> Optional[Dict[str, Any]]:
        if name in self._cache:
            return self._cache[name]
        server = await mcp_server_repo.get_by_name(name)
        if server:
            info = {
                "id": str(server.id),
                "name": server.name,
                "endpoint": server.endpoint,
                "tools_list": server.tools_list,
                "auth_scope": server.auth_scope,
                "health_status": server.health_status,
                "version": server.version,
                "status": server.status,
                "updated_at": server.updated_at.isoformat() if server.updated_at else None,
            }
            self._cache[name] = info
            return info
        return None

    async def list_all(self) -> List[Dict[str, Any]]:
        servers = await mcp_server_repo.list_all()
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "endpoint": s.endpoint,
                "tools_list": s.tools_list,
                "auth_scope": s.auth_scope,
                "health_status": s.health_status,
                "version": s.version,
                "status": s.status,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in servers
        ]

    async def _try_health_check(self, client: httpx.AsyncClient, endpoint: str) -> str:
        health_url = f"{endpoint}/health" if not endpoint.endswith("/") else f"{endpoint}health"
        try:
            response = await client.get(health_url)
            if response.status_code == 200:
                return "healthy"
            # Fall through to base endpoint if health subpath is unavailable
        except (httpx.TimeoutException, httpx.ConnectError):
            return "unhealthy"
        except Exception:
            pass  # Try base endpoint as fallback

        try:
            response = await client.get(endpoint)
            if response.status_code == 200:
                return "healthy"
            return "degraded"
        except (httpx.TimeoutException, httpx.ConnectError):
            return "unhealthy"
        except Exception:
            return "degraded"

    async def health_check(self, name: str) -> str:
        server = await self.get(name)
        if not server:
            return "not_found"

        async with httpx.AsyncClient(timeout=5.0) as client:
            status = await self._try_health_check(client, server["endpoint"])

        await self.update(server["id"], health_status=status)
        return status

    async def discover_tools(self, name: str) -> List[Dict[str, Any]]:
        server = await self.get(name)
        if not server:
            return []
        return server.get("tools_list") or []


mcp_registry = MCPServerRegistry()

"""MCP (Model Context Protocol) server manager.

Manages connections to external MCP servers (stdio, SSE, HTTP).
Uses centralized EventBus for broadcasting updates.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Awaitable, Any
import logging

from arche.core import event_bus

logger = logging.getLogger(__name__)


class MCPServerType(str, Enum):
    """MCP server transport types."""
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class MCPServerStatus(str, Enum):
    """MCP server connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    type: MCPServerType
    # For STDIO
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # For SSE/HTTP
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.value,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "headers": self.headers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MCPServerConfig":
        return cls(
            name=data["name"],
            type=MCPServerType(data["type"]),
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url"),
            headers=data.get("headers", {}),
        )


@dataclass
class MCPServer:
    """An MCP server instance."""
    config: MCPServerConfig
    status: MCPServerStatus = MCPServerStatus.DISCONNECTED
    tools: list[MCPTool] = field(default_factory=list)
    error_message: str | None = None
    connected_at: datetime | None = None

    # Internal
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _request_id: int = field(default=0, repr=False)
    _pending_requests: dict[int, asyncio.Future] = field(default_factory=dict, repr=False)
    _read_task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "name": self.config.name,
            "type": self.config.type.value,
            "status": self.status.value,
            "tool_count": len(self.tools),
            "tools": [t.to_dict() for t in self.tools],
            "error_message": self.error_message,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "config": self.config.to_dict(),
        }


# Legacy type alias for backward compatibility
BroadcastCallback = Callable[[str, dict], Awaitable[None]]


class MCPServerManager:
    """Manages MCP server connections.

    Uses centralized EventBus for all broadcasts.
    """

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or (Path.home() / ".claude")
        self.servers: dict[str, MCPServer] = {}
        self._lock = asyncio.Lock()

    def set_broadcast_callback(self, callback: BroadcastCallback):
        """Legacy method - broadcasts now go through event_bus."""
        pass

    async def _broadcast_update(self, server: MCPServer):
        """Broadcast server update via EventBus."""
        # Broadcast to all sessions using "*" as session_id
        await event_bus.broadcast("*", {
            "type": "mcp_server_update",
            "server": server.to_dict(),
        })

    async def add_server(self, config: MCPServerConfig) -> MCPServer:
        """Add and connect to an MCP server.

        Args:
            config: Server configuration

        Returns:
            MCPServer instance
        """
        if config.name in self.servers:
            raise ValueError(f"Server '{config.name}' already exists")

        server = MCPServer(config=config)

        async with self._lock:
            self.servers[config.name] = server

        # Connect to server
        await self._connect_server(server)
        return server

    async def _connect_server(self, server: MCPServer):
        """Connect to an MCP server."""
        server.status = MCPServerStatus.CONNECTING
        await self._broadcast_update(server)

        try:
            if server.config.type == MCPServerType.STDIO:
                await self._connect_stdio(server)
            elif server.config.type == MCPServerType.SSE:
                await self._connect_sse(server)
            elif server.config.type == MCPServerType.HTTP:
                await self._connect_http(server)

            server.status = MCPServerStatus.CONNECTED
            server.connected_at = datetime.now()
            server.error_message = None

            # Discover tools
            await self._discover_tools(server)

        except Exception as e:
            server.status = MCPServerStatus.ERROR
            server.error_message = str(e)
            logger.exception(f"Failed to connect to MCP server {server.config.name}: {e}")

        await self._broadcast_update(server)

    async def _connect_stdio(self, server: MCPServer):
        """Connect to STDIO-based MCP server."""
        if not server.config.command:
            raise ValueError("STDIO server requires 'command'")

        # Prepare environment
        import os
        env = os.environ.copy()
        env.update(server.config.env)

        # Start subprocess
        process = await asyncio.create_subprocess_exec(
            server.config.command,
            *server.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        server._process = process

        # Start reading task
        server._read_task = asyncio.create_task(self._read_stdio(server))

        # Initialize connection
        await self._send_request(server, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "arche-interactive",
                "version": "1.0.0",
            },
        })

    async def _connect_sse(self, server: MCPServer):
        """Connect to SSE-based MCP server."""
        # SSE implementation would use aiohttp or similar
        # For now, mark as not implemented
        raise NotImplementedError("SSE transport not yet implemented")

    async def _connect_http(self, server: MCPServer):
        """Connect to HTTP-based MCP server."""
        # HTTP implementation would use aiohttp or similar
        # For now, mark as not implemented
        raise NotImplementedError("HTTP transport not yet implemented")

    async def _read_stdio(self, server: MCPServer):
        """Read messages from STDIO server."""
        if not server._process or not server._process.stdout:
            return

        try:
            while True:
                line = await server._process.stdout.readline()
                if not line:
                    break

                try:
                    message = json.loads(line.decode('utf-8'))
                    await self._handle_message(server, message)
                except json.JSONDecodeError:
                    continue

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading from MCP server {server.config.name}: {e}")
            server.status = MCPServerStatus.ERROR
            server.error_message = str(e)
            await self._broadcast_update(server)

    async def _handle_message(self, server: MCPServer, message: dict):
        """Handle incoming MCP message."""
        if "id" in message:
            # Response to a request
            request_id = message["id"]
            if request_id in server._pending_requests:
                future = server._pending_requests.pop(request_id)
                if "error" in message:
                    future.set_exception(Exception(message["error"].get("message", "Unknown error")))
                else:
                    future.set_result(message.get("result"))
        elif "method" in message:
            # Notification from server
            logger.debug(f"MCP notification: {message['method']}")

    async def _send_request(self, server: MCPServer, method: str, params: dict | None = None) -> Any:
        """Send a request to MCP server."""
        if server.config.type != MCPServerType.STDIO:
            raise NotImplementedError("Only STDIO transport is implemented")

        if not server._process or not server._process.stdin:
            raise RuntimeError("Server not connected")

        server._request_id += 1
        request_id = server._request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        server._pending_requests[request_id] = future

        # Send request
        data = json.dumps(request) + "\n"
        server._process.stdin.write(data.encode('utf-8'))
        await server._process.stdin.drain()

        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            server._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Request {method} timed out")

    async def _discover_tools(self, server: MCPServer):
        """Discover available tools from server."""
        try:
            result = await self._send_request(server, "tools/list", {})
            tools = result.get("tools", []) if result else []

            server.tools = [
                MCPTool(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in tools
            ]

            logger.info(f"Discovered {len(server.tools)} tools from {server.config.name}")

        except Exception as e:
            logger.warning(f"Failed to discover tools from {server.config.name}: {e}")

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on an MCP server.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        server = self.servers.get(server_name)
        if not server:
            raise ValueError(f"Server '{server_name}' not found")

        if server.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Server '{server_name}' is not connected")

        result = await self._send_request(server, "tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        return result

    def get_server(self, name: str) -> MCPServer | None:
        """Get server by name."""
        return self.servers.get(name)

    def list_servers(self) -> list[MCPServer]:
        """List all servers."""
        return list(self.servers.values())

    def get_all_tools(self) -> list[dict]:
        """Get all tools from all connected servers."""
        tools = []
        for server in self.servers.values():
            if server.status == MCPServerStatus.CONNECTED:
                for tool in server.tools:
                    tools.append({
                        "server": server.config.name,
                        **tool.to_dict(),
                    })
        return tools

    async def remove_server(self, name: str) -> bool:
        """Remove and disconnect an MCP server."""
        server = self.servers.get(name)
        if not server:
            return False

        await self._disconnect_server(server)

        async with self._lock:
            del self.servers[name]

        return True

    async def _disconnect_server(self, server: MCPServer):
        """Disconnect from an MCP server."""
        # Cancel read task
        if server._read_task and not server._read_task.done():
            server._read_task.cancel()
            try:
                await server._read_task
            except asyncio.CancelledError:
                pass

        # Kill process
        if server._process:
            try:
                server._process.terminate()
                await asyncio.wait_for(server._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                server._process.kill()
            except Exception:
                pass
            server._process = None

        server.status = MCPServerStatus.DISCONNECTED
        server.tools = []
        await self._broadcast_update(server)

    async def load_from_config(self):
        """Load MCP servers from Claude CLI config."""
        config_file = self.config_dir / "mcp_servers.json"
        if not config_file.exists():
            return

        try:
            with open(config_file) as f:
                data = json.load(f)

            for name, server_data in data.items():
                config = MCPServerConfig(
                    name=name,
                    type=MCPServerType(server_data.get("type", "stdio")),
                    command=server_data.get("command"),
                    args=server_data.get("args", []),
                    env=server_data.get("env", {}),
                    url=server_data.get("url"),
                    headers=server_data.get("headers", {}),
                )
                await self.add_server(config)

        except Exception as e:
            logger.warning(f"Failed to load MCP config: {e}")

    async def save_config(self):
        """Save MCP servers to config file."""
        config_file = self.config_dir / "mcp_servers.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            name: server.config.to_dict()
            for name, server in self.servers.items()
        }

        with open(config_file, 'w') as f:
            json.dump(data, f, indent=2)

    async def shutdown(self):
        """Shutdown all MCP servers."""
        for server in list(self.servers.values()):
            await self._disconnect_server(server)


# Global instance
mcp_server_manager = MCPServerManager()

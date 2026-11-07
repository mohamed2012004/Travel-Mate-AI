import logging
import os
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import certifi
from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from langchain_mcp_adapters.tools import load_mcp_tools

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
WEATHERAPI_API_KEY = os.getenv("WEATHERAPI_API_KEY") or os.getenv("OPENWEATHER_API_KEY")

MCP_SERVERS = {
    "tavily": {
        "transport": "streamable_http",
        "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
    },
    "weather": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(BASE_DIR / "custom_weather_mcp_server.py")],
        "env": {"WEATHERAPI_API_KEY": WEATHERAPI_API_KEY},
    },
}


async def log_tool_calls(
    request: MCPToolCallRequest,
    handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
) -> MCPToolCallResult:
    """Terminal log for every real API call (Tavily/Weather)."""

    started = time.perf_counter()
    logger.info(
        "[api] CALL server=%s tool=%s args=%s",
        request.server_name, request.name, str(request.args)[:300],
    )
    try:
        result = await handler(request)
    except Exception as error:
        logger.error(
            "[api] FAILED server=%s tool=%s elapsed=%.1fs error=%s",
            request.server_name, request.name, time.perf_counter() - started, error,
        )
        raise

    logger.info(
        "[api] OK server=%s tool=%s elapsed=%.1fs result=%s",
        request.server_name, request.name, time.perf_counter() - started,
        str(result)[:300].replace("\n", " "),
    )
    return result


@asynccontextmanager
async def mcp_tools(server_name: str) -> AsyncIterator[list[BaseTool]]:
    """Yield MCP tools bound to ONE persistent session.

    Tools created via load_mcp_tools(session, ...) reuse this session
    for every tool call. The old client.get_tools() created a new
    session (stdio spawn -> os.access) on EVERY tool call, which
    LangGraph Dev blocks. The session must stay open while
    create_agent(tools=...) runs, so callers use:
        async with mcp_tools("weather") as tools:
            agent = create_agent(model, tools=tools, ...)
            await agent.ainvoke(...)
    """

    client = MultiServerMCPClient(
        {server_name: MCP_SERVERS[server_name]},
        tool_interceptors=[log_tool_calls],
    )
    async with client.session(server_name) as session:
        tools = await load_mcp_tools(
            session, server_name=server_name, tool_interceptors=[log_tool_calls]
        )
        logger.info("[mcp] persistent session %s: %s", server_name, [t.name for t in tools])
        yield tools

import os
import sys
from pathlib import Path

import certifi
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
WEATHERAPI_API_KEY = os.getenv("WEATHERAPI_API_KEY") or os.getenv("OPENWEATHER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# LLM
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=GROQ_API_KEY
)


# One MCP server per external API. Each agent only receives the tools of
# the server it is responsible for, so every API stays behind an MCP tool.
MCP_SERVERS = {
    "tavily": {
        "transport": "streamable_http",
        "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}"
    },

    "aviationstack": {
        "transport": "stdio",
        "command": "uvx",
        "args": [
            "aviationstack-mcp"
        ],
        "env": {
            "AVIATION_STACK_API_KEY": AVIATION_STACK_API_KEY
        }
    },

    "weather": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [
            str(BASE_DIR / "custom_weather_mcp_server.py")
        ],
        "env": {
            "WEATHERAPI_API_KEY": WEATHERAPI_API_KEY
        }
    }
}


client = MultiServerMCPClient(MCP_SERVERS)


# Tools are cached per server: a fresh MCP session is opened on every tool
# call, so the tool objects themselves can be reused by the agents.
_tools_cache: dict[str, list] = {}


async def get_server_tools(server_name: str):
    """Return the MCP tools exposed by a single server."""

    if server_name not in _tools_cache:
        _tools_cache[server_name] = await client.get_tools(server_name=server_name)

    return _tools_cache[server_name]


async def get_tavily_tools():
    """Web search tools used by the hotel agent."""

    return await get_server_tools("tavily")


async def get_aviation_tools():
    """AviationStack airport / airline / flight tools used by the flight agent."""

    return await get_server_tools("aviationstack")


async def get_weather_tools():
    """Custom weather MCP tools used by the weather agent."""

    return await get_server_tools("weather")


async def get_all_tools():
    """Print every tool available across all MCP servers."""

    tools = await client.get_tools()

    print("\nAvailable MCP Tools:\n")

    for tool in tools:
        print(tool.name)

    return tools

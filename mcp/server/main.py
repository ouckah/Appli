from mcp.server.fastmcp import FastMCP
from tools.registry import register_tools

mcp = FastMCP("appli")

register_tools(mcp)

mcp.run()
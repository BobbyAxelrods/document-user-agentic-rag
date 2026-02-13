
import os
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseServerParams, StdioServerParameters


PATH_TO_MCP_SCRIPT = os.path.join(os.path.dirname(__file__), 'server.py')
print('mcp_server_path', PATH_TO_MCP_SCRIPT)
mcp_tool = MCPToolset(
    connection_params=StdioServerParameters(
        command='python',
        args=[
            PATH_TO_MCP_SCRIPT
        ],
    ),
   
    tool_filter=["register_sp_booking_tools", "register_doctor_finder_tools"]
)

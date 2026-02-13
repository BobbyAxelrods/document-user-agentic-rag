
import os
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseServerParams, StdioServerParameters


PATH_TO_MCP_SCRIPT = os.path.join(os.path.dirname(__file__), 'mysql_server.py')
print('mcp_server_path', PATH_TO_MCP_SCRIPT)
mcp_tool = MCPToolset(
    # connection_params=StdioServerParameters(
    #     command='python',
    #     args=[
    #         PATH_TO_MCP_SCRIPT
    #     ],
    # ),
    connection_params=SseServerParams(
        url="https://gc-mcp-mock-1091311790583.asia-southeast1.run.app/policy/",
        timeout=15
        
        # url="http://localhost:8080/policy"
    ),
    tool_filter=["get_user_policy_and_products"]
)

from mcp.server.fastmcp import FastMCP
from tools.doctor_finder import register_doctor_finder_tools
#from tools.sp_appointment import register_sp_appointment_tools
from tools.sp_booking import register_sp_booking_tools


mcp = FastMCP("PHKL MCP (Modular)", json_response=True)

register_doctor_finder_tools(mcp)
#register_sp_appointment_tools(mcp)
register_sp_booking_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="stdio")
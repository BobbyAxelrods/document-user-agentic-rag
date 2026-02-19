import os
from typing import Dict, Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("prudential-mcp-policy", json_response=True)


MOCK_POLICIES: Dict[str, Any] = {
    "test_123": {
        "user_id": "test_123",
        "customer_name": "Alice Tan",
        "segment": "PRUHealth VIP",
        "policies": [
            {
                "policy_id": "POL-1234567890",
                "product_name": "PRUHealth Comprehensive",
                "status": "active",
                "coverage": {
                    "medical": "HKD 1,000,000 annual limit",
                    "room_type": "standard ward",
                    "co_payment": "20%",
                },
                "premium": {
                    "amount": "HKD 1,200",
                    "frequency": "monthly",
                },
            }
        ],
    },
    "test_456": {
        "user_id": "test_456",
        "customer_name": "Brian Wong",
        "segment": "PRUHealth Standard",
        "policies": [
            {
                "policy_id": "POL-4561237890",
                "product_name": "PRUHealth Essential",
                "status": "active",
                "coverage": {
                    "medical": "HKD 500,000 annual limit",
                    "room_type": "semi-private",
                    "co_payment": "10%",
                },
                "premium": {
                    "amount": "HKD 800",
                    "frequency": "monthly",
                },
            }
        ],
    },
    "test_789": {
        "user_id": "test_789",
        "customer_name": "Charlie Lee",
        "segment": "PRUHealth New Joiner",
        "policies": [
            {
                "policy_id": "POL-7894561230",
                "product_name": "PRUHealth Starter",
                "status": "pending_issuance",
                "coverage": {
                    "medical": "HKD 300,000 annual limit",
                    "room_type": "general ward",
                    "co_payment": "30%",
                },
                "premium": {
                    "amount": "HKD 500",
                    "frequency": "monthly",
                },
            }
        ],
    },
}


@mcp.tool()
def get_user_policy_and_products(user_id: str) -> Dict[str, Any]:
    record = MOCK_POLICIES.get(user_id)
    if record is not None:
        return {
            "status": "success",
            "data": record,
            "message": f"Mock policy data found for user_id={user_id}",
        }
    return {
        "status": "not_found",
        "data": None,
        "message": f"No mock policy data for user_id={user_id}",
    }


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


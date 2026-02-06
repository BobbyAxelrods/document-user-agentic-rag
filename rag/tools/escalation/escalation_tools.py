from typing import Dict, Any

def escalate_to_live_agent(reason: str, context: str = "") -> Dict[str, Any]:
    """
    Escalates the current conversation to a live human agent.
    Use this when the user explicitly asks for a human or when the query is too complex to handle automatically.
    
    Args:
        reason: The reason for escalation (e.g., "User request", "Complex query").
        context: Additional context or the specific query that triggered the escalation.
        
    Returns:
        A dictionary with the escalation status and mock ticket details.
    """
    import random
    import string
    
    ticket_id = "TKT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    policy_id = "POL-" + ''.join(random.choices(string.digits, k=10))
    
    # Mock MCP Data Sample
    mcp_data_sample = {
        "channel": "live_chat",
        "priority": "high" if "urgent" in context.lower() else "normal",
        "customer_segment": "vip" if random.choice([True, False]) else "standard",
        "routing_queue": "general_inquiries",
        "system_metadata": {
            "source": "rag_agent_v4",
            "handoff_timestamp": "2024-05-21T10:00:00Z" # In real scenario this would be dynamic
        }
    }
    
    return {
        "status": "success",
        "message": "Your request has been escalated to a live agent.",
        "ticket_id": ticket_id,
        "policy_id": policy_id,
        "mcp_data_sample": mcp_data_sample,
        "estimated_wait_time": "5 minutes",
        "reason": reason,
        "context_captured": context
    }

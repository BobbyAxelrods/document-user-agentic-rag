import os
from typing import Optional
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.memory import InMemoryMemoryService
from google.adk.models import LlmRequest, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import VertexAiSessionService
from google.genai import types
from dotenv import load_dotenv
from rag.config import AGENT_OUTPUT_KEY, PROJECT_ID, LOCATION, USE_VERTEX_MEMORY

from rag.tools.corpus.corpus_tools import (
    create_corpus,
    update_corpus,
    list_corpora,
    get_corpus,
    delete_corpus,
    import_files,
    list_files,
    get_file,
    delete_file_from_corpus,
    query_corpus,
)

# from rag.tools.mcp_tool.mcp_tools import mcp_tool

from rag.tools.lifecycle.lifecycle_main import automated_evaluation_testcase
from rag.tools.tone_management.tone_tools import (
    tone_management, 
    get_tone_guidelines_for_category, 
    apply_tone_guidelines, 
    validate_tone_compliance,
    classify_tone_group,
    get_tone_guidelines_by_group
)
from rag.tools.storage.storage_tools import create_gcs_bucket, list_blobs
from rag.tools.escalation.escalation_tools import escalate_to_live_agent
from rag.tools.policy.policy_tools import analyze_policy_and_risk

_rag_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(_rag_env_path):
    load_dotenv(_rag_env_path)
else:
    load_dotenv()

SANDBOX_ENV = os.getenv("SANDBOX", "false")
AZURE_MODEL_NAME = os.getenv("AZURE", "azure/gpt-4o")
model = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def load_instructions(instruction_file_name):
    path_of_instructions = os.path.join(os.path.dirname(__file__), f"{instruction_file_name}.md")
    try:
        with open(path_of_instructions, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "You are error reading instruction"


def _extract_user_message_text(llm_request: LlmRequest) -> str:
    texts: list[str] = []
    contents = getattr(llm_request, "contents", None) or []
    for content in contents:
        parts = getattr(content, "parts", None) or []
        for part in parts:
            value = getattr(part, "text", None)
            if isinstance(value, str) and value:
                texts.append(value)
    return "\n".join(texts).strip()


def prompt_injection_guard(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    user_text = _extract_user_message_text(llm_request)
    if not user_text:
        return None

    last_query = user_text.strip().splitlines()[-1].strip()
    if not last_query:
        return None

    result = analyze_policy_and_risk(last_query)
    query_type = result.get("query_type")
    fast_path = result.get("fast_path")
    risk_level = result.get("risk_level") or "low"

    if query_type in ("style_disallowed", "policy_violation", "prompt_injection") or fast_path == "policy_violation" or risk_level in ("high", "critical"):
        safe_text = (
            "I cannot follow that request because it violates my safety and confidentiality rules. "
            "Please rephrase your request to focus on Prudential policy, claims, or health support questions."
        )
        content = types.Content(
            role="model",
            parts=[types.Part(text=safe_text)],
        )
        return LlmResponse(content=content)

    return None


root_agent = Agent(
    name="pru_master_orchestrator",
    model=model,
    description="master orchestrator for Prudential multi-agent workflow",
    instruction=load_instructions("instruction"),
    tools=[
        analyze_policy_and_risk,
        classify_tone_group,
        get_tone_guidelines_by_group,
        apply_tone_guidelines,
        validate_tone_compliance,
        escalate_to_live_agent,
        # mcp_tool,
        query_corpus,
    ],
    output_key="root_agent_output",
    before_model_callback=prompt_injection_guard,
)


rag_worker_agent = Agent(
    name="pru_rag_worker",
    model=model,
    description="specialized worker for corpus lifecycle and knowledge retrieval",
    instruction="You are the RAG worker. Focus on corpus, files and knowledge retrieval only.",
    tools=[
        create_corpus,
        update_corpus,
        list_corpora,
        get_corpus,
        delete_corpus,
        import_files,
        list_files,
        get_file,
        delete_file_from_corpus,
        query_corpus,
        automated_evaluation_testcase,
    ],
    output_key="rag_agent_output",
)


mcp_worker_agent = Agent(
    name="pru_mcp_worker",
    model=model,
    description="specialized worker for policy data and MCP tools",
    instruction="You are the MCP worker. Use policy data tools to fetch user policy and product information.",
    tools=[
        # mcp_tool,
        analyze_policy_and_risk,
    ],
    output_key="mcp_agent_output",
)


system_worker_agent = Agent(
    name="pru_system_worker",
    model=model,
    description="specialized worker for storage and internal operations",
    instruction="You are the system worker. Focus on storage, buckets and internal system operations.",
    tools=[
        create_gcs_bucket,
        list_blobs,
        tone_management,
        get_tone_guidelines_for_category,
        get_tone_guidelines_by_group,
    ],
    output_key="storage_agent_output",
)


conversation_worker_agent = Agent(
    name="pru_conversation_worker",
    model=model,
    description="specialized worker for greetings, restarts and light conversation",
    instruction="You are the conversation worker. Handle greetings, restarts and light conversation with empathy.",
    tools=[
        classify_tone_group,
        get_tone_guidelines_by_group,
        apply_tone_guidelines,
        validate_tone_compliance,
        escalate_to_live_agent,
    ],
    output_key="conversation_agent_output",
)


def create_session_service(agent_engine_id: str | None = None) -> VertexAiSessionService:
    engine_id = agent_engine_id or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    if not engine_id:
        raise ValueError("agent_engine_id or GOOGLE_CLOUD_AGENT_ENGINE_ID must be set for VertexAiSessionService")
    return VertexAiSessionService(
        project=PROJECT_ID,
        location=LOCATION,
        agent_engine_id=engine_id,
    )

# ----------------- MULTI AGENT SECTION PLAN 
# 1 Safety Risk Analyzer
# parallel_worker_agent = ParallelAgent(
#     name="pru_safety",
#     model=model,
#     description="",
#     instructions="",
#     tools=[analyze_policy_and_risk, escalate_to_live_agent],
#     output_key="policy_view",
# )

# 2 Parallel Workers 




# ------------------ MULTI AGENT END 
def create_memory_service(agent_engine_id: str | None = None):
    return InMemoryMemoryService()


def create_runner(app_name: str, agent_engine_id: str | None = None) -> Runner:
    session_service = create_session_service(agent_engine_id=agent_engine_id)
    memory_service = create_memory_service(agent_engine_id=agent_engine_id)
    return Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        memory_service=memory_service,
    )

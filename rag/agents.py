import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm 
from google.adk.models import Gemini
from dotenv import load_dotenv
from rag.config import AGENT_OUTPUT_KEY

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
from rag.tools.lifecycle.lifecycle_main import automated_evaluation_testcase
from rag.tools.tone_management.tone_tools import tone_management
from rag.tools.storage.storage_tools import create_gcs_bucket, list_blobs
from rag.tools.escalation.escalation_tools import escalate_to_live_agent

_rag_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(_rag_env_path):
    load_dotenv(_rag_env_path)
else:
    load_dotenv()

SANDBOX_ENV = os.getenv("SANDBOX", "false")
AZURE_MODEL_NAME = os.getenv("AZURE", "azure/gpt-4o")

if SANDBOX_ENV == "true":
    model = Gemini(model="gemini-1.5-pro-001")
else:
    model = LiteLlm(model=AZURE_MODEL_NAME)


def load_instructions(instruction_file_name):
    path_of_instructions = os.path.join(os.path.dirname(__file__), f"{instruction_file_name}.md")
    try:
        with open(path_of_instructions, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"You are error reading instruction"

root_agent = Agent(
    name= "pru_rag_manager",
    model=model,
    description="managing rag data source lifecycle",
    instruction = load_instructions("instruction"),
    tools = [
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
        tone_management,
        create_gcs_bucket,
        list_blobs,
        escalate_to_live_agent,
    ],
    output_key=AGENT_OUTPUT_KEY
)

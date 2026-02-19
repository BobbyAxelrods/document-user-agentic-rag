## https://docs.cloud.google.com/agent-builder/agent-engine/deploy?_gl=1*1etp7z*_ga*MTYyNTAzNDQxNi4xNzY1NjE5Nzc3*_ga_WH2QY8WWF5*czE3NzEyNDQ5OTUkbzEwMCRnMSR0MTc3MTI0NjI5MCRqNTgkbDAkaDA.#from-an-agent-object
# pip install google-cloud-aiplatform[agent_engines,adk]
# https://raphaelmansuy.github.io/adk_training/docs/hello_world_agent
from dotenv import load_dotenv

from rag.config import PROJECT_ID

load_dotenv()

import os 
PROJECT_ID="prudential-poc-484904"
LOCATION_ID="europe-west2"

vertexai.init(project=PROJECT_ID, location=LOCATION_ID)
client = vertexai.preview.get_genai_client()

local_agent = ADKRunner()

requirements = [
    "google-adk",
    "google-cloud-aiplatform[adk,agent-engines]",
    "google-cloud-storage",
    "litellm",
    "openai",
    "pydantic",
    "deprecated",
    "google-genai",
    "cloud-sql-python-connector[pg8000]",
    "pandas",
    "openpyxl",
    "mcp",
]
remote_agent = client.agent_engines.create(
    agent=local_agent,
    config={
        "requirements": requirements,
        "display_name": "Healthcare AI Assistant",
        "description": "PRUHealth Team - Healthcare AI Assistant with ADK, LiteLLM, and GCS",
        "env_vars": env_vars,
        "agent_framework": "google-adk",
        "labels": {
            "env": "production",
            "version": "1.0",
            "team": "healthcare-ai"
        },
        # Resource controls
        "min_instances": 1,
        "max_instances": 10,
        "resource_limits": {"cpu": "4", "memory": "8Gi"},
        "container_concurrency": 9,
        # Optional: Agent identity
        # "identity_type": "AGENT_IDENTITY",
        # Optional: Custom service account
        # "service_account": "your-service-account@project.iam.gserviceaccount.com",
    },
)
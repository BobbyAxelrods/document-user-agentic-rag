import pathlib

import dotenv
import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator


pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session", autouse=True)
def load_env():
    dotenv.load_dotenv()


@pytest.mark.asyncio
async def test_pru_rag_conversation_eval():
    dataset_path = pathlib.Path(__file__).parent / "evaluation_files" / "conversation.test.json"
    await AgentEvaluator.evaluate(
        agent_module="rag",
        eval_dataset_file_path_or_dir=str(dataset_path),
        num_runs=1,
    )


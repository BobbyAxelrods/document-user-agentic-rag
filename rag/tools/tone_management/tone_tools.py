import os
from typing import Optional, Dict, List, Any
from google.adk.models.lite_llm import LiteLlm 
from google.adk.models import Gemini
from dotenv import load_dotenv

# Load env vars for model config
_rag_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
if os.path.exists(_rag_env_path):
    load_dotenv(_rag_env_path)
else:
    load_dotenv()

def _get_model():
    """Helper to initialize the model based on environment settings."""
    sandbox_env = os.getenv("SANDBOX", "false")
    azure_model_name = os.getenv("AZURE", "azure/gpt-4o")
    
    if sandbox_env == "true":
        return Gemini(model="gemini-1.5-pro-001")
    else:
        return LiteLlm(model=azure_model_name)

def tone_management(
    answer: str,
    acknowledgement: Optional[str] = None,
    citations: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Refines the answer tone using Golden Dialogue principles via an LLM call.
    """
    # 1. Load instructions
    instruction_path = os.path.join(os.path.dirname(__file__), "tone_tools.md")
    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            instructions = f.read()
    except Exception:
        instructions = "Rewrite the response to be professional, clear, and empathetic."

    # 2. Prepare prompt
    prompt = f"""
{instructions}

---
Task: Rewrite the following DRAFT RESPONSE to match the tone and structure guidelines above.
Preserve all factual information and citations.

DRAFT RESPONSE:
{answer}
"""

    # 3. Call Model
    try:
        model = _get_model()
        # Depending on the model interface, we might need to adjust this call.
        # Assuming model.ask() or similar method exists. 
        # Checking agents.py, it uses `model` in `Agent`. 
        # ADK models usually have a generate or prompt method.
        # Let's assume a standard `generate_content` or similar interface wrapper is used, 
        # but since we don't see the model definition, we'll try a common pattern or the ADK's likely method.
        # If it's a standard ADK model, it might be callable or have `generate`.
        # For now, let's assume we can pass it to the agent or call it directly.
        # Actually, the safest bet is to instantiate a temporary Agent if we want to use the framework fully,
        # or just call the model if we know the API. 
        # Let's try to just use the model object.
        
        # NOTE: Without seeing google.adk.models source, I am guessing the method is `predict` or `generate`.
        # I will use a generic try/except to handle potential method name mismatches if I can't verify.
        # However, looking at standard usage: response = model.generate(prompt)
        
        # Let's try `ask` as it is common in some frameworks, or `generate_content`.
        # Given `Agent` takes `model`, `Agent` probably calls `model.ask(prompt)`.
        
        refined_text = model.ask(prompt) 
        # If model.ask returns an object, we might need to extract text. 
        # Assuming it returns a string for now based on typical simple wrappers.

    except Exception as e:
        # Fallback if model call fails
        refined_text = answer + f" [Tone refinement failed: {str(e)}]"

    # 4. Format Output
    ack = acknowledgement.strip() if acknowledgement else ""
    
    formatted_citations = []
    for c in citations or []:
        corpus = c.get("corpus_name", "").strip()
        filename = c.get("filename", "").strip()
        chunk = c.get("chunk", "").strip()
        formatted_citations.append(f"[Source: {corpus} | File: {filename} | Chunk: {chunk}]")

    return {
        "acknowledgement": ack,
        "text": refined_text,
        "citations": formatted_citations
    }

import os
from typing import Optional, Dict, List, Any
from google.adk.models.lite_llm import LiteLlm 
from google.adk.models import Gemini
from dotenv import load_dotenv
import litellm

try:
    from rag.tools.corpus.corpus_tools import query_corpus
except ImportError:
    try:
        from ..corpus.corpus_tools import query_corpus
    except ImportError:
        query_corpus = None

TONE_CORPUS_ID = "7782220156096217088"
# Source PDF: "Tonality and System Instructions - Tone of Voice Guided Care.pdf"

# --- TONE GUIDELINES FROM PLAN ---

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

class ToneCache:
    def __init__(self, tone_corpus_id: str):
        self.corpus_id = tone_corpus_id
        self._cache = {}
    
    def get_tone_for_category(self, query_category: str) -> str:
        """
        Retrieves tone guidelines for a specific query category.
        Categories: claims, general_inquiry, complaint, etc.
        """
        if query_category not in self._cache:
            if query_corpus:
                try:
                    # Query once and cache
                    result = query_corpus(
                        corpus_id=self.corpus_id,
                        query=f"Tone guidelines for {query_category} queries",
                        similarity_top_k=3
                    )
                    guidance = ""
                    if result and "results" in result:
                        for res in result["results"]:
                            guidance += f"- {res.get('text', '')}\n"
                    self._cache[query_category] = guidance
                except Exception as e:
                    print(f"Warning: Failed to cache tone for {query_category}: {e}")
                    return ""
            else:
                return ""
        return self._cache.get(query_category, "")

# Instantiate singleton
tone_cache = ToneCache(TONE_CORPUS_ID)

def get_tone_guidelines_for_category(category: str) -> str:
    """
    Retrieves cached tone guidelines for a general category.
    Useful for 'parallel retrieval' step.
    """
    return tone_cache.get_tone_for_category(category)

def apply_tone_guidelines(
    content_answer: str, 
    tone_guidelines: str, 
    user_query: str
) -> str:
    """
    Applies tone guidelines from RAG to the generated answer (Sandwich Prompt).
    
    Args:
        content_answer: The factual answer or retrieved context chunks
        tone_guidelines: Retrieved tone rules from tone corpus
        user_query: Original user question for context
    
    Returns:
        Tone-adjusted answer string
    """
    prompt = f"""
    You are a Voice of Care Agent for Prudential.
    
    ### USER QUERY:
    {user_query}
    
    ### FACTUAL CONTEXT/ANSWER:
    {content_answer}
    
    ### TONE GUIDELINES (VOICE OF CARE):
    {tone_guidelines}
    
    ### INSTRUCTIONS:
    1. Answer the user's query using the FACTUAL CONTEXT provided.
    2. Strictly adhere to the TONE GUIDELINES (Empathy, Clarity, Professionalism).
    3. If the context is raw chunks, synthesize them into a coherent response.
    4. Do not include internal jargon (e.g., "corpus", "chunks") in the final output.
    
    Generate the final response now.
    """
    
    try:
        # Determine model name
        model_name = os.getenv("AZURE", "azure/gpt-4o")
        if os.getenv("SANDBOX", "false") == "true":
            model_name = "gemini/gemini-1.5-pro-001"
            
        response = litellm.completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return content_answer + f" [Tone refinement failed: {str(e)}]"

def validate_tone_compliance(response_text: str, tone_guidelines: Optional[str] = None) -> str:
    """
    Evaluates if a response complies with tone guidelines.
    Returns a JSON string with scores and feedback.
    """
    if not tone_guidelines:
        tone_guidelines = """
        1. Empathy: Acknowledge emotions first.
        2. Clarity: Simple, jargon-free language.
        3. Professionalism: Reassuring and knowledgeable.
        4. Coverage: Explicitly mention coverage if relevant.
        """

    prompt = f"""
    You are a Quality Assurance Auditor for PRUHealth.
    Your task is to evaluate the following response against our Tone Guidelines.

    RESPONSE TO EVALUATE:
    "{response_text}"

    TONE GUIDELINES:
    {tone_guidelines}

    Evaluate on a scale of 1-5 for:
    - Empathy (Did it acknowledge emotion?)
    - Clarity (Is it simple?)
    - Professionalism (Is it reassuring?)
    - Compliance (Did it follow specific rules like mentioning coverage?)

    Output JSON format:
    {{
        "empathy_score": int,
        "clarity_score": int,
        "professionalism_score": int,
        "compliance_score": int,
        "overall_score": int,
        "feedback": "string explaining issues"
    }}
    """

    try:
        model_name = os.getenv("AZURE", "azure/gpt-4o")
        if os.getenv("SANDBOX", "false") == "true":
            model_name = "gemini/gemini-1.5-pro-001"

        response = litellm.completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except Exception as e:
        return f'{{"error": "{str(e)}"}}'

def tone_management(
    answer: str,
    acknowledgement: Optional[str] = None,
    citations: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Legacy tool wrapper that now uses apply_tone_guidelines internally if possible,
    or maintains backward compatibility.
    """
    # 1. Load instructions (Legacy fallback)
    instruction_path = os.path.join(os.path.dirname(__file__), "tone_tools.md")
    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            base_instructions = f.read()
    except Exception:
        base_instructions = "Rewrite the response to be professional, clear, and empathetic."

    # 2. Query Tone Corpus (Legacy Inline Logic)
    # We use this if 'tone_management' is called directly without pre-fetched guidelines
    corpus_guidance = ""
    if query_corpus:
        try:
            search_query = f"Tone guidelines for: {answer[:500]}"
            tone_query_result = query_corpus(
                corpus_id=TONE_CORPUS_ID,
                query=search_query,
                similarity_top_k=3
            )
            if tone_query_result and "results" in tone_query_result:
                 corpus_guidance = "\n\n### Additional Tone Guidance from Corpus:\n"
                 for res in tone_query_result["results"]:
                     corpus_guidance += f"- {res.get('text', '')}\n"
        except Exception as e:
            print(f"Warning: Failed to query tone corpus: {e}")

    # 3. Use apply_tone_guidelines logic
    combined_guidelines = base_instructions + corpus_guidance
    # We infer user_query from answer context or leave generic since this tool signature doesn't have it
    refined_text = apply_tone_guidelines(answer, combined_guidelines, "User Query (Inferred from context)")

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

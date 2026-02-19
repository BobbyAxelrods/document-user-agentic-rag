import os
from typing import Optional, Dict, List, Any
from google.adk.models.lite_llm import LiteLlm 
from google.adk.models import Gemini
from dotenv import load_dotenv
import litellm
from google import genai

PEACE_OF_MIND_FORMULA = """
1. Empathise: Acknowledge the user's feelings, situation, or effort first. Use warm, human language.
2. Guide: Give a clear next step or factual answer. Avoid jargon. Keep sentences short (12-18 words).
3. Reassure: End with a calm, confident statement that reinforces Prudential's support.
"""

TONE_GROUP_FILE_MAP = {
    "fallback": "FALLBACK.md",
    "tg_fallback": "FALLBACK.md",
    "exitflow": "EXITFLOW.md",
    "tg_exitflow": "EXITFLOW.md",
    "system_general": "FOUNDATION.md",
    "foundation": "FOUNDATION.md",
    "tg_system_foundation": "FOUNDATION.md",
    "health_action": "HEALTH_ACTION.md",
    "tg_health_action": "HEALTH_ACTION.md",
    "health_assurance": "HEALTH_REASSURANCE.md",
    "health_reassurance": "HEALTH_REASSURANCE.md",
    "tg_health_reassurance": "HEALTH_REASSURANCE.md",
    "reengagement": "REENGAGEMENT.md",
    "tg_reengagement": "REENGAGEMENT.md",
    "speciality_care": "SPECIALTY_CARE.md",
    "specialty_care": "SPECIALTY_CARE.md",
    "tg_specialty_care": "SPECIALTY_CARE.md",
    "internal_prompt": "INTERNAL_PROMPT.md",
    "tg_internal_prompt": "INTERNAL_PROMPT.md",
}

def classify_tone_group(query: str, factual_context_found: bool = True) -> str:
    """
    Classifies the user query into one of the tone groups: fallback, exitflow, or system_general.
    The factual_context_found flag is accepted for backward compatibility but classification is
    based on the query text alone.
    """
    prompt = f"""
    Classify the following user query into exactly ONE of these categories:

    - exitflow: Use if the user wants to end, stop, cancel, or says "thank you", "goodbye", "that's all".
      Example: "Thank you, bye", "Stop messages", "I'm done".
    
    - fallback: Use if the user is emotional (nervous, worried), asks for a human, asks a medical question, or is confused.
      Example: "I'm scared", "Talk to a person", "What's wrong with me?", "I don't understand".
    
    - system_general: Use for everything else (health questions, booking, greetings).
      Example: "How do I book?", "What is diabetes?", "Hello".

    User Query: "{query}"

    Output only the single word: fallback, exitflow, or system_general.
    """
    
    try:
        client = _get_genai_client()
        if client:
            model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            raw_response = (response.text or "").strip().lower()
        else:
            model_name = os.getenv("AZURE", "azure/gpt-4o")
            if os.getenv("SANDBOX_ENV", "false").lower() == "true":
                model_name = "gemini/gemini-1.5-pro-001"
            response = litellm.completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            raw_response = response.choices[0].message.content.strip().lower()
        # Check for keywords in response to be more robust
        if "fallback" in raw_response:
            return "fallback"
        elif "exitflow" in raw_response:
            return "exitflow"
        elif "system_general" in raw_response:
            return "system_general"
        return "system_general"
    except Exception:
        return "system_general"

def _resolve_tone_file(group: str) -> str:
    key = (group or "system_general").strip().lower().replace(" ", "_")
    if key not in TONE_GROUP_FILE_MAP:
        key = "system_general"
    return TONE_GROUP_FILE_MAP[key]


def _load_tone_markdown(group: str) -> str:
    filename = _resolve_tone_file(group)
    rag_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    primary_dir = os.path.join(rag_root, "tone_groups")
    secondary_dir = os.path.join(os.path.dirname(rag_root), "tone_group")
    paths = [
        os.path.join(primary_dir, filename),
        os.path.join(secondary_dir, filename.lower()),
        os.path.join(secondary_dir, filename),
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                break
    return f"# TONE GROUP: {group}\nProvide helpful, empathetic, clear support.\n"


def get_tone_guidelines_by_group(group: str) -> str:
    normalized_group = (group or "system_general").strip().lower()
    foundation = _load_tone_markdown("foundation")
    specific = _load_tone_markdown(normalized_group)
    guidance = f"### TONE GROUP: {normalized_group.upper()}\n"
    guidance += f"### FORMULA:\n{PEACE_OF_MIND_FORMULA}\n"
    if foundation:
        guidance += "### FOUNDATION GUIDELINES:\n"
        guidance += f"{foundation}\n\n"
    guidance += f"### SPECIFIC TONE GROUP: {normalized_group.upper()}\n"
    guidance += f"{specific}\n"
    return guidance

def get_tone_guidelines_for_category(category: str) -> str:
    """
    Alias for get_tone_guidelines_by_group to maintain backward compatibility.
    """
    return get_tone_guidelines_by_group(category)

_rag_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
if os.path.exists(_rag_env_path):
    load_dotenv(_rag_env_path)
else:
    load_dotenv()


def _get_genai_client() -> Optional[genai.Client]:
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GENAI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION")
    if use_vertex and project_id and location:
        try:
            return genai.Client(vertexai=True, project=project_id, location=location)
        except Exception:
            return None
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            return genai.Client(api_key=api_key)
        except Exception:
            return None
    return None

def apply_tone_guidelines(
    content_answer: str, 
    tone_guidelines: str, 
    user_query: str,
    citations: Optional[str] = None
) -> str:
    prompt = f"""
    You are a Voice of Care Agent for Prudential.
    
    ### USER QUERY:
    {user_query}
    
    ### FACTUAL CONTEXT/ANSWER:
    {content_answer}
    
    ### CITATIONS:
    {citations if citations else "No specific source citations provided."}
    
    ### TONE GUIDELINES (VOICE OF CARE):
    {tone_guidelines}
    
    ### INSTRUCTIONS:
    1. Answer the user's query using the FACTUAL CONTEXT provided.
    2. **STRICTLY APPLY** the TONE GUIDELINES and the **Peace-of-Mind Formula** (Empathise -> Guide -> Reassure).
    3. Ensure you follow any **GOLDEN DIALOGUE** or **MANDATORY DISCLAIMERS** listed in the guidelines.
    4. Keep the tone human, warm, and supportive. Use active voice and simple language (max 20 words per sentence).
    5. Avoid jargon like "guided care", "orchestration", or "pathway". Use "help", "support", or "team" instead.
    6. If citations are provided, append them at the end under a "**Sources:**" header.
    
    ### RESPONSE FORMAT:
    [Internal: Tone Group Detected: <detected_group>]

    <Peace-of-Mind Response>

    **Sources:**
    [Citations if available]
    """
    
    try:
        client = _get_genai_client()
        if client:
            model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = response.text or ""
            return text
        model_name = os.getenv("AZURE", "azure/gpt-4o")
        if os.getenv("SANDBOX_ENV", "false").lower() == "true":
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
        client = _get_genai_client()
        if client:
            model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = response.text or ""
            return text
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
    Legacy tool wrapper that now uses instruction-based tone refinement.
    """
    # 1. Use the Peace-of-Mind Formula as baseline instructions
    combined_guidelines = f"### MANDATORY FORMULA:\n{PEACE_OF_MIND_FORMULA}\n"
    
    # 2. Refine text using apply_tone_guidelines logic
    # Since this legacy tool doesn't have the user_query, we use a placeholder
    refined_text = apply_tone_guidelines(answer, combined_guidelines, "User inquiry about PRUHealth")

    # 3. Format Output
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

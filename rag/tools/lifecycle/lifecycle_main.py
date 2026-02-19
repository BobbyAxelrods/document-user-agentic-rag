import os 
import hashlib
import math
import json
import io
import time
import re
from typing import Any, Optional, List, Dict
import pandas as pd 
import datetime
import pg8000
from google.cloud.sql.connector import Connector, IPTypes
import logging
from google.cloud import storage
from google.adk.tools import FunctionTool, ToolContext
import litellm
import sys
from google.cloud.sql.connector import Connector, IPTypes
from dotenv import load_dotenv
from google import genai

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()

try:
    from tools.corpus.corpus_tools import (
        get_corpus_id_by_display_name,
        query_corpus,
        import_files,
        delete_file_from_corpus,
        create_corpus,
        delete_corpus,
        list_corpora,
        list_files
    )
    from tools.storage.storage_tools import create_gcs_bucket, list_blobs
    from config import (
        PROJECT_ID, 
        RAG_DEFAULT_TOP_K,
        LOCATION, 
        EVAL_BUCKET_NAME,
    )
except ImportError:
    try:
        from rag.tools.corpus.corpus_tools import (
            get_corpus_id_by_display_name,
            query_corpus,
            import_files,
            delete_file_from_corpus,
            create_corpus,
            delete_corpus,
            list_corpora,
            list_files
        )
        from rag.tools.storage.storage_tools import create_gcs_bucket, list_blobs
        from rag.config import (
            PROJECT_ID, 
            RAG_DEFAULT_TOP_K,
            LOCATION, 
            EVAL_BUCKET_NAME,
        )
    except ImportError:
        from ...tools.corpus.corpus_tools import (
            get_corpus_id_by_display_name,
            query_corpus,
            import_files,
            delete_file_from_corpus,
            create_corpus,
            delete_corpus,
            list_corpora,
            list_files
        )
        from ...tools.storage.storage_tools import create_gcs_bucket, list_blobs
        from ...config import (
            PROJECT_ID, 
            RAG_DEFAULT_TOP_K,
            LOCATION, 
            EVAL_BUCKET_NAME,
        )

# Import tone tools
try:
    from tools.tone_management.tone_tools import (
        apply_tone_guidelines, 
        validate_tone_compliance,
        classify_tone_group,
        get_tone_guidelines_by_group
    )
except ImportError:
    try:
        from rag.tools.tone_management.tone_tools import (
            apply_tone_guidelines, 
            validate_tone_compliance,
            classify_tone_group,
            get_tone_guidelines_by_group
        )
    except ImportError:
        try:
            from ...tools.tone_management.tone_tools import (
                apply_tone_guidelines, 
                validate_tone_compliance,
                classify_tone_group,
                get_tone_guidelines_by_group
            )
        except ImportError:
            apply_tone_guidelines = None
            validate_tone_compliance = None
            classify_tone_group = None
            get_tone_guidelines_by_group = None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    storage_client = storage.Client(project=PROJECT_ID)
except Exception as e:
    logger.error(f"Failed to initialize storage client: {e}")
    storage_client = None


def _get_genai_client() -> Optional[genai.Client]:
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GENAI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or LOCATION
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

def _evaluate_with_llm(query: str, response: str, ground_truth: str) -> Dict[str, Any]:
    try:
        client = _get_genai_client()
        prompt = f"""
        You are an expert evaluator for RAG systems.
        
        Query: {query}
        Generated Response (Retrieved Context): {response}
        Ground Truth: {ground_truth}
        
        Task:
        1. Compare the Generated Response with the Ground Truth.
        2. Assign a score between 0.0 and 1.0 (1.0 being perfect match in meaning).
        3. Provide a brief reason.
        
        Output JSON format:
        {{
            "score": float,
            "reason": "string"
        }}
        """
        if client:
            model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
            completion = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            content = completion.text or ""
        else:
            model_name = os.getenv("AZURE", "azure/gpt-4o")
            completion = litellm.completion(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }
            )
            content = completion.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        return {"score": 0.0, "reason": f"Evaluation failed: {str(e)}"}

def _generate_answer(query: str, context: str) -> str:
    try:
        client = _get_genai_client()
        prompt = f"""
        You are a helpful assistant. Answer the user's query based ONLY on the provided context.
        If the answer is not in the context, say "I cannot answer this based on the provided information."
        
        Context:
        {context}
        
        Query: 
        {query}
        
        Answer:
        """
        if client:
            model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
            completion = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = completion.text or ""
            return text.strip()
        model_name = os.getenv("AZURE", "azure/gpt-4o")
        completion = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Generation failed: {str(e)}"

import math

def _normalize_filename(uri: str) -> str:
    """
    Extracts the base filename (lowercase, no extension) from a URI or file path.
    Example: "gs://bucket/folder/File-Name.pdf" -> "file-name"
    Handles removing parenthesis content and normalizing separators.
    """
    if not uri or pd.isna(uri):
        return ""
    
    # 1. Get basename
    base = os.path.basename(str(uri))
    
    # 2. Remove extension
    name = os.path.splitext(base)[0]
    
    # 3. Remove content in parentheses (e.g. "Treatment Sure (webpage)" -> "Treatment Sure")
    name = re.sub(r'\([^)]*\)', '', name)
    
    # 4. Replace special chars ([-_]) with space
    name = re.sub(r'[-_]', ' ', name)
    
    # 5. Normalize whitespace (strip and collapse multiple spaces)
    name = " ".join(name.split())
    
    return name.lower()

def _calculate_retrieval_metrics(retrieved_uris: List[str], ground_truth_docs: List[str], k: int = 20) -> Dict[str, float]:
    """
    Calculates Recall, Precision, and NDCG for retrieval.
    """
    # Normalize inputs
    retrieved_norm_raw = [_normalize_filename(u) for u in retrieved_uris]

    gt_norm = set([_normalize_filename(g) for g in ground_truth_docs if _normalize_filename(g)])
    
    if not gt_norm:
        return {"recall": 0.0, "precision": 0.0, "ndcg": 0.0}

    # Deduplicate retrieved items based on Ground Truth matching (Strict Document Level)
    # 1. Map each retrieved item to its matched GT document (if any)
    # 2. Deduplicate the resulting list preserving order
    retrieved_unique = []
    seen_docs = set() # Stores the normalized doc string (either GT name or original doc name)

    for doc in retrieved_norm_raw:
        # Check if this doc matches any Ground Truth
        matched_gt = None
        for gt in gt_norm:
            # Match if strings are equal, or one is substring of another
            if doc == gt or doc in gt or gt in doc:
                matched_gt = gt
                break
        
        # Use the matched GT name if found, otherwise use the original doc name
        item_to_add = matched_gt if matched_gt else doc
        
        if item_to_add not in seen_docs:
            retrieved_unique.append(item_to_add)
            seen_docs.add(item_to_add)

    # Slice to top K (Document Level)
    retrieved_k = retrieved_unique[:k]
    
    # Calculate Matches (Strict Document Level)
    matches_count = 0
    dcg = 0.0
    
    for i, doc in enumerate(retrieved_k):
        # Check strict existence in GT set (since we already mapped them)
        if doc in gt_norm:
            matches_count += 1
            # DCG: Binary relevance = 1
            dcg += 1.0 / math.log2(i + 2)

    # 1. Recall (Document-Level)
    # Unique Matches / Total Unique GT
    recall = matches_count / len(gt_norm)
    
    # 2. Precision (Document-Level)
    # Unique Matches / Total Unique Retrieved (Dynamic K)
    # This ensures 1/1 = 1.0 (100%)
    precision = matches_count / len(retrieved_k) if retrieved_k else 0.0
    
    # 3. NDCG (Document-Level)
    # IDCG based on Ideal Ranking of the retrieved set size
    # This ensures perfect ranking of available items = 1.0
    idcg = 0.0
    num_ideal_matches = min(len(gt_norm), len(retrieved_k))
    for i in range(num_ideal_matches):
        idcg += 1.0 / math.log2(i + 2)
        
    ndcg = dcg / idcg if idcg > 0 else 0.0
    
    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "ndcg": round(ndcg, 4)
    }

# =================MAIN PROCESS =====================
# =================MAIN PROCESS =====================
def automated_evaluation_testcase(
    tool_context : ToolContext,
    candidate_corpus: str,
    excel_path:str,

) -> Dict[str,Any]:

    """
    Executes an automated evaluation of a RAG corpus using a test case Excel file.
    
    Args:
        tool_context: Context for tool execution.
        candidate_corpus: The display name or ID of the RAG corpus to evaluate.
        excel_path: The FULL LOCAL PATH to the Excel file containing test cases (e.g., 'C:\eval\test.xlsx').
                    The tool has direct access to the local filesystem.
    
    Plan:

    1. Read the Excel file using pandas .
    2. Iterate through the rows.
    3. For each row, execute a RAG query using query_corpus .
    4. Compare the result with the ground truth using an LLM as a judge (). # Change this adding quantitative scoring recall, precision & NDCG 
    5. Update the pandas DataFrame with the results (RAG response, Score, Pass/Fail status).
    6. Return the final DataFrame (as a dict/list of records) and summary statistics.
    7. 

    """

    # Read Excel 
    df = pd.read_excel(excel_path)
    
    # Identify columns (flexible) by checking lowercase stripped versions but keeping original headers
    # Create a mapping for easy lookup
    col_map = {str(c).lower().strip(): c for c in df.columns}
    
    # Find actual column names in the dataframe
    query_col_name = next((c for c in col_map.keys() if c in ['query', 'question', 'input', 'user query']), list(col_map.keys())[0])
    truth_col_name = next((c for c in col_map.keys() if c in ['ground_truth', 'ground truth', 'groundtruth', 'expected', 'truth', 'answer', 'correct answer']), None)
    doc_truth_col_name = next((c for c in col_map.keys() if c in ['ground truth source documents', 'source document', 'source documents', 'ground truth documents']), None)
    
    query_col = col_map[query_col_name]
    truth_col = col_map[truth_col_name] if truth_col_name else None
    doc_truth_col = col_map[doc_truth_col_name] if doc_truth_col_name else None

    # Resolve Corpus ID
    corpus_id = candidate_corpus
    resolved_id = get_corpus_id_by_display_name(candidate_corpus)
    if resolved_id:
        corpus_id = resolved_id

    # Check if corpus has files
    files_res = list_files(corpus_id)
    if files_res.get("status") != "success":
        return {
             "status": "error", 
             "message": f"Failed to list files for corpus {candidate_corpus} (ID: {corpus_id}): {files_res.get('message')}"
         }

    if not files_res.get("files"):
         return {
             "status": "error", 
             "message": f"Corpus {candidate_corpus} (ID: {corpus_id}) is empty. Please ensure 'create_candidate_corpus' completed successfully and files were imported."
         }

    # Loop and Validate
    total_score = 0
    total_recall = 0.0
    total_precision = 0.0
    total_ndcg = 0.0
    pass_count = 0
    evaluated_rows = []

    # Setup for continuous save
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    date_folder = datetime.datetime.now().strftime("%Y-%m-%d")
    base_name = os.path.splitext(os.path.basename(excel_path))[0]
    
    # Define temporary and final paths
    temp_blob_path = f"temp_processing/{base_name}_{timestamp}_working.xlsx"
    final_blob_path = f"eval_results/{date_folder}/{base_name}_results_{timestamp}.xlsx"

    # Helper to save current progress to GCS
    def save_progress_to_gcs(current_rows, blob_path, is_temp=True):
        if not storage_client: return
        try:
            temp_df = pd.DataFrame(current_rows)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                temp_df.to_excel(writer, index=False)
            output_bytes = output.getvalue()
            
            bucket = storage_client.bucket(EVAL_BUCKET_NAME)
            blob = bucket.blob(blob_path)
            blob.upload_from_string(
                data=output_bytes,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            if not is_temp:
                logger.info(f"Saved results to gs://{EVAL_BUCKET_NAME}/{blob_path}")
        except Exception as e:
            logger.warning(f"Failed to save progress to {blob_path}: {e}")

    # 1. Upload initial file to temp location
    try:
        if storage_client:
            bucket = storage_client.bucket(EVAL_BUCKET_NAME)
            if not bucket.exists():
                create_gcs_bucket(tool_context=tool_context, bucket_name=EVAL_BUCKET_NAME, location=LOCATION)
            
            # Read bytes from local file
            with open(excel_path, "rb") as f:
                bucket.blob(temp_blob_path).upload_from_file(f)
            logger.info(f"Uploaded working copy to gs://{EVAL_BUCKET_NAME}/{temp_blob_path}")
    except Exception as e:
        logger.warning(f"Failed to upload initial working copy: {e}")
    
    try: ## main evaluation process ## --
        for index, row in df.iterrows():
            # Add delay to avoid hitting rate limits (LLM/Vertex AI quotas)
            time.sleep(2)
            
            query_text = str(row[query_col])
            # Use the identified truth column, but keep strict N/A handling for evaluation
            ground_truth = str(row[truth_col]) if truth_col and truth_col in df.columns else "N/A"
            if ground_truth.lower() == 'nan': ground_truth = "N/A"
            
            # Query RAG - Content Corpus
            rag_result = query_corpus(corpus_id=corpus_id, query=query_text)
            factual_context_found = rag_result.get("status") == "success" and bool(rag_result.get("results"))

            # Tone Grouping & Retrieval (New 4-step workflow)
            tone_group = "system_general"
            tone_guidelines = ""
            if classify_tone_group:
                tone_group = classify_tone_group(query_text, factual_context_found)
                if get_tone_guidelines_by_group:
                    tone_guidelines = get_tone_guidelines_by_group(tone_group)

            response_text = "No response"
            factual_response = "No factual response"
            citations = []
            chunks = []
            retrieved_uris = []
            tone_eval = {}
            
            if rag_result.get("status") == "success":
                 if "results" in rag_result and rag_result["results"]:
                     # Get top 5 chunks
                     top_results = rag_result["results"][:5]
                     
                     # Prepare context from chunks
                     context_text = "\n\n".join([r.get("text", "") for r in top_results])
                     chunks = [r.get("text", "") for r in top_results]
                     
                     # Collect URIs for retrieval evaluation (Use ALL retrieved results, not just top 5)
                     retrieved_uris = [r.get("source_uri", "") for r in rag_result["results"]]
                     
                     # 1. Generate Factual Answer using LLM
                     factual_response = _generate_answer(query_text, context_text)
                     
                     # 2. Apply Tone Guidelines (Sandwich Prompt)
                     if apply_tone_guidelines and tone_guidelines:
                         response_text = apply_tone_guidelines(factual_response, tone_guidelines, query_text)
                     else:
                         response_text = factual_response

                     # 3. Validate Tone Compliance
                     if validate_tone_compliance:
                         tone_eval_str = validate_tone_compliance(response_text, tone_guidelines)
                         try:
                             tone_eval = json.loads(tone_eval_str)
                         except:
                             tone_eval = {"error": "Failed to parse tone evaluation"}
                     
                     # Extract citations (source_uri)
                     citations = list(set([r.get("source_uri", "Unknown") for r in rag_result["results"] if r.get("source_uri")]))
            
            # --- Retrieval Evaluation (New) ---
            retrieval_metrics = {"recall": 0.0, "precision": 0.0, "ndcg": 0.0}
            if doc_truth_col and doc_truth_col in df.columns:
                raw_gt_docs = str(row[doc_truth_col])
                if raw_gt_docs.lower() != 'nan':
                    # Split by comma if multiple docs
                    gt_docs_list = [d.strip() for d in raw_gt_docs.split(',')]
                    retrieval_metrics = _calculate_retrieval_metrics(retrieved_uris, gt_docs_list, k=RAG_DEFAULT_TOP_K)

            # --- Generation Evaluation (Existing) ---
            eval_result = _evaluate_with_llm(query_text, response_text, ground_truth)
            score = eval_result.get("score", 0.0)
            
            is_pass = score >= 0.7
            if is_pass: pass_count += 1
            total_score += score
            
            # Construct Output Row:
            # 1. Start with original row data to preserve structure and values
            out_row = row.to_dict()
            
            # 2. Append new results columns
            out_row['factual_response'] = factual_response[:1000] + "..." if len(factual_response) > 1000 else factual_response
            out_row['rag_response'] = response_text[:1000] + "..." if len(response_text) > 1000 else response_text
            out_row['tone_group'] = tone_group
            out_row['tone_guidelines'] = tone_guidelines
            
            # Add Tone Metrics
            out_row['tone_empathy_score'] = tone_eval.get('empathy_score', 0)
            out_row['tone_clarity_score'] = tone_eval.get('clarity_score', 0)
            out_row['tone_professionalism_score'] = tone_eval.get('professionalism_score', 0)
            out_row['tone_compliance_score'] = tone_eval.get('compliance_score', 0)
            out_row['tone_overall_score'] = tone_eval.get('overall_score', 0)
            out_row['tone_feedback'] = tone_eval.get('feedback', "")
            
            # Add Retrieval Metrics
            out_row['retrieval_recall'] = retrieval_metrics['recall']
            out_row['retrieval_precision'] = retrieval_metrics['precision']
            out_row['retrieval_ndcg'] = retrieval_metrics['ndcg']
            
            # Aggregate metrics
            total_recall += retrieval_metrics['recall']
            total_precision += retrieval_metrics['precision']
            total_ndcg += retrieval_metrics['ndcg']
            
            # Add top chunks
            for i in range(1):
                out_row[f'chunk_{i+1}'] = chunks[i] if i < len(chunks) else ""

            out_row['citations'] = ", ".join(citations)
            out_row['score'] = score
            out_row['status'] = "PASS" if is_pass else "FAIL"
            out_row['reason'] = eval_result.get("reason", "")
            out_row['row_id'] = index + 1
            
            # Sanitize for JSON/LiteLLM compatibility (handle NaN, Timestamp, etc.)
            for k, v in out_row.items():
                if pd.isna(v):  # Handles NaN, None, NaT
                    out_row[k] = None
                elif isinstance(v, (pd.Timestamp, datetime.datetime, datetime.date)):
                    out_row[k] = str(v)
            
            evaluated_rows.append(out_row)

            # Checkpoint every 5 rows
            if (index + 1) % 5 == 0:
                save_progress_to_gcs(evaluated_rows, temp_blob_path, is_temp=True)

    except Exception as e:
        logger.error(f"Regression test interrupted: {e}")
        # Try to save whatever we have so far
        save_progress_to_gcs(evaluated_rows, temp_blob_path, is_temp=True)
        return {
            "status": "error", 
            "message": f"Regression test failed/interrupted: {str(e)}", 
            "partial_results_uri": f"gs://{EVAL_BUCKET_NAME}/{temp_blob_path}"
        }

    avg_score = total_score / len(df) if len(df) > 0 else 0
    avg_recall = total_recall / len(df) if len(df) > 0 else 0
    avg_precision = total_precision / len(df) if len(df) > 0 else 0
    avg_ndcg = total_ndcg / len(df) if len(df) > 0 else 0
    
    failures = [r["row_id"] for r in evaluated_rows if r["status"] == "FAIL"]
    
    # Save results directly to GCS
    results_gcs_uri = ""
    try:
        # Save final to output folder
        save_progress_to_gcs(evaluated_rows, final_blob_path, is_temp=False)
        results_gcs_uri = f"gs://{EVAL_BUCKET_NAME}/{final_blob_path}"

        # Clean up temp file
        if storage_client:
            try:
                bucket = storage_client.bucket(EVAL_BUCKET_NAME)
                blob = bucket.blob(temp_blob_path)
                if blob.exists():
                    blob.delete()
                    logger.info(f"Deleted temporary working file: {temp_blob_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_blob_path}: {e}")

    except Exception as e:
        logger.error(f"Failed to save/upload regression results: {e}")
        results_gcs_uri = f"Error: {str(e)}"

    return {
        "status": "success",
        "project_id": PROJECT_ID,
        "results_file_uri": results_gcs_uri,
        "summary": {
            "total_queries": len(df),
            "passed": pass_count,
            "failed": len(failures),
            "average_score": round(avg_score, 2),
            "average_recall": round(avg_recall, 4),
            "average_precision": round(avg_precision, 4),
            "average_ndcg": round(avg_ndcg, 4),
            "failed_row_ids": failures,
            "passed_row_ids": [r["row_id"] for r in evaluated_rows if r["status"] == "PASS"]
        },
        # "details": evaluated_rows  # Removed to prevent LLM token limit errors. Full results are in the Excel file.
    }

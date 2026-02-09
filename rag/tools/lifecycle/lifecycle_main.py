import os 
import hashlib
import json
import io
import time
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

# Import corpus tools
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
            LOCATION, 
            EVAL_BUCKET_NAME,
        )

### storage client initi
# Initialize Storage Client
try:
    storage_client = storage.Client(project=PROJECT_ID)
except Exception as e:
    logger.error(f"Failed to initialize storage client: {e}")
    storage_client = None


# Logger setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def _evaluate_with_llm(query: str, response: str, ground_truth: str) -> Dict[str, Any]:
    """
    Evaluates RAG response against ground truth using LiteLLM (matching Agent's config).
    """
    try:
        #model_name = os.getenv("AZURE", "azure/gpt-4o")
        model_name = os.getenv("MODEL_NAME", "gemini-2.5-pro")
        
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
    """
    Generates an answer based on the query and retrieved context using the LLM.
    """
    try:
        #model_name = os.getenv("AZURE", "azure/gpt-4o")
        model_name = os.getenv("MODEL_NAME", "gemini-2.5-pro")

        prompt = f"""
        You are a helpful assistant. Answer the user's query based ONLY on the provided context.
        If the answer is not in the context, say "I cannot answer this based on the provided information."
        
        Context:
        {context}
        
        Query: 
        {query}
        
        Answer:
        """
        
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

def _refine_tone_with_golden_dialogue(answer: str) -> str:
    """
    Refines the answer's tone using an LLM to conform to Golden Dialogue principles.
    """
    try:
        model_name = os.getenv("MODEL_NAME", "gemini-1.5-pro")

        prompt = f"""
        You are an expert in communication, tasked with refining an answer to align with "Golden Dialogue" principles.

        Golden Dialogue Principles:
        - **Clarity & Empathy**: Be clear, empathetic, and professional.
        - **Action-Oriented**: Use direct and action-oriented phrasing.
        - **Simplicity**: Avoid jargon. If jargon is necessary, explain it briefly.
        - **Safety**: Avoid speculation. If there is uncertainty, state it explicitly.

        Original Answer:
        {answer}

        Task:
        Revise the original answer to strictly follow the Golden Dialogue principles.
        Do not add any new information.
        If the original answer indicates it cannot answer, keep that meaning.

        Revised Answer:
        """

        completion = litellm.completion(
            model=model_name,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Tone refinement failed: {e}")
        return answer # Return original answer if refinement fails
# =================MAIN PROCESS =====================
# =================MAIN PROCESS =====================
def automated_evaluation_testcase(
    tool_context : ToolContext,
    #candidate_corpus: str,
    #excel_path:str,

) -> Dict[str,Any]:

    """
    Plan:

    1. Read the Excel file using pandas .
    2. Iterate through the rows.
    3. For each row, execute a RAG query using query_corpus .
    4.  Compare the result with the ground truth using an LLM as a judge ().
    5. Update the pandas DataFrame with the results (RAG response, Score, Pass/Fail status).
    6. Return the final DataFrame (as a dict/list of records) and summary statistics.

    """

    # Read Excel 
    excel_path = "./evaluation_files/EMO, POLICY & VAS QA_updated.xlsx"
    df = pd.read_excel(excel_path, sheet_name="Sheet2")
    
    # Identify columns (flexible) by checking lowercase stripped versions but keeping original headers
    # Create a mapping for easy lookup
    col_map = {str(c).lower().strip(): c for c in df.columns}
    
    # Find actual column names in the dataframe
    query_col_name = next((c for c in col_map.keys() if c in ['query', 'question', 'input', 'user query']), list(col_map.keys())[0])
    truth_col_name = next((c for c in col_map.keys() if c in ['ground_truth', 'ground truth', 'groundtruth', 'expected', 'truth', 'answer', 'correct answer']), None)
    
    query_col = col_map[query_col_name]
    truth_col = col_map[truth_col_name] if truth_col_name else None

    # Loop and Validate
    total_score = 0
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
    
    try:
        df_eval = pd.DataFrame()
        for index, row in df.iterrows():
            # Add delay to avoid hitting rate limits (LLM/Vertex AI quotas)
            time.sleep(2)
            
            query_text = str(row[query_col])
            # Use the identified truth column, but keep strict N/A handling for evaluation
            ground_truth = str(row[truth_col]) if truth_col and truth_col in df.columns else "N/A"
            if ground_truth.lower() == 'nan': ground_truth = "N/A"
            
            # --- Start of New Agent-like Logic ---

            # 2. Select Corpus based on query
            query_lower = query_text.lower()
            if "pru" in query_lower or "prudential" in query_lower or "policy" in query_lower or "product" in query_lower:
                target_corpus_display_name = "gc-phkl-policy"
            else:
                target_corpus_display_name = "gc-phkl-vas"
            
            corpus_id = get_corpus_id_by_display_name(target_corpus_display_name)
            if not corpus_id:
                # Fallback to the original candidate_corpus if the specific one isn't found
                logger.warning(f"Could not find corpus '{target_corpus_display_name}'. Falling back to '{candidate_corpus}'.")
                corpus_id = get_corpus_id_by_display_name(candidate_corpus)
                if not corpus_id:
                     # If fallback also fails, we must skip this row.
                    logger.error(f"Fallback corpus '{candidate_corpus}' also not found. Skipping row {index + 1}.")
                    response_text = f"Error: Corpus '{target_corpus_display_name}' or fallback '{candidate_corpus}' not found."
                    citations, chunks = [], []
                    # Continue to evaluation to mark it as a failure
                
            # 3. Query Corpus and Generate Initial Answer
            response_text = "No response"
            citations, chunks, chunk_ids, document_names = [], [], [], []

            if corpus_id:
                rag_result = query_corpus(corpus_id=corpus_id, query=query_text)
                
                if rag_result.get("status") == "success" and "results" in rag_result and rag_result["results"]:
                    # Get top 5 chunks for context
                    top_results = rag_result["results"][:5]
                    
                    # Prepare context from chunks
                    context_text = "\n\n".join([r.get("text", "") for r in top_results])
                    
                    # Generate Initial Answer using LLM
                    initial_answer = _generate_answer(query_text, context_text)

                    # 4. Refine Tone with Golden Dialogue
                    response_text = _refine_tone_with_golden_dialogue(initial_answer)
                    
                    # 5. Extract chunk details and citations
                    chunks = [r.get("text", "") for r in top_results]
                    chunk_ids = [r.get("chunk_id", "") for r in top_results]
                    document_names = [os.path.basename(r.get("source_uri", "Unknown")) for r in top_results]
                    citations = list(set([r.get("source_uri", "Unknown") for r in top_results if r.get("source_uri")]))
                else:
                    response_text = "Could not retrieve any information from the corpus to answer the query."
            
            # --- End of New Agent-like Logic ---

            # Evaluate
            eval_result = _evaluate_with_llm(query_text, response_text, ground_truth)
            score = eval_result.get("score", 0.0)
            
            is_pass = score >= 0.7
            if is_pass: pass_count += 1
            total_score += score
            
            # Construct Output Row:
            # 1. Start with original row data to preserve structure and values
            out_row = row.to_dict()
            
            # 2. Append new results columns
            out_row['rag_response'] = response_text[:1000] + "..." if len(response_text) > 1000 else response_text
            
            # Add top 5 chunks and their details
            for i in range(5):
                out_row[f'retrieved_chunk_{i+1}'] = chunks[i] if i < len(chunks) else ""
                out_row[f'retrieved_chunk_id_{i+1}'] = chunk_ids[i] if i < len(chunk_ids) else ""
                out_row[f'retrieved_document_name_{i+1}'] = document_names[i] if i < len(document_names) else ""

            out_row['retrieved_citations'] = ", ".join(citations)
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
            print(evaluated_rows)
            df_eval = pd.DataFrame(evaluated_rows)
            
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

    df_eval.to_excel("/home/sinkitlo/guided_care/document-user-agentic-rag/evaluation_files/eval_results.xlsx", index=False)
    return {
        "status": "success",
        "project_id": PROJECT_ID,
        "results_file_uri": results_gcs_uri,
        "summary": {
            "total_queries": len(df),
            "passed": pass_count,
            "failed": len(failures),
            "average_score": round(avg_score, 2),
            "failed_row_ids": failures,
            "passed_row_ids": [r["row_id"] for r in evaluated_rows if r["status"] == "PASS"]
        },
        # "details": evaluated_rows  # Removed to prevent LLM token limit errors. Full results are in the Excel file.
    }

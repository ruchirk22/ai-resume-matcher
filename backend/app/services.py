# backend/app/services.py
import io
import os
import json
import asyncio
from typing import List, Dict, Any, Tuple
import time

import pypdf
import docx2txt
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_random_exponential

from . import schemas # Import schemas for type hinting

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")

genai.configure(api_key=GEMINI_API_KEY)

PRIMARY_EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_FALLBACKS = [
    "models/text-embedding-004",  # primary (kept first for clarity)
    "models/text-embedding-002",  # older embedding
]

PRIMARY_GENERATION_MODEL = "gemini-2.0-flash"
GENERATION_FALLBACKS = [
    "gemini-2.0-flash",  # primary (kept first for clarity)
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

cache: Dict[str, Any] = {}

# --- TTL Cache Management ---
_TTL_SECONDS = 60 * 30  # 30 minutes for JD skill extraction & short-lived objects
_jd_skill_cache: Dict[str, Tuple[float, dict]] = {}  # jd_text -> (timestamp, result)

def _is_fresh(ts: float) -> bool:
    return (time.time() - ts) < _TTL_SECONDS

def flush_caches():
    _jd_skill_cache.clear()
    cache.clear()
    return {"status": "flushed"}

# --- File Processing ---
def extract_text_from_file(filename: str, content: bytes) -> str:
    """Extracts text from a given file's content (PDF or DOCX)."""
    if filename.lower().endswith(".pdf"):
        try:
            pdf_reader = pypdf.PdfReader(io.BytesIO(content))
            return "".join(page.extract_text() or "" for page in pdf_reader.pages)
        except Exception as e:
            print(f"Error reading PDF {filename}: {e}")
            return ""
    elif filename.lower().endswith(".docx"):
        return docx2txt.process(io.BytesIO(content))
    else:
        return content.decode("utf-8", errors="ignore")

# --- AI Services ---

@retry(wait=wait_random_exponential(min=1, max=30), stop=stop_after_attempt(3))
async def get_embedding(text: str) -> List[float]:
    """Generate embeddings with tiered model fallback.

    Order: primary then fallbacks. On rate limit / transient error we try next model.
    Returns zero-vector if all attempts fail.
    """
    if not text or not isinstance(text, str):
        return [0.0] * 768
    last_err = None
    for model_name in EMBEDDING_FALLBACKS:
        try:
            result = await genai.embed_content_async(
                model=model_name,
                content=text,
                task_type="RETRIEVAL_DOCUMENT"
            )
            return result.get('embedding', [0.0]*768)
        except Exception as e:
            last_err = e
            print(f"Embedding model '{model_name}' failed: {e}")
            continue
    print(f"All embedding models failed. Returning zero-vector. Last error: {last_err}")
    return [0.0] * 768

@retry(wait=wait_random_exponential(min=1, max=30), stop=stop_after_attempt(2))
async def call_gemini_api(prompt: str, response_schema: Any) -> Dict[str, Any]:
    """Call Gemini with structured JSON output & fallback across multiple models.

    Falls through GENERATION_FALLBACKS; if all fail returns minimal empty structure.
    """
    last_err = None
    for model_name in GENERATION_FALLBACKS:
        try:
            model = genai.GenerativeModel(
                model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            full_prompt = f"{prompt}\n\nStrictly follow this JSON schema for your response:\n{json.dumps(response_schema)}"
            response = await model.generate_content_async(full_prompt, request_options={"timeout": 120})
            response_text = (response.text or '').strip()
            return json.loads(response_text) if response_text else {}
        except Exception as e:
            last_err = e
            print(f"Generation model '{model_name}' failed: {e}")
            continue
    print(f"All generation models failed. Returning fallback empty structure. Last error: {last_err}")
    # Build empty object respecting schema top-level keys if possible
    empty: Dict[str, Any] = {}
    if isinstance(response_schema, dict) and response_schema.get('properties'):
        for k, v in response_schema['properties'].items():
            t = v.get('type') if isinstance(v, dict) else None
            if t == 'array':
                empty[k] = []
            elif t == 'object':
                empty[k] = {}
            else:
                empty[k] = ''
    return empty

async def parse_resume_text(resume_text: str) -> dict:
    """Uses a robust prompt with Gemini to parse resume text into a structured JSON object."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "experience": { "type": "array", "items": { "type": "object", "properties": { "title": {"type": "string"}, "company": {"type": "string"}, "duration": {"type": "string"}}}}
        }
    }
    prompt = f"Parse the following resume text into a valid JSON object. Be thorough in extracting all skills.\n\nResume Text:\n---\n{resume_text}\n---"
    return await call_gemini_api(prompt, schema)

async def extract_skills_from_jd(jd_text: str) -> dict:
    """Uses Gemini to extract required and nice-to-have skills from a JD.

    Adds a TTL cache (30 min) to avoid repeated LLM calls when user navigates or refetches.
    """
    cached = _jd_skill_cache.get(jd_text)
    if cached and _is_fresh(cached[0]):
        return cached[1]

    schema = {"type": "object", "properties": {"required_skills": {"type": "array", "items": {"type": "string"}}, "nice_to_have_skills": {"type": "array", "items": {"type": "string"}}}}
    prompt = f"Analyze the job description and extract skills into 'required_skills' and 'nice_to_have_skills'.\n\nJob Description:\n---\n{jd_text}\n---"

    result = await call_gemini_api(prompt, schema)
    _jd_skill_cache[jd_text] = (time.time(), result)
    return result

async def evaluate_candidate_for_jd(jd_text: str, jd_skills: dict, resume_text: str) -> dict:
    """
    Uses Gemini to evaluate a candidate's resume against a job description.
    This is the AI-powered analysis that identifies matched and missing skills
    directly from the resume text, without relying on parsed skills.
    
    Returns a dict with matched_skills, missing_skills, and rationale.
    """
    required_skills = jd_skills.get('required_skills', [])
    
    schema = {
        "type": "object",
        "properties": {
            "matched_skills": {"type": "array", "items": {"type": "string"}},
            "missing_skills": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"}
        }
    }
    
    # CRITICAL FIX: Enhanced prompt to make skill matching more accurate
    prompt = f"""
    You are a professional recruiting assistant. Your task is to evaluate how well a candidate's skills match a job's requirements.
    
    JOB DESCRIPTION:
    ---
    {jd_text}
    ---
    
    REQUIRED SKILLS (IMPORTANT: Use EXACTLY these skill names in your response):
    {', '.join(required_skills)}
    
    NICE TO HAVE SKILLS (IMPORTANT: Use EXACTLY these skill names in your response):
    {', '.join(jd_skills.get('nice_to_have_skills', []))}
    
    RESUME:
    ---
    {resume_text}
    ---
    
    INSTRUCTIONS:
    
    1. For each skill in the REQUIRED SKILLS list, determine if the candidate possesses it based on their resume.
    2. Return the exact skill names (matching the spelling and capitalization provided in REQUIRED SKILLS) that the candidate has.
    3. Also return the exact skill names the candidate is missing.
    4. Provide a 2-sentence rationale explaining how well the candidate matches the job.
    
    IMPORTANT: ONLY use the EXACT skill names provided in the lists above. DO NOT reword, rephrase, or create your own skill names.
    Look for direct mentions, synonyms, or evidence of experience with those exact skills in the resume.
    """
    
    result = await call_gemini_api(prompt, schema)
    return result

async def generate_candidate_rationale(
    jd_skills: dict, resume_text: str, matched_skills: List[str], missing_skills: List[str]
) -> str:
    """
    Generate a human-friendly rationale text explaining the candidate's match score.
    
    This function does NOT evaluate or score the candidate - it ONLY explains the 
    pre-calculated match based on the provided skills data.
    
    Args:
        jd_skills: Dictionary containing required and nice-to-have skills from the JD
        resume_text: The candidate's resume text
        matched_skills: List of skills the candidate has that match required skills
        missing_skills: List of required skills the candidate is missing
    
    Returns:
        A 2-sentence rationale explaining the candidate's match
    """
    schema = {"type": "object", "properties": {"rationale": {"type": "string"}}}
    
    # Format the prompt to give clear instructions to the AI
    prompt = f"""
    You are a professional recruiting assistant. A candidate has already been scored based on their skills match.
    Your task is to provide a brief, 2-sentence rationale explaining the score.
    
    DO NOT re-evaluate the candidate or calculate a new score. Your job is ONLY to explain the existing match.
    
    **Job's Required Skills:** {', '.join(jd_skills.get('required_skills', []))}
    **Candidate's Matched Skills:** {', '.join(matched_skills)}
    **Candidate's Missing Required Skills:** {', '.join(missing_skills)}

    Based on this information, write a 2-sentence summary for the recruiter that explains:
    1. The candidate's strengths based on matched skills
    2. The candidate's gaps based on missing skills
    
    Be concise, objective, and ensure your explanation aligns with the pre-calculated match.
    """
    
    # Call the AI API and get the rationale
    response = await call_gemini_api(prompt, schema)
    return response.get("rationale", "AI rationale could not be generated.")


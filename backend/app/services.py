import io
import os
import json
import re
import asyncio
import pypdf
import docx2txt
import google.generativeai as genai
from sentence_transformers import SentenceTransformer

# --- File processing ---
def extract_text_from_file(file):
    """
    Extracts text from a given file (PDF or DOCX).
    """
    filename = file.filename
    content = file.file.read()
    
    if filename.endswith(".pdf"):
        pdf_reader = pypdf.PdfReader(io.BytesIO(content))
        text = ""
        for page in pdf_reader.pages:
            extracted_text = page.extract_text()
            if extracted_text:
                text += extracted_text
        return text
    elif filename.endswith(".docx"):
        return docx2txt.process(io.BytesIO(content))
    elif filename.endswith(".txt"):
        return content.decode("utf-8")
    else:
        return content.decode("utf-8")

# --- Embedding Logic ---
print("Loading local sentence-transformer model...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
print("Sentence-transformer model loaded.")

def get_embedding(text: str) -> list[float]:
    """
    Generates embeddings for a given text using a local SentenceTransformer model.
    """
    if not text or not isinstance(text, str):
        return [0.0] * 384
        
    embedding = embedding_model.encode(text, convert_to_tensor=False).tolist()
    return embedding

# --- AI Interaction Logic with Fallback and Resilience ---

# **RELIABILITY FIX**: Define a list of models to try in order of preference.
GEMINI_MODEL_FALLBACK_LIST = [
    'gemini-2.5-pro',
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.0-flash',
    'gemini-2.0-flash-lite',
    'gemini-1.5-flash-latest',
]

async def _call_gemini_with_fallback(prompt: str) -> str:
    """
    Calls the Gemini API with a given prompt, trying models from the fallback list.
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("ERROR: GOOGLE_API_KEY not found.")
        raise ValueError("Google API Key not configured.")
    
    genai.configure(api_key=google_api_key)
    
    for model_name in GEMINI_MODEL_FALLBACK_LIST:
        try:
            print(f"Attempting to use Gemini model: {model_name}")
            model = genai.GenerativeModel(model_name)
            response = await model.generate_content_async(prompt, request_options={"timeout": 100})
            print(f"Successfully received response from {model_name}.")
            return response.text
        except Exception as e:
            print(f"Failed to use model {model_name}. Error: {e}")
            if model_name == GEMINI_MODEL_FALLBACK_LIST[-1]:
                raise
            else:
                print("Trying next model in fallback list...")
    
    raise RuntimeError("Failed to get a response from any of the Gemini models.")


def _clean_and_parse_json(ai_response_text: str) -> dict:
    """
    Cleans markdown/conversation from AI response and parses it into a dictionary.
    """
    json_match = re.search(r'\{.*\}', ai_response_text, re.DOTALL)
    
    if not json_match:
        print(f"Failed to find a JSON object in the AI response. Full response: {ai_response_text}")
        raise json.JSONDecodeError("No JSON object found in response", ai_response_text, 0)

    clean_json_text = json_match.group(0)
    return json.loads(clean_json_text)

async def parse_resume_text(resume_text: str) -> dict:
    """
    Asynchronously uses Gemini API to parse raw resume text into a structured JSON object.
    """
    prompt = f"""
    Parse the following resume text into a structured JSON object.

    **JSON Schema:**
    {{
      "name": "string", "email": "string", "phone": "string", "skills": ["string"],
      "experience": [{{ "title": "string", "company": "string", "duration": "string", "responsibilities": ["string"] }}],
      "education": [{{ "degree": "string", "institution": "string", "year": "string" }}]
    }}
    **Instructions:**
    1. Extract the candidate's full name, email, and phone. Use "N/A" if not found.
    2. List all technical skills and tools.
    3. Detail work experience and education.
    4. **CRITICAL: Respond with ONLY the raw JSON object.**
    **Resume Text:**
    ---
    {resume_text}
    ---
    """
    try:
        response_text = await _call_gemini_with_fallback(prompt)
        parsed_data = _clean_and_parse_json(response_text)
        print("Successfully parsed resume.")
        return parsed_data
    except Exception as e:
        print(f"An error occurred during resume parsing: {e}")
        return {"error": "Parsing failed", "name": "Parsing Error", "skills": [], "experience": [], "education": []}

async def evaluate_candidate_with_ai(jd_text: str, resume_text: str) -> dict:
    """
    Asynchronously evaluates a resume against a job description using Gemini API.
    """
    prompt = f"""
    You are an expert Technical Recruiter. Evaluate the candidate's resume against the job description.
    Provide your analysis as a raw JSON object.

    **JSON Schema:**
    {{ "match_percentage": "integer", "rationale": "string", "matched_skills": ["string"], "missing_skills": ["string"] }}
    **Instructions:**
    1. **match_percentage**: Overall match score (0-100).
    2. **rationale**: A 2-3 sentence summary of your reasoning.
    3. **matched_skills**: Key skills from the JD present in the resume.
    4. **missing_skills**: Key skills from the JD missing from the resume.
    5. **CRITICAL: Respond with ONLY the raw JSON object.**
    ---
    **Job Description:**
    {jd_text}
    ---
    **Candidate Resume:**
    {resume_text}
    ---
    """
    try:
        response_text = await _call_gemini_with_fallback(prompt)
        evaluation_data = _clean_and_parse_json(response_text)
        
        score = evaluation_data.get("match_percentage", 0)
        if score >= 80:
            evaluation_data["category"] = "Strong"
        elif score >= 60:
            evaluation_data["category"] = "Good"
        else:
            evaluation_data["category"] = "Weak"
            
        print("Successfully evaluated candidate.")
        return evaluation_data
    except Exception as e:
        print(f"An error occurred during AI evaluation: {e}")
        return {"error": "Evaluation failed", "match_percentage": 0, "rationale": "An error occurred during AI analysis.", "matched_skills": [], "missing_skills": [], "category": "Weak"}


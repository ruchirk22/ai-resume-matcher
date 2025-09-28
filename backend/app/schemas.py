# backend/app/schemas.py
from pydantic import BaseModel, ConfigDict
from typing import Any, Optional, List, Dict
from datetime import datetime

# --- Base Schemas ---
class UserBase(BaseModel):
    email: str

class JobDescriptionBase(BaseModel):
    title: str

class ResumeBase(BaseModel):
    candidate_name: str

# --- Create Schemas ---
class UserCreate(UserBase):
    password: str

# --- AI Model Schemas ---
class ResumeParsed(BaseModel):
    name: str
    email: str
    phone: str
    skills: List[str]
    experience: List[Dict[str, str]]

# --- Response Schemas ---
class User(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class JobDescription(JobDescriptionBase):
    id: int
    user_id: int
    text: Optional[str] = None
    required_skills: Optional[List[str]] = None
    nice_to_have_skills: Optional[List[str]] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class Resume(ResumeBase):
    id: int
    user_id: int
    parsed_json: Optional[Any] = None
    # analysis_results is now deprecated in favor of on-the-fly generation
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# This is the unified data model for a candidate match, used by both list and detail views.
class CandidateMatch(BaseModel):
    resume: Resume
    score: float
    match_rating: str
    matched_skills: List[str]
    missing_skills: List[str]
    analyzed_at: Optional[str] = None
    similarity: Optional[float] = None
    # match_rating values:
    #  - "Strong" | "Good" | "Weak" -> AI-verified scoring
    #  - "Preliminary" -> fast heuristic (before AI analysis or when low-similarity skipped)
    resume_excerpt: Optional[str] = None

# The detailed view simply adds the AI-generated rationale to the base match data.
class DetailedCandidate(CandidateMatch):
    rationale: str

class JDAnalysisStatus(BaseModel):
    jd_id: int
    total_resumes: int
    analyzed: int
    preliminary: int
    pending: int
    # Convenience percentage fields
    analyzed_pct: float
    preliminary_pct: float
    pending_pct: float

# --- Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Bulk Upload Schemas ---
class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    total: int


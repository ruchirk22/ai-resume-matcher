from pydantic import BaseModel, ConfigDict
from typing import Any, Optional, List

# --- Analysis Schemas ---
class AnalysisBase(BaseModel):
    match_percentage: int
    rationale: str
    matched_skills: List[str]
    missing_skills: List[str]

class AnalysisCreate(AnalysisBase):
    pass

class Analysis(AnalysisBase):
    id: int
    resume_id: int
    jd_id: int
    
    model_config = ConfigDict(from_attributes=True)

# --- Resume Schemas ---
class ResumeBase(BaseModel):
    candidate_name: str

class Resume(ResumeBase):
    id: int
    user_id: int
    weaviate_id: str
    parsed_json: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

# --- JD Schemas ---
class JobDescriptionBase(BaseModel):
    title: str

class JobDescription(JobDescriptionBase):
    id: int
    user_id: int
    weaviate_id: str
    text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- Main Response Schema ---
class CandidateMatch(AnalysisBase):
    resume: Resume

    model_config = ConfigDict(from_attributes=True)
    
# --- User & Token Schemas (no changes) ---
class UserCreate(BaseModel):
    email: str
    password: str

class User(BaseModel):
    id: int
    email: str
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None


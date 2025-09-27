from sqlalchemy import Column, Integer, String, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    jds = relationship("JobDescription", back_populates="owner", cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="owner", cascade="all, delete-orphan")

class JobDescription(Base):
    __tablename__ = "job_descriptions"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    text = Column(Text)
    weaviate_id = Column(String, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="jds")
    analyses = relationship("Analysis", back_populates="jd", cascade="all, delete-orphan")

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    candidate_name = Column(String, index=True)
    text = Column(Text)
    parsed_json = Column(JSON)
    weaviate_id = Column(String, unique=True)
    content_hash = Column(String, unique=True) # For duplicate checking
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="resumes")
    analyses = relationship("Analysis", back_populates="resume", cascade="all, delete-orphan")

# NEW: The "memory" of our application
class Analysis(Base):
    __tablename__ = "analysis"
    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"))
    jd_id = Column(Integer, ForeignKey("job_descriptions.id"))
    
    # The stored results from the AI
    match_percentage = Column(Integer)
    rationale = Column(Text)
    matched_skills = Column(JSON)
    missing_skills = Column(JSON)
    category = Column(String)
    
    # Relationships to link back
    resume = relationship("Resume", back_populates="analyses")
    jd = relationship("JobDescription", back_populates="analyses")


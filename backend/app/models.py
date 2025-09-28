# backend/app/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, Text, DateTime, func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    jds = relationship("JobDescription", back_populates="owner", cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="owner", cascade="all, delete-orphan")

class JobDescription(Base):
    __tablename__ = "job_descriptions"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    text = Column(Text)
    embedding = Column(Vector(768)) # Gemini embedding size
    required_skills = Column(JSON)
    nice_to_have_skills = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="jds")

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    candidate_name = Column(String, index=True)
    text = Column(Text)
    parsed_json = Column(JSON)
    embedding = Column(Vector(768)) # Gemini embedding size
    content_hash = Column(String, unique=True)
    analysis_results = Column(JSON) # Storing AI analysis here
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="resumes")

    file_path = Column(String, nullable=True)            # NEW: absolute or relative path to stored file
    original_filename = Column(String, nullable=True)    # NEW: original client filename
    mime_type = Column(String, nullable=True)            # NEW: content-type hint (e.g., application/pdf)


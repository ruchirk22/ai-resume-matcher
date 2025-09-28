# backend/app/jd.py
import asyncio
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
import traceback

from . import models, schemas, services
from .database import get_db
from .dependencies import get_current_user

router = APIRouter()

@router.post("/upload", response_model=schemas.JobDescription, status_code=status.HTTP_201_CREATED)
async def upload_jd(
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        # Enforce max JD limit (MVP requirement)
        existing_count = db.query(models.JobDescription).filter(models.JobDescription.user_id == current_user.id).count()
        if existing_count >= 3:
            raise HTTPException(status_code=400, detail="JD limit reached (max 3 for MVP). Delete one to add another.")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="JD file is empty.")

        # CRITICAL FIX: The extract_text_from_file function now correctly receives both filename and content.
        jd_text = services.extract_text_from_file(file.filename, content)
        if not jd_text.strip():
            raise HTTPException(status_code=400, detail="JD file is empty or unreadable.")

        # Concurrently get skills and embedding from Gemini API
        skills_task = services.extract_skills_from_jd(jd_text)
        embedding_task = services.get_embedding(jd_text)
        
        results = await asyncio.gather(skills_task, embedding_task, return_exceptions=True)
        
        skills, embedding = results
        
        if isinstance(skills, Exception):
            traceback.print_exception(type(skills), skills, skills.__traceback__)
            raise HTTPException(status_code=500, detail=f"AI failed to extract skills from JD: {skills}")

        if isinstance(embedding, Exception):
            traceback.print_exception(type(embedding), embedding, embedding.__traceback__)
            raise HTTPException(status_code=500, detail=f"AI failed to generate embedding for JD: {embedding}")
            
        db_jd = models.JobDescription(
            title=title,
            text=jd_text,
            embedding=embedding,
            required_skills=skills.get("required_skills", []),
            nice_to_have_skills=skills.get("nice_to_have_skills", []),
            user_id=current_user.id
        )
        db.add(db_jd)
        db.commit()
        db.refresh(db_jd)
        
        return db_jd
    except HTTPException as e:
        raise e
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {str(e)}")


@router.get("", response_model=List[schemas.JobDescription])
def list_jds(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return db.query(models.JobDescription).filter(
        models.JobDescription.user_id == current_user.id
    ).order_by(models.JobDescription.created_at.desc()).all()


@router.delete("/{jd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_jd(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db_jd = db.query(models.JobDescription).filter(
        models.JobDescription.id == jd_id,
        models.JobDescription.user_id == current_user.id
    ).first()

    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    db.delete(db_jd)
    db.commit()
    return None

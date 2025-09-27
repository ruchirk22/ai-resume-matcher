import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
import weaviate.classes as wvc

from . import models, schemas, services
from .database import get_db
from .dependencies import get_current_user
from .weaviate_client import client

router = APIRouter()

@router.post("/upload", response_model=schemas.JobDescription, status_code=status.HTTP_201_CREATED)
def upload_jd(
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- ROBUST LOGIC: ADD JD TO EXISTING LIST ---
    # The previous logic of deleting all JDs has been removed.
    print(f"Adding new JD for user {current_user.id}...")
    
    # Process the new JD
    try:
        jd_text = services.extract_text_from_file(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {e}")

    jd_embedding = services.get_embedding(jd_text)
    
    weaviate_uuid = str(uuid.uuid4())
    jd_collection = client.collections.get("JobDescription")
    jd_collection.data.insert(
        uuid=weaviate_uuid,
        properties={
            "user_id": current_user.id,
            "title": title,
            "content": jd_text,
        },
        vector=jd_embedding,
    )

    db_jd = models.JobDescription(
        title=title,
        text=jd_text,
        weaviate_id=weaviate_uuid,
        user_id=current_user.id
    )
    db.add(db_jd)
    db.commit()
    db.refresh(db_jd)
    
    print(f"Successfully added JD with ID: {db_jd.id}")
    return db_jd

@router.get("", response_model=List[schemas.JobDescription])
def list_jds(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Retrieve all job descriptions for the current user.
    """
    return db.query(models.JobDescription).filter(models.JobDescription.user_id == current_user.id).order_by(models.JobDescription.id.desc()).all()

@router.delete("/{jd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_jd(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Delete a specific job description for the current user.
    """
    print(f"Attempting to delete JD {jd_id} for user {current_user.id}")
    db_jd = db.query(models.JobDescription).filter(
        models.JobDescription.id == jd_id,
        models.JobDescription.user_id == current_user.id
    ).first()

    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    # Delete from Weaviate
    jd_collection = client.collections.get("JobDescription")
    jd_collection.data.delete_by_id(db_jd.weaviate_id)
    print(f"Deleted JD from Weaviate with UUID: {db_jd.weaviate_id}")

    # Delete from SQLite
    db.delete(db_jd)
    db.commit()
    print(f"Deleted JD from SQLite with ID: {jd_id}")
    
    return


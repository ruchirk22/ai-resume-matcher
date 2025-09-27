import uuid
import asyncio
import hashlib
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import models, schemas, services
from .database import get_db
from .dependencies import get_current_user
from .weaviate_client import client

router = APIRouter()

@router.post("/upload", response_model=List[schemas.Resume])
async def upload_resumes(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- ROBUST LOGIC: DUPLICATE CHECKING ---
    existing_hashes = db.query(models.Resume.content_hash).filter(models.Resume.user_id == current_user.id).all()
    existing_hashes_set = {h[0] for h in existing_hashes}
    print(f"Found {len(existing_hashes_set)} existing resume hashes for user {current_user.id}.")

    async def process_file(file: UploadFile):
        try:
            content = await file.read()
            # Reset pointer for text extraction
            await file.seek(0)
            
            # Create a hash of the file content to check for duplicates
            content_hash = hashlib.sha256(content).hexdigest()
            if content_hash in existing_hashes_set:
                print(f"Skipping duplicate file: {file.filename}")
                return None

            resume_text = services.extract_text_from_file(file)
            if not resume_text.strip():
                print(f"Skipping empty or unreadable file: {file.filename}")
                return None

            parsed_data = await services.parse_resume_text(resume_text)
            
            candidate_name = parsed_data.get("name", file.filename)
            if not candidate_name or candidate_name == "N/A" or "Error" in candidate_name:
                candidate_name = file.filename

            return {
                "text": resume_text,
                "parsed_data": parsed_data,
                "candidate_name": candidate_name,
                "embedding": services.get_embedding(resume_text),
                "content_hash": content_hash
            }
        except Exception as e:
            print(f"Failed to process file {file.filename}: {e}")
            return None

    processing_tasks = [process_file(file) for file in files]
    processed_results = await asyncio.gather(*processing_tasks)
    
    valid_results = [res for res in processed_results if res is not None]
    if not valid_results:
        # It's not an error if all files were duplicates
        return []

    created_resumes = []
    resume_collection = client.collections.get("Resume")
    with resume_collection.batch.dynamic() as batch:
        for result in valid_results:
            weaviate_uuid = str(uuid.uuid4())
            batch.add_object(
                uuid=weaviate_uuid,
                properties={
                    "user_id": current_user.id,
                    "candidate_name": result["candidate_name"],
                    "content": result["text"],
                },
                vector=result["embedding"],
            )
            db_resume = models.Resume(
                candidate_name=result["candidate_name"],
                text=result["text"],
                parsed_json=result["parsed_data"],
                weaviate_id=weaviate_uuid,
                user_id=current_user.id,
                content_hash=result["content_hash"]
            )
            db.add(db_resume)
            created_resumes.append(db_resume)

    db.commit()
    for resume in created_resumes:
        db.refresh(resume)
        
    print(f"Successfully added {len(created_resumes)} new resumes.")
    return created_resumes

@router.delete("/all", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_resumes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Deletes all resumes for the current user.
    """
    print(f"Deleting ALL resumes for user {current_user.id}...")
    db_resumes_to_delete = db.query(models.Resume).filter(models.Resume.user_id == current_user.id).all()
    
    resume_collection = client.collections.get("Resume")
    
    # Weaviate's delete_many is more efficient with a filter than a list of IDs
    resume_collection.data.delete_many(where=services.wvc.query.Filter.by_property("user_id").equal(current_user.id))
    print(f"Deleted resumes from Weaviate for user {current_user.id}.")

    for db_resume in db_resumes_to_delete:
        db.delete(db_resume)
    db.commit()
    print("Deleted all resumes from SQLite.")
    
    return


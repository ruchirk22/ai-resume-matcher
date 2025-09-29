# backend/app/resume.py
import uuid
import asyncio
import hashlib
import mimetypes
from datetime import datetime
from typing import List, Dict
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, status, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session
import os
import re
import logging
import fitz  # PyMuPDF
from io import BytesIO
import requests  # NEW
from uuid import uuid4
from werkzeug.utils import secure_filename

# resume.py — add a tiny, dependency-free filename sanitizer
def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "resume")
    return re.sub(r'[^A-Za-z0-9._-]+', '_', base)

# resume.py — add an upload directory (configurable via .env)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


from . import models, schemas, services, dependencies
from .database import get_db
from .dependencies import get_current_user

router = APIRouter()

logger = logging.getLogger(__name__)

# In-memory job tracking for simplicity. For production, use Redis or a DB table.
job_statuses: Dict[str, schemas.JobStatus] = {}

def _get_resume_or_404(db: Session, resume_id: int):
    """
    Returns a tuple: (resume, file_path, file_bytes, file_url)
    One of file_path or file_bytes will be present.
    """
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    file_path = (
        getattr(resume, "file_path", None)
        or getattr(resume, "filepath", None)
        or getattr(resume, "path", None)
    )
    file_url = getattr(resume, "file_url", None)
    file_bytes = getattr(resume, "file_bytes", None) or getattr(resume, "content", None)

    # If we only have a URL (e.g., Supabase public URL), fetch bytes
    if not file_path and not file_bytes and file_url:
        try:
            r = requests.get(file_url, timeout=10)
            r.raise_for_status()
            file_bytes = r.content
        except Exception:
            raise HTTPException(status_code=404, detail="Unable to fetch resume from file_url")

    # If we only have a path, ensure it exists
    if file_path and not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Resume file not found on disk")

    if not file_path and not file_bytes:
        raise HTTPException(status_code=404, detail="Resume file not available (no file_path stored).")

    return resume, file_path, file_bytes, file_url


def _detect_mime(file_path: str) -> str:
    mime, _ = mimetypes.guess_type(file_path)
    return mime or "application/octet-stream"

async def process_resume_files(file_data: List[dict], user_id: int, job_id: str, db: Session):
    """
    Background task to process uploaded resumes.
    
    This function:
    1. Extracts text from resume files
    2. Concurrently parses resume content and generates embeddings
    3. Stores the structured data in the database
    4. Updates job status for progress tracking
    """
    total_files = len(file_data)
    job_statuses[job_id] = schemas.JobStatus(job_id=job_id, status="processing", progress=0, total=total_files)
    
    # Get existing content hashes to avoid duplicates
    existing_hashes = {h[0] for h in db.query(models.Resume.content_hash).filter(models.Resume.user_id == user_id).all()}
    
    for i, file_item in enumerate(file_data):
        filename = file_item["filename"]
        content = file_item["content"]
        # Save file to disk
        safe_name = secure_filename(filename or f"resume_{uuid4()}")
        dest_path = os.path.abspath(os.path.join(UPLOAD_DIR, f"{uuid4()}_{safe_name}"))
        with open(dest_path, "wb") as out:
            out.write(content)
        
        try:
            # Generate hash to identify duplicates
            content_hash = hashlib.sha256(content).hexdigest()
            if content_hash in existing_hashes:
                logger.info("Skipping duplicate resume: %s", filename)
                continue

            # Extract text from file
            resume_text = services.extract_text_from_file(filename, content)
            if not resume_text.strip():
                logger.info("Skipping empty resume: %s", filename)
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
                continue

            # Concurrently parse and embed for efficiency
            parsed_data_task = services.parse_resume_text(resume_text)
            embedding_task = services.get_embedding(resume_text)
            parsed_data, embedding = await asyncio.gather(parsed_data_task, embedding_task)

            # Get candidate name from parsed data or use filename as fallback
            candidate_name = parsed_data.get("name", filename)
            if not candidate_name or candidate_name == "N/A":
                candidate_name = filename

            # Create resume record with structured data and file pointer
            db_resume = models.Resume(
                candidate_name=candidate_name,
                text=resume_text,
                parsed_json=parsed_data,
                embedding=embedding,
                user_id=user_id,
                content_hash=content_hash,
                analysis_results={
                    "processed": True,
                    "processed_at": str(datetime.now()),
                    "skills_extracted": len(parsed_data.get("skills", [])),
                },
                file_path=dest_path,
                original_filename=filename or None,
                mime_type=mimetypes.guess_type(filename)[0] if filename else None,
            )
            db.add(db_resume)
            db.commit()
            
        except Exception as e:
            logger.exception("Failed to process %s", filename)
        finally:
            # Update progress regardless of success/failure
            job_statuses[job_id].progress = i + 1

    # Mark job as completed
    job_statuses[job_id].status = "completed"
    logger.info("Job %s completed.", job_id)


@router.post("/bulk-upload", status_code=status.HTTP_202_ACCEPTED)
async def bulk_upload_resumes(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    job_id = str(uuid.uuid4())

    # Enforce resume limit (20)
    existing = db.query(models.Resume).filter(models.Resume.user_id == current_user.id).count()
    remaining_slots = 20 - existing
    if remaining_slots <= 0:
        raise HTTPException(status_code=400, detail="Resume limit reached (max 20 for MVP). Delete some to upload more.")

    # Preload file data and detect duplicates synchronously so we can notify the user
    file_data = []
    duplicates = []

    # Get existing content hashes to detect duplicates
    existing_hashes = {h[0] for h in db.query(models.Resume.content_hash).filter(models.Resume.user_id == current_user.id).all()}

    for file in files:
        if len(file_data) >= remaining_slots:
            break
        try:
            content = await file.read()
            content_hash = hashlib.sha256(content).hexdigest()
            if content_hash in existing_hashes:
                # record duplicate filename and skip scheduling
                duplicates.append(file.filename or 'unknown')
                continue
            file_data.append({"filename": file.filename, "content": content})
            # also add this hash to existing_hashes to prevent duplicates in same batch
            existing_hashes.add(content_hash)
        except Exception as e:
            logger.exception("Failed to read %s", file.filename)

    if len(file_data) > 0:
        background_tasks.add_task(process_resume_files, file_data, current_user.id, job_id, db)
        return {"job_id": job_id, "message": f"Started processing {len(file_data)} resumes (limit enforced).", "duplicates": duplicates}
    else:
        # Nothing to process (all duplicates or read errors)
        return {"job_id": None, "message": "No new resumes to process (duplicates or read errors).", "duplicates": duplicates}

@router.get("/bulk-upload/status/{job_id}", response_model=schemas.JobStatus)
def get_job_status(job_id: str):
    status = job_statuses.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status

@router.delete("/all", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_resumes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db.query(models.Resume).filter(models.Resume.user_id == current_user.id).delete()
    db.commit()

@router.get("/{resume_id}/file")
def get_resume_file(resume_id: int, db: Session = Depends(dependencies.get_db)):
    resume, file_path, file_bytes, file_url = _get_resume_or_404(db, resume_id)

    if file_path:
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type=_detect_mime(file_path),
        )

    # Fallback to bytes (from DB or fetched via URL)
    guessed_name = (os.path.basename(file_url) if file_url else f"resume_{resume_id}")
    mime = _detect_mime(guessed_name)
    buf = BytesIO(file_bytes)
    headers = {
        "Content-Disposition": f'attachment; filename="{guessed_name}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(buf, media_type=mime, headers=headers)


# ---------------------------------------------------------------------
# NEW: Resume preview
#   - PDF -> first page PNG image
#   - DOCX/TXT/unknown -> text preview (first N chars)
# ---------------------------------------------------------------------
@router.get("/{resume_id}/preview")
def get_resume_preview(resume_id: int, db: Session = Depends(dependencies.get_db)):
    resume, file_path, file_bytes, file_url = _get_resume_or_404(db, resume_id)

    # Detect type from path or url (fallback to octet-stream)
    name_for_guess = file_path or (file_url or "")
    mime = _detect_mime(name_for_guess).lower()

    is_pdf = ("pdf" in mime) or (name_for_guess.lower().endswith(".pdf"))

    # PDF → first page PNG
    if is_pdf:
        try:
            if file_path:
                doc = fitz.open(file_path)
            else:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
            if doc.page_count == 0:
                return PlainTextResponse("Empty PDF", status_code=200)
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=150)
            buf = BytesIO(pix.tobytes("png"))
            return StreamingResponse(buf, media_type="image/png", headers={"Cache-Control": "no-store"})
        except Exception as e:
            return PlainTextResponse(f"Preview unavailable (PDF render failed): {e}", status_code=200)

    # Non-PDF → return plaintext preview (first 10k chars)
    try:
        if file_path and os.path.isfile(file_path):
            # Try read as text
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(10_000)
            if text.strip():
                return PlainTextResponse(text, status_code=200, headers={"Cache-Control": "no-store"})
        else:
            # We have bytes (from URL or DB); decode as utf-8 best-effort
            text = (file_bytes or b"").decode("utf-8", errors="ignore")[:10_000]
            if text.strip():
                return PlainTextResponse(text, status_code=200, headers={"Cache-Control": "no-store"})
        return PlainTextResponse("Preview unavailable for this file type.", status_code=200)
    except Exception as e:
        return PlainTextResponse(f"Preview unavailable: {e}", status_code=200)

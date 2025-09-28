# backend/app/candidate_status.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from . import dependencies, database

router = APIRouter(prefix="/candidates/status", tags=["candidate-status"])

# Allowed statuses for the workflow
StatusLiteral = Literal["New", "Reviewed", "Shortlisted", "Interview", "Contacted", "Rejected"]

# -------------------------
# Table bootstrap (idempotent)
# -------------------------
def ensure_table_exists():
    ddl = """
    CREATE TABLE IF NOT EXISTS candidate_statuses (
        jd_id INTEGER NOT NULL,
        resume_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'New',
        note TEXT,
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        PRIMARY KEY (jd_id, resume_id)
    );
    """
    with database.SessionLocal() as db:
        db.execute(text(ddl))
        db.commit()

# Ensure the table on module import
ensure_table_exists()

# -------------------------
# Schemas
# -------------------------
class BulkStatusUpdateRequest(BaseModel):
    jd_id: int = Field(..., description="Job description ID")
    resume_ids: List[int] = Field(..., min_items=1, description="Resume IDs to update")
    status: StatusLiteral
    note: Optional[str] = None

class StatusRecord(BaseModel):
    resume_id: int
    status: StatusLiteral
    note: Optional[str] = None
    updated_at: datetime

class StatusListResponse(BaseModel):
    jd_id: int
    statuses: List[StatusRecord]

# -------------------------
# Endpoints
# -------------------------

@router.get("/{jd_id}", response_model=StatusListResponse)
def get_statuses_for_jd(
    jd_id: int,
    db: Session = Depends(dependencies.get_db),
):
    sql = text("""
        SELECT resume_id, status, note, updated_at
        FROM candidate_statuses
        WHERE jd_id = :jd_id
        ORDER BY updated_at DESC
    """)
    rows = db.execute(sql, {"jd_id": jd_id}).mappings().all()

    statuses = [
        StatusRecord(
            resume_id=row["resume_id"],
            status=row["status"],
            note=row["note"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    return StatusListResponse(jd_id=jd_id, statuses=statuses)

@router.patch("/bulk")
def bulk_update_status(
    payload: BulkStatusUpdateRequest,
    db: Session = Depends(dependencies.get_db),
):
    # Upsert on (jd_id, resume_id)
    sql = text("""
        INSERT INTO candidate_statuses (jd_id, resume_id, status, note, updated_at)
        VALUES (:jd_id, :resume_id, :status, :note, NOW())
        ON CONFLICT (jd_id, resume_id)
        DO UPDATE SET status = EXCLUDED.status,
                      note = EXCLUDED.note,
                      updated_at = NOW();
    """)

    for rid in payload.resume_ids:
        db.execute(sql, {
            "jd_id": payload.jd_id,
            "resume_id": rid,
            "status": payload.status,
            "note": payload.note
        })
    db.commit()

    return {
        "updated": len(payload.resume_ids),
        "status": payload.status,
        "jd_id": payload.jd_id,
        "resume_ids": payload.resume_ids,
    }

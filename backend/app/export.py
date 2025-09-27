import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import weaviate.classes as wvc

from . import models, services
from .database import get_db
from .dependencies import get_current_user
from .weaviate_client import client

router = APIRouter()

@router.post("/csv/{jd_id}")
def export_candidates_to_csv(
    jd_id: int,
    category: str = None, # Optional category to filter by: "Strong", "Good", "Weak"
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Verify the JD exists and belongs to the user
    db_jd = db.query(models.JobDescription).filter(
        models.JobDescription.id == jd_id,
        models.JobDescription.user_id == current_user.id
    ).first()

    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    # 2. Get JD vector from Weaviate to find relevant candidates
    jd_collection = client.collections.get("JobDescription")
    jd_object = jd_collection.query.fetch_object_by_id(db_jd.weaviate_id, include_vector=True)
    
    if not jd_object or not jd_object.vector:
        raise HTTPException(status_code=404, detail="JD vector not found")
    
    jd_vector = jd_object.vector['default']

    # 3. Perform vector search in Weaviate for the most relevant resumes
    resume_collection = client.collections.get("Resume")
    response = resume_collection.query.near_vector(
        near_vector=jd_vector,
        limit=20, # Analyze the same top 20 candidates as the dashboard
        filters=wvc.query.Filter.by_property("user_id").equal(current_user.id)
    )

    # 4. Prepare data for CSV, using the new AI evaluation logic
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header row
    writer.writerow(["Candidate Name", "Email", "Phone", "Category", "Match Percentage", "Rationale", "Matched Skills", "Missing Skills"])

    if response.objects:
        for item in response.objects:
            db_resume = db.query(models.Resume).filter(
                models.Resume.weaviate_id == str(item.uuid)
            ).first()

            if db_resume:
                # Use the same powerful AI evaluation for consistency
                ai_evaluation = services.evaluate_candidate_with_ai(db_jd.text, db_resume.text)
                
                if "error" not in ai_evaluation:
                    match_category = ai_evaluation.get("category", "Weak")
                    
                    # If a category filter is applied, skip candidates that don't match
                    if category and category != "All" and category != match_category:
                        continue
                    
                    # Safely get parsed data for contact info
                    parsed = db_resume.parsed_json or {}
                    email = parsed.get("email", "N/A")
                    phone = parsed.get("phone", "N/A")
                    
                    # Write the enriched data to the CSV row
                    writer.writerow([
                        db_resume.candidate_name,
                        email,
                        phone,
                        match_category,
                        ai_evaluation.get("match_percentage", 0),
                        ai_evaluation.get("rationale", ""),
                        ", ".join(ai_evaluation.get("matched_skills", [])),
                        ", ".join(ai_evaluation.get("missing_skills", []))
                    ])

    # 5. Create a streaming response to return the CSV file
    output.seek(0)
    response = StreamingResponse(iter([output.read()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=shortlist_jd_{jd_id}.csv"
    
    return response

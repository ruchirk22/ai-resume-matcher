from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from typing import List
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
import weaviate.classes as wvc

from .database import engine, get_db
from . import models, schemas, services, crud
from .dependencies import get_current_user
from .weaviate_client import client
from .auth import router as auth_router
from .jd import router as jd_router
from .resume import router as resume_router
from .export import router as export_router

load_dotenv()
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Resume Matcher API")

origins = ["http://localhost:3000"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- The New Smart Candidates Endpoint ---
@app.get("/candidates/{jd_id}", response_model=List[schemas.CandidateMatch], tags=["candidates"])
async def get_smart_candidate_matches(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_jd = db.query(models.JobDescription).filter(models.JobDescription.id == jd_id, models.JobDescription.user_id == current_user.id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    # Step 1: Get top similar resumes from Weaviate (fast)
    jd_collection = client.collections.get("JobDescription")
    try:
        jd_object = jd_collection.query.fetch_object_by_id(db_jd.weaviate_id, include_vector=True)
        jd_vector = jd_object.vector['default']
    except Exception:
        raise HTTPException(status_code=404, detail="JD vector not found in Weaviate")

    resume_collection = client.collections.get("Resume")
    response = resume_collection.query.near_vector(
        near_vector=jd_vector, limit=20,
        filters=wvc.query.Filter.by_property("user_id").equal(current_user.id)
    )
    if not response.objects:
        return []

    # Step 2: Identify which resumes need new analysis
    resumes_to_analyze_items = []
    final_results = []
    
    for item in response.objects:
        db_resume = db.query(models.Resume).filter(models.Resume.weaviate_id == str(item.uuid)).first()
        if not db_resume:
            continue
            
        existing_analysis = db.query(models.Analysis).filter(
            models.Analysis.resume_id == db_resume.id,
            models.Analysis.jd_id == jd_id
        ).first()

        if existing_analysis:
            # Already analyzed! Get from our "memory" (fast)
            final_results.append(schemas.CandidateMatch(resume=db_resume, **schemas.Analysis.from_orm(existing_analysis).model_dump()))
        else:
            # Needs analysis! Add to the queue
            resumes_to_analyze_items.append(item)
    
    # Step 3: Run AI analysis ONLY on the new resumes
    if resumes_to_analyze_items:
        async def evaluate_batch(batch):
            tasks = [services.evaluate_candidate_with_ai(db_jd.text, item.properties.get("content", "")) for item in batch]
            return await asyncio.gather(*tasks)

        batch_size = 5
        for i in range(0, len(resumes_to_analyze_items), batch_size):
            batch_items = resumes_to_analyze_items[i:i+batch_size]
            evaluations = await evaluate_batch(batch_items)
            
            for item, analysis_data in zip(batch_items, evaluations):
                db_resume = db.query(models.Resume).filter(models.Resume.weaviate_id == str(item.uuid)).first()
                if db_resume and analysis_data:
                    # Save the new analysis to our "memory"
                    new_analysis = models.Analysis(
                        resume_id=db_resume.id,
                        jd_id=jd_id,
                        **analysis_data
                    )
                    db.add(new_analysis)
                    db.commit()
                    db.refresh(new_analysis)
                    final_results.append(schemas.CandidateMatch(resume=db_resume, **schemas.Analysis.from_orm(new_analysis).model_dump()))

    return sorted(final_results, key=lambda x: x.match_percentage, reverse=True)

# Include all other routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(jd_router, prefix="/jd", tags=["jd"])
app.include_router(resume_router, prefix="/resume", tags=["resume"])
app.include_router(export_router, prefix="/export", tags=["export"])

@app.get("/")
def read_root():
    return {"status": "API is running"}


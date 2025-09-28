# backend/app/main.py
import asyncio
import datetime
import math
from typing import List, Dict, Any
import re
from typing import Tuple
from collections import Counter

# --- NEW imports for offline preliminary scoring ---
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
# alias sklearn cosine to avoid overriding the existing embedding cosine_similarity helper
from sklearn.metrics.pairwise import cosine_similarity as _sklearn_cosine

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from . import models, schemas, services
from .dependencies import get_current_user
from .auth import router as auth_router
from .jd import router as jd_router
from .resume import router as resume_router
from .candidate_status import router as candidate_status_router
import os

UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Resume Matcher API")

# --- System Limits (MVP requirements) ---
MAX_JDS = 3
MAX_RESUMES = 20

origins = [
    "http://localhost:3000",
    "http://localhost:3001",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Reusable Ranking Engine ---

def calculate_candidate_match(resume: models.Resume, db_jd: models.JobDescription) -> schemas.CandidateMatch:
    """Unified ranking engine for resume matching.

    Behavior (simplified – no more 'Pending'):
    - If per-JD AI analysis exists (analysis_results['jd_<id>']) -> return stored AI result (Strong|Good|Weak)
    - Else compute a fast heuristic preliminary score (match_rating='Preliminary') based on JD skills vs parsed resume skills.
    - If JD has no skills defined or resume has no parsed skills, still return a Preliminary result with score 0 (instead of 'Pending').
    """
    # Look for per-JD stored analysis first
    if resume.analysis_results and isinstance(resume.analysis_results, dict):
        jd_key = f"jd_{db_jd.id}"
        if jd_key in resume.analysis_results:
            stored = resume.analysis_results[jd_key]
            return schemas.CandidateMatch(
                resume=resume,
                score=stored.get("score", 0.0),
                match_rating=stored.get("match_rating", "Preliminary"),
                matched_skills=stored.get("matched_skills", []) or [],
                missing_skills=stored.get("missing_skills", []) or [],
                analyzed_at=stored.get("analyzed_at"),
                similarity=stored.get("similarity"),
                resume_excerpt=(resume.text or "")[:300]
            )

    # No AI analysis yet -> compute our improved offline preliminary score using the
    # shared helper. This returns a dict with score, matched_skills, missing_skills, etc.
    jd_text = getattr(db_jd, "text", "") or getattr(db_jd, "jd_text", "") or ""
    jd_req = db_jd.required_skills or []
    jd_nice = db_jd.nice_to_have_skills or []
    prelim = _compute_prelim_score(jd_text, jd_req, jd_nice, resume.text or "")

    return schemas.CandidateMatch(
        resume=resume,
        score=prelim.get("score", 0.0),
        match_rating=prelim.get("match_rating", "Preliminary"),
        matched_skills=prelim.get("matched_skills", []) or [],
        missing_skills=prelim.get("missing_skills", []) or [],
        analyzed_at=prelim.get("analyzed_at"),
        similarity=prelim.get("similarity"),
        resume_excerpt=prelim.get("resume_excerpt", (resume.text or "")[:300])
    )

# ========== Preliminary scoring helpers (offline) ==========

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-+/#.]*")
YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(\+?\s*)?(?:years?|yrs)\b", re.IGNORECASE)

def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\x00", " ")
    return " ".join(_WORD_RE.findall(s.lower()))

def _extract_years_of_experience(text: str) -> float:
    years = 0.0
    for m in YEARS_RE.finditer(text or ""):
        try:
            val = float(m.group(1))
            if val > years:
                years = val
        except:
            continue
    return min(years, 20.0)

def _list_from_field(val) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
        return [x.strip() for x in val.split(",") if x.strip()]
    return []

def _dedup_keep_order(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out

def _fuzzy_contains(haystack: str, needle: str, threshold: int = 85) -> bool:
    if not needle:
        return False
    if needle.lower() in haystack:
        return True
    score = fuzz.partial_ratio(needle.lower(), haystack)
    return score >= threshold

def _match_skills(resume_text_norm: str, skills: List[str], thresh: int) -> Tuple[List[str], List[str]]:
    matched, missing = [], []
    for sk in skills:
        if _fuzzy_contains(resume_text_norm, sk, thresh):
            matched.append(sk)
        else:
            missing.append(sk)
    return matched, missing

def _tfidf_cosine(jd_text: str, resume_text: str) -> float:
    a = _normalize_text(jd_text)
    b = _normalize_text(resume_text)
    if not a or not b:
        return 0.0
    vec = TfidfVectorizer(min_df=1, ngram_range=(1,2))
    mat = vec.fit_transform([a, b])
    try:
        sim = _sklearn_cosine(mat[0:1], mat[1:2])[0][0]
        return max(0.0, min(1.0, float(sim)))
    except Exception:
        return 0.0

def _get_excerpt(text: str, length: int = 600) -> str:
    if not text:
        return ""
    t = " ".join(text.split())
    return t[:length]

def _compute_prelim_score(jd_text: str, jd_req_skills: List[str], jd_nice_skills: List[str], resume_text: str) -> Dict[str, Any]:
    """
    Weighted blend (fully offline):
      - Required skills coverage: 55%
      - Nice-to-have skills coverage: 20%
      - TF-IDF cosine similarity: 20%
      - Years of experience regex heuristic: 5% (capped at 10 for scoring)
    """
    resume_text_norm = _normalize_text(resume_text)
    req = _dedup_keep_order([s for s in jd_req_skills if s])
    nice = _dedup_keep_order([s for s in jd_nice_skills if s])

    matched_req, missing_req = _match_skills(resume_text_norm, req, 85)
    matched_nice, _ = _match_skills(resume_text_norm, nice, 85)

    req_cov = (len(matched_req) / len(req)) if len(req) > 0 else 0.0
    nice_cov = (len(matched_nice) / max(1, len(nice)))
    tfidf = _tfidf_cosine(jd_text or "", resume_text or "")

    years = _extract_years_of_experience(resume_text)
    exp_factor = min(years / 10.0, 1.0)

    score = (
        0.55 * req_cov +
        0.20 * nice_cov +
        0.20 * tfidf +
        0.05 * exp_factor
    ) * 100.0

    return {
        "score": float(round(score, 2)),
        "similarity": float(round(tfidf, 4)),
        "matched_skills": matched_req,
        "missing_skills": missing_req,
        "matched_nice_to_have": matched_nice,
        "resume_excerpt": _get_excerpt(resume_text, 600),
        "match_rating": "Preliminary",
        "rationale": None,
        "analyzed_at": None,
    }

# --- Helper: Per-JD AI Analysis Cache on Resume ---

def cosine_similarity(vec_a, vec_b):
    """Robust cosine similarity with defensive guards against malformed vectors.

    Accepts sequences, pgvector objects (with tolist), memoryviews, or returns 0.0 otherwise.
    Ensures no exceptions propagate (always safe in scoring path).
    """
    try:
        # Avoid ambiguous truth-value checks on numpy/pgvector objects
        if vec_a is None or vec_b is None:
            return 0.0
        if hasattr(vec_a, 'tolist'):
            vec_a = vec_a.tolist()
        if hasattr(vec_b, 'tolist'):
            vec_b = vec_b.tolist()
        if isinstance(vec_a, memoryview):
            vec_a = list(vec_a)
        if isinstance(vec_b, memoryview):
            vec_b = list(vec_b)
        if not isinstance(vec_a, (list, tuple)) or not isinstance(vec_b, (list, tuple)):
            return 0.0
        if len(vec_a) == 0 or len(vec_b) == 0:
            return 0.0
        dot = 0.0
        sum_a = 0.0
        sum_b = 0.0
        for a, b in zip(vec_a, vec_b):
            try:
                fa = float(a)
                fb = float(b)
            except (TypeError, ValueError):
                continue
            dot += fa * fb
            sum_a += fa * fa
            sum_b += fb * fb
        if sum_a == 0.0 or sum_b == 0.0:
            return 0.0
        return dot / (math.sqrt(sum_a) * math.sqrt(sum_b))
    except Exception:
        return 0.0

async def ensure_analysis_for_jd(
    resume: models.Resume,
    db_jd: models.JobDescription,
    db,
    force: bool = False,
    skip_ai: bool = False
) -> Dict[str, Any]:
    """Ensures there is an AI analysis for (resume, jd). Stores analyses per-JD inside `analysis_results`.

    Data model stored in Resume.analysis_results:
    {
        "jd_<id>": {
            "score": float,
            "match_rating": str,
            "matched_skills": [...],
            "missing_skills": [...],
            "rationale": str,
            "analyzed_at": ts
        },
        ...
    }

    NOTE: This replaces the earlier single-object analysis. Backward compatibility: if the existing
    structure is *not* a dict keyed by jd_ we will wrap it under a legacy key and recompute.
    """
    if not db_jd.required_skills:
        return {
            "score": 0.0,
            "match_rating": "Weak",
            "matched_skills": [],
            "missing_skills": [],
            "rationale": "Job description has no required skills defined.",
        }

    key = f"jd_{db_jd.id}"
    container: Dict[str, Any] = {}
    raw = resume.analysis_results
    if isinstance(raw, dict) and any(k.startswith("jd_") for k in raw.keys()):
        container = raw
    else:
        # Legacy / empty -> initialize container
        container = {} if not isinstance(raw, dict) else {}

    # Reuse unless force or missing
    if not force and key in container:
        return container[key]

    # Call AI to evaluate
    jd_skills = {
        "required_skills": db_jd.required_skills or [],
        "nice_to_have_skills": db_jd.nice_to_have_skills or []
    }

    if skip_ai:
        ai_result = {"matched_skills": [], "missing_skills": [], "rationale": "Skipped AI (heuristic-only mode)."}
    else:
        try:
            ai_result = await services.evaluate_candidate_for_jd(
                db_jd.text or "", jd_skills, resume.text or ""
            )
        except Exception as e:
            print(f"AI evaluation failed for resume {resume.id}: {e}")
            # Fallback: use parsed skills only
            parsed = (resume.parsed_json or {}).get("skills", []) if resume.parsed_json else []
            matched_skills = [s for s in parsed if s.lower() in {r.lower() for r in jd_skills["required_skills"] + jd_skills["nice_to_have_skills"]}]
            ai_result = {
                "matched_skills": matched_skills,
                "missing_skills": [],
                "rationale": "Fallback rationale: AI unavailable; matched skills derived from parsed resume only."
            }

    required_set_lower = {s.lower() for s in jd_skills["required_skills"]}
    nice_set_lower = {s.lower() for s in jd_skills["nice_to_have_skills"]}

    # Normalize matched skills (trust AI but project back to canonical names from JD lists when possible)
    matched_ai = ai_result.get("matched_skills", []) or []
    matched_normalized: List[str] = []
    # Build canonical mapping
    canonical_map = {s.lower(): s for s in jd_skills["required_skills"] + jd_skills["nice_to_have_skills"]}
    seen_lower = set()
    for skill in matched_ai:
        low = skill.lower()
        if low in seen_lower:
            continue
        seen_lower.add(low)
        matched_normalized.append(canonical_map.get(low, skill))

    # Compute missing required skills ourselves (do not trust AI missing list)
    matched_required_lower = {s.lower() for s in matched_normalized if s.lower() in required_set_lower}
    missing_required = [canonical_map[r] for r in required_set_lower - matched_required_lower if r in canonical_map]

    # Score components
    matched_required_count = len(matched_required_lower)
    required_total = max(len(required_set_lower), 1)
    required_score = (matched_required_count / required_total) * 90

    matched_nice_lower = {s.lower() for s in matched_normalized if s.lower() in nice_set_lower}
    nice_total = len(nice_set_lower)
    nice_score = (len(matched_nice_lower) / nice_total) * 10 if nice_total > 0 else 0

    total_score = round(required_score + nice_score, 2)
    if total_score > 70:
        match_rating = "Strong"
    elif total_score > 35:
        match_rating = "Good"
    else:
        match_rating = "Weak"

    # Pre-compute similarity (even if low) for transparency
    if resume.embedding is not None and db_jd.embedding is not None:
        similarity = cosine_similarity(resume.embedding, db_jd.embedding)
    else:
        similarity = 0.0

    analysis_obj = {
        "score": total_score,
        "match_rating": match_rating,
        "matched_skills": matched_normalized,
        "missing_skills": missing_required,
        "rationale": ai_result.get("rationale", "No rationale provided."),
        "analyzed_at": str(datetime.datetime.utcnow()),
        "similarity": round(similarity, 4)
    }

    container[key] = analysis_obj
    resume.analysis_results = container
    try:
        db.add(resume)
        db.commit()
    except Exception as e:
        print(f"Failed to persist analysis for resume {resume.id}: {e}")
        db.rollback()

    return analysis_obj

# --- API Endpoints ---

@app.get("/candidates/{jd_id}", response_model=List[schemas.CandidateMatch], tags=["candidates"])
def get_candidate_matches(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Endpoint for the main candidate list view. Uses an offline preliminary scoring blend.

    Implementation replaced with TF-IDF + fuzzy-skill matching blend. Returns the same
    response model as before. This keeps the decorator and signature unchanged.
    """
    db_jd = db.query(models.JobDescription).filter_by(id=jd_id, user_id=current_user.id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    # Use the unified ranking engine which now uses the improved offline score when
    # AI analysis for this resume+JD is not present.
    all_resumes = db.query(models.Resume).filter_by(user_id=current_user.id).all()
    results = [calculate_candidate_match(resume, db_jd) for resume in all_resumes]
    valid_results = [res for res in results if res is not None]
    valid_results.sort(key=lambda x: x.score, reverse=True)
    return valid_results

@app.post("/candidates/analyze", response_model=schemas.DetailedCandidate, tags=["candidates"])
async def analyze_top_candidate(
    jd_id: int,
    resume_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Single candidate analysis aligned with per-JD storage model.

    Now simply delegates to ensure_analysis_for_jd and returns enriched object.
    Supports force re-analysis for a single resume (useful for debugging or updated JDs).
    """
    db_jd = db.query(models.JobDescription).filter_by(id=jd_id, user_id=current_user.id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")
    resume_obj = db.query(models.Resume).filter_by(id=resume_id, user_id=current_user.id).first()
    if not resume_obj:
        raise HTTPException(status_code=404, detail="Resume not found")
    analysis = await ensure_analysis_for_jd(resume_obj, db_jd, db, force=force)
    return schemas.DetailedCandidate(
        resume=resume_obj,
        score=analysis["score"],
        match_rating=analysis["match_rating"],
        matched_skills=analysis["matched_skills"],
        missing_skills=analysis["missing_skills"],
        rationale=analysis.get("rationale", "No rationale."),
        analyzed_at=analysis.get("analyzed_at"),
        similarity=analysis.get("similarity"),
        resume_excerpt=(resume_obj.text or "")[:300]
    )

@app.get("/candidates/full-analysis/{jd_id}", response_model=List[schemas.DetailedCandidate], tags=["candidates"])
async def full_analysis_for_jd(
    jd_id: int,
    force: bool = Query(False, description="Force re-analysis even if cached"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Unified endpoint returning FULL ranked list + rationale for every candidate in one call.

    Steps:
    - For each resume: ensure (JD, resume) analysis exists (AI call if missing / forced)
    - Compute / reuse score & rating
    - Sort by score DESC
    - Return list of DetailedCandidate objects

    This is optimized for recruiter UX and ensures consistency.
    """
    db_jd = db.query(models.JobDescription).filter_by(id=jd_id, user_id=current_user.id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    resumes = db.query(models.Resume).filter_by(user_id=current_user.id).all()
    if not resumes:
        return []

    # Evaluate concurrently (limit concurrency to avoid rate limits)
    semaphore = asyncio.Semaphore(5)

    async def evaluate(resume: models.Resume):
        async with semaphore:
            # Semantic pre-filter: if similarity very low and not forced & no prior analysis, skip expensive AI
            if resume.embedding is not None and db_jd.embedding is not None:
                sim = cosine_similarity(resume.embedding, db_jd.embedding)
            else:
                sim = 0.0
            key = f"jd_{jd_id}"
            has_prior = isinstance(resume.analysis_results, dict) and key in resume.analysis_results
            if sim < 0.15 and not force and not has_prior:
                # Provide heuristic preliminary instead of 'Pending'
                prelim = calculate_candidate_match(resume, db_jd)
                return schemas.DetailedCandidate(
                    resume=resume,
                    score=prelim.score,
                    match_rating="Preliminary",
                    matched_skills=prelim.matched_skills,
                    missing_skills=prelim.missing_skills,
                    rationale="Heuristic only (low similarity). Use force to run full AI analysis.",
                    analyzed_at=None,
                    similarity=round(sim,4),
                    resume_excerpt=prelim.resume_excerpt
                )
            analysis = await ensure_analysis_for_jd(resume, db_jd, db, force=force)
            return schemas.DetailedCandidate(
                resume=resume,
                score=analysis["score"],
                match_rating=analysis["match_rating"],
                matched_skills=analysis["matched_skills"],
                missing_skills=analysis["missing_skills"],
                rationale=analysis["rationale"],
                analyzed_at=analysis.get("analyzed_at"),
                similarity=analysis.get("similarity"),
                resume_excerpt=(resume.text or "")[:300]
            )

    detailed_list = await asyncio.gather(*(evaluate(r) for r in resumes))
    # Sort descending by score but keep Pending (0) at bottom without implying Weak
    detailed_list.sort(key=lambda c: c.score, reverse=True)
    return detailed_list


@app.post("/candidates/analyze/preliminary/{jd_id}", response_model=List[schemas.DetailedCandidate], tags=["candidates"])
async def analyze_preliminary_only(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # This endpoint analyzes only the resumes that do NOT yet have a per-JD AI
    # analysis stored under resume.analysis_results['jd_<id>'].
    # - For each missing resume: call ensure_analysis_for_jd(...) which will run AI
    #   and persist the result into resume.analysis_results[jd_<id>] (unless AI fails).
    # - For already-analyzed resumes: leave them untouched.
    # Finally return a full list of DetailedCandidate objects (mix of AI and preliminary).
    db_jd = db.query(models.JobDescription).filter_by(id=jd_id, user_id=current_user.id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    resumes = db.query(models.Resume).filter_by(user_id=current_user.id).all()
    key = f"jd_{jd_id}"

    # Find resumes that are missing AI analysis for this JD
    prelim_targets = [r for r in resumes if not (isinstance(r.analysis_results, dict) and key in (r.analysis_results or {}))]

    # Run AI analysis for missing ones (persisted by ensure_analysis_for_jd)
    for r in prelim_targets:
        try:
            await ensure_analysis_for_jd(r, db_jd, db, force=False, skip_ai=False)
        except Exception as e:
            # If AI fails, we do not overwrite prior state; we simply log and continue
            print(f"AI analysis failed for resume {r.id}: {e}")

    # Build the response: prefer persisted AI analysis if available, else compute preliminary
    out: List[schemas.DetailedCandidate] = []
    for r in resumes:
        if isinstance(r.analysis_results, dict) and key in r.analysis_results:
            a = r.analysis_results[key]
            out.append(schemas.DetailedCandidate(
                resume=r,
                score=a.get("score", 0.0),
                match_rating=a.get("match_rating", "Weak"),
                matched_skills=a.get("matched_skills", []),
                missing_skills=a.get("missing_skills", []),
                rationale=a.get("rationale", ""),
                analyzed_at=a.get("analyzed_at"),
                similarity=a.get("similarity"),
                resume_excerpt=(r.text or "")[:300]
            ))
        else:
            prelim = calculate_candidate_match(r, db_jd)
            out.append(schemas.DetailedCandidate(
                resume=r,
                score=prelim.score,
                match_rating=prelim.match_rating,
                matched_skills=prelim.matched_skills,
                missing_skills=prelim.missing_skills,
                rationale="Heuristic only (awaiting full analysis).",
                analyzed_at=prelim.analyzed_at,
                similarity=prelim.similarity,
                resume_excerpt=prelim.resume_excerpt
            ))

    out.sort(key=lambda c: c.score, reverse=True)
    return out

@app.get("/candidates/status/{jd_id}", response_model=schemas.JDAnalysisStatus, tags=["candidates"])
def jd_analysis_status(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_jd = db.query(models.JobDescription).filter_by(id=jd_id, user_id=current_user.id).first()
    if not db_jd:
        raise HTTPException(status_code=404, detail="Job Description not found")
    resumes = db.query(models.Resume).filter_by(user_id=current_user.id).all()
    key = f"jd_{jd_id}"
    analyzed = 0
    preliminary = 0
    pending = 0
    for r in resumes:
        if isinstance(r.analysis_results, dict) and key in r.analysis_results:
            analyzed += 1
        else:
            # We treat everything else as preliminary-ready, no true 'pending' separate state
            preliminary += 1
    total = len(resumes)
    if total == 0:
        total = 1  # avoid div zero in pct
    return schemas.JDAnalysisStatus(
        jd_id=jd_id,
        total_resumes=len(resumes),
        analyzed=analyzed,
        preliminary=preliminary,
        pending=pending,
        analyzed_pct=round(analyzed*100/total,2),
        preliminary_pct=round(preliminary*100/total,2),
        pending_pct=round(pending*100/total,2)
    )

@app.post("/admin/cache/flush", tags=["admin"])
def flush_caches_endpoint(current_user: models.User = Depends(get_current_user)):
    """Flush in-memory caches (JD skill extraction, generic). Admin-lite utility.
    For now any authenticated user can call; in future enforce role."""
    flushed = services.flush_caches()
    return {"detail": "Caches flushed", **flushed}

# --- Include Routers ---
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(jd_router, prefix="/jd", tags=["jd"])
app.include_router(resume_router, prefix="/resume", tags=["resume"])
# candidate_status_router already has its own prefix defined in the module
app.include_router(candidate_status_router, tags=["candidate-status"])
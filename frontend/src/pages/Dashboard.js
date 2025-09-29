// frontend/src/pages/Dashboard.js
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';
import Modal from '../components/Modal';
import toast from 'react-hot-toast';
import { LogOut, Plus, Trash2, Upload, Check, X, ChevronRight, FileDown, RotateCw, ExternalLink, ChevronUp } from 'lucide-react';
import Papa from 'papaparse';
import * as Progress from '@radix-ui/react-progress';

// --- Workflow statuses (keep in sync with backend)
const STATUS_OPTIONS = ["New", "Reviewed", "Shortlisted", "Interview", "Contacted", "Rejected"];

// --- Main Dashboard Component ---
function Dashboard() {
  const [jds, setJds] = useState([]);
  const [selectedJd, setSelectedJd] = useState(null);
  const [candidates, setCandidates] = useState([]);
  // track which JDs have had a full analysis run (so Run Full Analysis is only
  // enabled once per JD). Keyed by jdId -> boolean
  const [fullAnalyzedMap, setFullAnalyzedMap] = useState({});
  const [analysisCache, setAnalysisCache] = useState({});
  // Keep a ref of analysisCache so callbacks (that we don't want to re-create)
  // can access the latest cache without adding it to dependency lists.
  const analysisCacheRef = useRef(analysisCache);
  const [isLoading, setIsLoading] = useState(true);
  const [isJdModalOpen, setIsJdModalOpen] = useState(false);
  const [isResumeModalOpen, setIsResumeModalOpen] = useState(false);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [selectedCandidates, setSelectedCandidates] = useState(new Set());
  const [statusMap, setStatusMap] = useState({}); // { resumeId: "Status" }
  const [activeFilters, setActiveFilters] = useState({
    ratings: ['all'], // multi-select semantics; 'all' overrides others
    statuses: ['all'], // NEW: status filters
    hidePreliminary: false,
    minScore: 0,
    textQuery: '',
    sortKey: 'score',
    sortDir: 'desc'
  });
  
  const navigate = useNavigate();

  const fetchJds = useCallback(async (selectJd = null) => {
    try {
      const response = await api.listJds();
      setJds(response.data);
      if (selectJd) {
        setSelectedJd(selectJd);
      } else if (response.data.length > 0 && !selectedJd) {
        setSelectedJd(response.data[0]);
      }
    } catch (error) {
      console.error("Failed to fetch JDs", error);
    }
  }, [selectedJd]);

  // Whenever analysisCache or selectedJd changes, ensure candidate list reflects any
  // cached AI analyses for the selected JD (this prevents transient reversion to Preliminary)
  useEffect(() => {
    // keep ref in sync
    analysisCacheRef.current = analysisCache;

    if (!selectedJd) return;
    const jdCache = analysisCache[selectedJd.id] || {};
    if (!jdCache || Object.keys(jdCache).length === 0) return;
    setCandidates(prev => {
      if (!prev || prev.length === 0) return prev;
      return prev.map(item => {
        const rid = item.resume?.id;
        if (rid && jdCache[rid]) {
          const cached = jdCache[rid];
          return {
            ...item,
            score: cached.score ?? item.score,
            match_rating: cached.match_rating ?? item.match_rating,
            matched_skills: cached.matched_skills ?? item.matched_skills,
            missing_skills: cached.missing_skills ?? item.missing_skills,
            rationale: cached.rationale ?? item.rationale,
            analyzed_at: cached.analyzed_at ?? item.analyzed_at,
            similarity: cached.similarity ?? item.similarity,
            resume_excerpt: cached.resume_excerpt ?? item.resume_excerpt,
          };
        }
        return item;
      });
    });
  }, [selectedJd, analysisCache]);

  const fetchCandidatesForJd = useCallback(async () => {
    if (selectedJd) {
      setIsLoading(true);
      setCandidates([]);
      setSelectedCandidates(new Set());
      try {
        const response = await api.getCandidatesForJd(selectedJd.id);
        // ensure resume_excerpt flows through
        const list = response.data.map(c => ({...c, resume_excerpt: c.resume_excerpt}));
        // If we already have cached analyses for this JD (in memory), merge them so
        // cached AI results override any 'Preliminary' returned by the server.
        setCandidates(prev => {
          const copyList = list.map(item => ({ ...item }));
          // read latest cache from ref to avoid stale closure problems
          const jdCache = analysisCacheRef.current?.[selectedJd.id] || {};
          if (jdCache && Object.keys(jdCache).length > 0) {
            for (let i = 0; i < copyList.length; i++) {
              const rid = copyList[i].resume?.id;
              if (rid && jdCache[rid]) {
                // overlay the cached AI analysis fields
                const cached = jdCache[rid];
                copyList[i] = {
                  ...copyList[i],
                  score: cached.score ?? copyList[i].score,
                  match_rating: cached.match_rating ?? copyList[i].match_rating,
                  matched_skills: cached.matched_skills ?? copyList[i].matched_skills,
                  missing_skills: cached.missing_skills ?? copyList[i].missing_skills,
                  rationale: cached.rationale ?? copyList[i].rationale,
                  analyzed_at: cached.analyzed_at ?? copyList[i].analyzed_at,
                  similarity: cached.similarity ?? copyList[i].similarity,
                  resume_excerpt: cached.resume_excerpt ?? copyList[i].resume_excerpt
                };
              }
            }
          }
          return copyList;
        });
        // Build per-JD cache from returned analyses so we don't lose AI results when switching JDs
        setAnalysisCache(prev => {
          const copy = { ...prev };
          const jdCache = copy[selectedJd.id] ? { ...copy[selectedJd.id] } : {};
          // For any returned candidate that has been AI-analyzed (not Preliminary), store it
          list.forEach(item => {
            try {
              if (item.match_rating && item.match_rating !== 'Preliminary') {
                jdCache[item.resume.id] = {
                  resume: item.resume,
                  score: item.score,
                  match_rating: item.match_rating,
                  matched_skills: item.matched_skills || [],
                  missing_skills: item.missing_skills || [],
                  rationale: item.rationale || '',
                  analyzed_at: item.analyzed_at,
                  similarity: item.similarity,
                  resume_excerpt: item.resume_excerpt
                };
              }
            } catch (e) { /* defensive: ignore malformed items */ }
          });
          copy[selectedJd.id] = jdCache;
          return copy;
        });
  // Note: we intentionally DO NOT reset the per-JD "full analyzed" flag
  // based on incoming data here. The button should remain disabled after
  // a manual Full Analysis run for that JD. That flag is only set when
  // runFullAnalysis completes successfully.

        // Fetch statuses and map into {resumeId: status}
        const { data: statusResp } = await api.getCandidateStatuses(selectedJd.id);
  const map = {};
  (statusResp.statuses || []).forEach(s => { map[s.resume_id] = s.status; });

        // For any candidate without an explicit status, default to "New"
        list.forEach(c => { if(!map[c.resume.id]) map[c.resume.id] = "New"; });
        setStatusMap(map);
      } catch (error) {
        console.error(`Failed to fetch candidates for JD ${selectedJd.id}`, error);
      } finally {
        setIsLoading(false);
      }
    }
  }, [selectedJd]);

  const runFullAnalysis = async (force=false) => {
    if (!selectedJd) return;
    setIsLoading(true);
    try {
      const { data } = await api.fullAnalysis(selectedJd.id, force);
      const list = data.map(d => ({
        resume: d.resume,
        score: d.score,
        match_rating: d.match_rating,
        matched_skills: d.matched_skills,
        missing_skills: d.missing_skills,
        rationale: d.rationale,
        analyzed_at: d.analyzed_at,
        similarity: d.similarity,
        resume_excerpt: d.resume_excerpt
      }));
      setCandidates(list);
      // Store analyses scoped by JD
      setAnalysisCache(prev => {
        const copy = { ...prev };
        const jdCache = {};
        data.forEach(d => { jdCache[d.resume.id] = d; });
        copy[selectedJd.id] = jdCache;
        return copy;
      });
  // mark this JD as having completed a full analysis (disable the one-shot button)
  setFullAnalyzedMap(prev => ({ ...prev, [selectedJd.id]: true }));
      toast.success('Full AI analysis completed');

      // Ensure status map at least has "New" for all
      setStatusMap(prev => {
        const copy = { ...prev };
        list.forEach(c => { if(!copy[c.resume.id]) copy[c.resume.id] = "New"; });
        return copy;
      });
    } catch (e) {
      toast.error('Full analysis failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Analyze only candidates that are still heuristic (Preliminary)
  const analyzePreliminaryOnly = async () => {
    if (!selectedJd) return;
    setIsLoading(true);
    try {
      const { data } = await api.analyzePreliminary(selectedJd.id);
      if (data.length === 0) {
        toast('No preliminary candidates to analyze');
        return;
      }
      const map = new Map(candidates.map(c => [c.resume.id, c]));
      data.forEach(d => {
        map.set(d.resume.id, {
          resume: d.resume,
          score: d.score,
          match_rating: d.match_rating,
          matched_skills: d.matched_skills,
          missing_skills: d.missing_skills,
          rationale: d.rationale,
          analyzed_at: d.analyzed_at,
          similarity: d.similarity,
          resume_excerpt: d.resume_excerpt
        });
      });
      const merged = Array.from(map.values()).sort((a,b)=> b.score - a.score);
      setCandidates(merged);
      // merge into cache too
      setAnalysisCache(prev => {
        const copy = { ...prev };
        const jdCache = copy[selectedJd.id] ? { ...copy[selectedJd.id] } : {};
        data.forEach(d => { jdCache[d.resume.id] = d; });
        copy[selectedJd.id] = jdCache;
        return copy;
      });
      toast.success(`Analyzed ${data.length} preliminary candidate(s)`);

  // We intentionally do not change the one-shot per-JD full-analysis flag here.
  // That flag is controlled only by an explicit Run Full Analysis action.

      // Ensure statuses present for new candidates
      setStatusMap(prev => {
        const copy = { ...prev };
        merged.forEach(c => { if(!copy[c.resume.id]) copy[c.resume.id] = "New"; });
        return copy;
      });
    } catch(e){
      toast.error('Analyze preliminary failed');
    } finally {
      setIsLoading(false);
    }
  };


  useEffect(() => {
    fetchJds();
  }, [fetchJds]); // Added fetchJds as a dependency

  useEffect(() => {
    fetchCandidatesForJd();
  }, [selectedJd, fetchCandidatesForJd]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    toast.success("Logged out");
    navigate('/login');
  };
  
  const handleJdDelete = async (jdId, e) => {
    e.stopPropagation();
    toast((t) => (
      <div className="flex flex-col items-center gap-2">
        <p className="font-semibold">Are you sure?</p>
        <p className="text-sm text-slate-600">This job and all its data will be deleted.</p>
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => {
              toast.dismiss(t.id);
              api.deleteJd(jdId).then(() => {
                toast.success("Job description deleted.");
                fetchJds();
                setSelectedJd(null);
              });
            }}
            className="px-3 py-1 bg-red-600 text-white rounded-md text-sm"
          >
            Delete
          </button>
          <button
            onClick={() => toast.dismiss(t.id)}
            className="px-3 py-1 bg-slate-200 rounded-md text-sm"
          >
            Cancel
          </button>
        </div>
      </div>
    ));
  };

  const handleResumeUploadSuccess = (jobId) => {
    setUploadStatus({ jobId, progress: 0, total: 1, status: 'processing' });
    const interval = setInterval(async () => {
      try {
        const { data } = await api.getUploadStatus(jobId);
        setUploadStatus(data);
        if (data.status === 'completed') {
          clearInterval(interval);
          toast.success('Resumes processed!');
          setUploadStatus(null);
          if(selectedJd) {
            fetchCandidatesForJd();
          }
        }
      } catch (error) {
        clearInterval(interval);
        setUploadStatus(null);
      }
    }, 2000);
  };

  // --- Status helpers ---
  const setStatusForSelection = async (status) => {
    if (!selectedJd || selectedCandidates.size === 0) return;
    const ids = Array.from(selectedCandidates);
    try {
      await api.bulkUpdateCandidateStatus(selectedJd.id, ids, status);
      toast.success(`Moved ${ids.length} to ${status}`);
      setStatusMap(prev => {
        const copy = { ...prev };
        ids.forEach(id => copy[id] = status);
        return copy;
      });
      setSelectedCandidates(new Set()); // clear selection
    } catch(e) {
      // error toasted by interceptor
    }
  };

  const setStatusForOne = async (resumeId, status) => {
    if (!selectedJd) return;
    try {
      await api.bulkUpdateCandidateStatus(selectedJd.id, [resumeId], status);
      setStatusMap(prev => ({ ...prev, [resumeId]: status }));
      toast.success(`Updated to ${status}`);
    } catch(e) { /* toast handled */ }
  };

  // --- Filtering with status + rating ---
  const filteredCandidates = useMemo(() => {
    const textQuery = activeFilters.textQuery.trim().toLowerCase();
    return candidates
      .filter(c => {
        // rating multi-select filter
        const selectedRatings = activeFilters.ratings;
        if (!(selectedRatings.includes('all'))) {
          if (!selectedRatings.map(r => r.toLowerCase()).includes(c.match_rating.toLowerCase())) return false;
        }
        // status multi-select filter
        const selectedStatuses = activeFilters.statuses;
        const status = statusMap[c.resume.id] || "New";
        if (!(selectedStatuses.includes('all'))) {
          if (!selectedStatuses.map(s => s.toLowerCase()).includes(status.toLowerCase())) return false;
        }
        // hide preliminary toggle
        if (activeFilters.hidePreliminary && c.match_rating === 'Preliminary') return false;
        // min score
        if (c.score < activeFilters.minScore) return false;
        // text search across candidate name, resume excerpt, and JD text
        if (textQuery) {
          const haystack = [c.resume.candidate_name, c.resume_excerpt || '', selectedJd?.text || '']
            .join(' ').toLowerCase();
          if (!haystack.includes(textQuery)) return false;
        }
        return true;
      })
      .sort((a,b) => {
        const dir = activeFilters.sortDir === 'asc' ? 1 : -1;
        switch(activeFilters.sortKey){
          case 'name':
            return a.resume.candidate_name.localeCompare(b.resume.candidate_name) * dir;
          case 'rating':
            return a.match_rating.localeCompare(b.match_rating) * dir;
          case 'status':
            return ( (statusMap[a.resume.id]||"New").localeCompare(statusMap[b.resume.id]||"New") ) * dir;
          case 'score':
          default:
            return (a.score - b.score) * dir;
        }
      });
  }, [candidates, activeFilters, selectedJd, statusMap]);
  
  return (
    <div className="min-h-screen bg-slate-50">
      <Header onLogout={handleLogout} />
      <main>
        <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-4 space-y-4">
              <JdList 
                jds={jds} 
                selectedJd={selectedJd} 
                setSelectedJd={setSelectedJd} 
                onNewJd={() => setIsJdModalOpen(true)}
                onDeleteJd={handleJdDelete}
              />
            </div>

            <div className="lg:col-span-8">
                <CandidateAreaHeader
                  selectedJd={selectedJd}
                  isLoading={isLoading}
                  candidateCount={filteredCandidates.length}
                  onAddResumes={() => setIsResumeModalOpen(true)}
                />

                {uploadStatus && uploadStatus.status === 'processing' && <UploadProgress status={uploadStatus} />}
                
                {selectedJd && (
                  <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                    <FilterBar 
                      activeFilters={activeFilters} 
                      setActiveFilters={setActiveFilters} 
                      onRefresh={fetchCandidatesForJd} 
                      jd={selectedJd} 
                    />
            <CandidateTable 
                      candidates={filteredCandidates} 
                      isLoading={isLoading}
                      jd={selectedJd}
                      selectedCandidates={selectedCandidates}
                      setSelectedCandidates={setSelectedCandidates}
                      fullAnalyzed={fullAnalyzedMap[selectedJd.id] || false}
                      runFullAnalysis={runFullAnalysis}
                      analysisCache={analysisCache}
                      setAnalysisCache={setAnalysisCache}
                      analyzePreliminaryOnly={analyzePreliminaryOnly}
                      statusMap={statusMap}
                      onSetStatusOne={setStatusForOne}
                      onSetStatusBulk={setStatusForSelection}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </main>
        <JDModal isOpen={isJdModalOpen} onClose={()=>setIsJdModalOpen(false)} onUploadSuccess={(jd)=>fetchJds(jd)} />
        <ResumeModal isOpen={isResumeModalOpen} onClose={()=>setIsResumeModalOpen(false)} onUploadSuccess={handleResumeUploadSuccess} />
      </div>
    );

}

const JdList = ({ jds, selectedJd, setSelectedJd, onNewJd, onDeleteJd }) => (
  <>
    <div className="flex items-center justify-between">
      <h2 className="text-lg font-semibold text-slate-700">Job Descriptions</h2>
      <button onClick={onNewJd} className="flex items-center space-x-2 px-3 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2">
        <Plus size={16} /><span>New JD</span>
      </button>
    </div>
    <div className="bg-white p-3 rounded-lg shadow-sm space-y-2">
      {jds.length === 0 && <p className="text-sm text-center text-slate-500 py-4">No jobs added yet.</p>}
      {jds.map(jd => (
        <div key={jd.id} onClick={() => setSelectedJd(jd)} className={`p-3 rounded-md cursor-pointer border-2 transition-colors ${selectedJd?.id === jd.id ? 'bg-indigo-50 border-indigo-500' : 'hover:bg-slate-50 border-transparent'}`}>
          <div className="flex justify-between items-start">
            <p className={`font-semibold ${selectedJd?.id === jd.id ? 'text-indigo-800' : 'text-slate-800'}`}>{jd.title}</p>
            <button onClick={(e) => onDeleteJd(jd.id, e)} className="text-slate-400 hover:text-red-500 p-1" aria-label="Delete job"><Trash2 size={16} /></button>
          </div>
        </div>
      ))}
    </div>
  </>
);

const Header = ({ onLogout }) => (
  <header className="bg-white border-b shadow-sm">
    <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
      <h1 className="text-lg font-semibold text-slate-800">AI Resume Matcher</h1>
      <button onClick={onLogout} className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-200 hover:bg-slate-300 text-sm text-slate-700">
        <LogOut size={16} /> <span>Logout</span>
      </button>
    </div>
  </header>
);

const CandidateAreaHeader = ({ selectedJd, isLoading, candidateCount, onAddResumes }) => {
  const handleClearResumes = async () => {
    if (window.confirm('Are you sure you want to delete all resumes? This action cannot be undone.')) {
      try {
        await api.deleteAllResumes();
        toast.success('All resumes deleted successfully.');
        window.location.reload(); // Refresh the page
      } catch (error) {
        toast.error('Failed to delete resumes.');
      }
    }
  };

  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-700">{selectedJd ? `Candidates for ${selectedJd.title}` : 'Select a Job'}</h2>
        {selectedJd && <p className="text-sm text-slate-500">{isLoading ? 'Loading...' : `${candidateCount} candidate(s) found`}</p>}
      </div>
      {selectedJd && (
        <div className="flex space-x-3">
          <button 
            onClick={handleClearResumes}
            className="flex items-center space-x-2 px-3 py-2 text-sm font-semibold text-red-600 bg-red-50 border border-red-200 rounded-lg shadow-sm hover:bg-red-100"
          >
            <Trash2 size={16} /><span>Delete All</span>
          </button>
          <button 
            onClick={onAddResumes} 
            disabled={!selectedJd} 
            className="flex items-center space-x-2 px-3 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg shadow-sm hover:bg-indigo-700 disabled:bg-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            <Upload size={16} /><span>Add Resumes</span>
          </button>
        </div>
      )}
    </div>
  );
};

const UploadProgress = ({ status }) => (
  <div className="bg-white p-4 rounded-lg shadow-sm mb-4">
    <p className="text-sm font-medium mb-2">Processing resumes... ({status.progress}/{status.total})</p>
    <Progress.Root value={(status.progress / status.total) * 100} className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
      <Progress.Indicator style={{ width: `${(status.progress / status.total) * 100}%` }} className="h-full bg-indigo-600 transition-all duration-300" />
    </Progress.Root>
  </div>
);

const FilterBar = ({ activeFilters, setActiveFilters, onRefresh, jd }) => {
  const handleInput = (field) => (e) => setActiveFilters(prev => ({ ...prev, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const toggleMulti = (key, val) => {
    setActiveFilters(prev => {
      // 'all' special handling
      if (val === 'all') return { ...prev, [key]: ['all'] };
      const existing = prev[key].filter(r => r !== 'all');
      const has = existing.includes(val);
      const next = has ? existing.filter(r => r !== val) : [...existing, val];
      return { ...prev, [key]: next.length ? next : ['all'] };
    });
  };

  return (
    <div className="p-3 bg-slate-50 border-b flex flex-col gap-2">
      {/* Row 1 */}
      <div className="flex items-center gap-4 flex-nowrap overflow-x-auto pr-2">
        {/* Ratings */}
        <div className="flex items-center gap-2 flex-nowrap">
          <span className="text-xs font-semibold text-slate-600 whitespace-nowrap">Ratings</span>
          <div className="flex items-center gap-1 flex-nowrap">
            {['all','Strong','Good','Weak','Preliminary'].map(r => {
              const val = r.toLowerCase();
              const active = activeFilters.ratings.includes('all') ? (r==='all') : activeFilters.ratings.map(x=>x.toLowerCase()).includes(val);
              return (
                <button key={r} onClick={()=>toggleMulti('ratings', val)} className={`px-2 py-1 rounded text-[11px] border ${active ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 hover:bg-slate-100 border-slate-300'}`}>{r}</button>
              );
            })}
          </div>
        </div>

        {/* Group: Min Score + Hide Preliminary (kept together for compact scanning) */}
        <div className="flex items-center gap-4 ml-4">
          <div className="flex items-center gap-1 text-xs">
            <span className="text-slate-600">Min Score</span>
            <input type="number" min={0} max={100} value={activeFilters.minScore} onChange={handleInput('minScore')} className="w-16 border rounded px-1 py-0.5 text-xs" />
          </div>
          <div className="flex items-center gap-3 text-xs">
            <label className="flex items-center gap-1 text-slate-600"><input type="checkbox" checked={activeFilters.hidePreliminary} onChange={handleInput('hidePreliminary')} /> Hide Preliminary</label>
          </div>
        </div>
      </div>
      {/* Row 2 */}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Statuses (moved here for better scanning) */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-600 whitespace-nowrap">Status</span>
          <div className="flex items-center gap-1 flex-wrap">
            {['all', ...STATUS_OPTIONS].map(s => {
              const val = s.toLowerCase();
              const active = activeFilters.statuses.includes('all') ? (s==='all') : activeFilters.statuses.map(x=>x.toLowerCase()).includes(val);
              return (
                <button key={s} onClick={()=>toggleMulti('statuses', val)} className={`px-2 py-1 rounded text-[11px] border ${active ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 hover:bg-slate-100 border-slate-300'}`}>{s}</button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-600">Sort</span>
          <select value={`${activeFilters.sortKey}:${activeFilters.sortDir}`} onChange={(e)=>{
              const [k,d]= e.target.value.split(':');
              setActiveFilters(prev => ({...prev, sortKey: k, sortDir: d}));
            }} className="text-xs border rounded px-1 py-0.5 bg-white">
            <option value="score:desc">Score ↓</option>
            <option value="score:asc">Score ↑</option>
            <option value="name:asc">Name A-Z</option>
            <option value="name:desc">Name Z-A</option>
          </select>
        </div>

        <input type="text" value={activeFilters.textQuery} onChange={handleInput('textQuery')} placeholder="Search name / resume / JD" className="flex-1 min-w-[240px] border rounded px-3 py-1 text-xs bg-white" />

        <div className="flex items-center gap-2">
          <button onClick={onRefresh} className="p-1.5 text-slate-500 hover:text-indigo-600 hover:bg-slate-200 rounded" title="Refresh from server"><RotateCw size={14} /></button>
          <button onClick={()=> setActiveFilters({ratings:['all'], statuses:['all'], hidePreliminary:false, minScore:0, textQuery:'', sortKey:'score', sortDir:'desc'})} className="p-1.5 text-slate-500 hover:text-indigo-600 hover:bg-slate-200 rounded text-xs" title="Reset filters">Reset</button>
        </div>

        {jd && <p className="text-[10px] text-slate-500 ml-auto">JD: {jd.title} • {jd.required_skills?.length || 0} req / {jd.nice_to_have_skills?.length || 0} nice</p>}
      </div>
    </div>
  );
};


const CandidateTable = ({ candidates, isLoading, jd, selectedCandidates, setSelectedCandidates, fullAnalyzed, runFullAnalysis, analysisCache, setAnalysisCache, analyzePreliminaryOnly, statusMap, onSetStatusOne, onSetStatusBulk }) => {
  const [expandedRow, setExpandedRow] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(null); // resume ID
  const hasPreliminary = candidates.some(c => c.match_rating === 'Preliminary');
  const hasAnalyzed = candidates.some(c => c.match_rating !== 'Preliminary');

  const handleAnalyze = async (resumeId, force=false) => {
    const jdCache = analysisCache[jd?.id] || {};
    if (!force && jdCache[resumeId]) return; // already have and not forcing
    setIsAnalyzing(resumeId);
    try {
      const response = await api.analyzeCandidate(jd.id, resumeId, force);
      setAnalysisCache(prev => {
        const copy = { ...prev };
        const jdCacheLocal = copy[jd.id] ? { ...copy[jd.id] } : {};
        jdCacheLocal[resumeId] = { ...response.data, resume_excerpt: response.data.resume_excerpt };
        copy[jd.id] = jdCacheLocal;
        return copy;
      });
      if(force) toast.success('Re-analyzed candidate');
    } catch (error) {
      toast.error('AI analysis failed.');
      console.error(error);
    } finally {
      setIsAnalyzing(null);
    }
  };

  const toggleRow = (resumeId) => {
    const newExpandedRow = expandedRow === resumeId ? null : resumeId;
    setExpandedRow(newExpandedRow);
    if (newExpandedRow && !(analysisCache[jd.id] && analysisCache[jd.id][newExpandedRow])) {
      handleAnalyze(newExpandedRow);
    }
  };

  const handleSelect = (id) => {
    const newSelection = new Set(selectedCandidates);
    newSelection.has(id) ? newSelection.delete(id) : newSelection.add(id);
    setSelectedCandidates(newSelection);
  };

  const handleSelectAll = (e) => {
    e.target.checked ? setSelectedCandidates(new Set(candidates.map(c => c.resume.id))) : setSelectedCandidates(new Set());
  };

  if (isLoading) return <SkeletonLoader />;
  if (candidates.length === 0) return <div className="p-6 text-center text-slate-500">No candidates match the current filters.</div>;

  const exportToCsv = () => {
    const dataToExport = candidates
      .filter(c => selectedCandidates.has(c.resume.id))
      .map(c => ({
        Name: c.resume.candidate_name,
        Email: c.resume.parsed_json?.email || 'N/A',
        MatchRating: c.match_rating,
        MatchScore: c.score,
        Status: statusMap[c.resume.id] || 'New',
        MatchedSkills: c.matched_skills.join(', '),
        MissingSkills: c.missing_skills.join(', '),
      }));
    const csv = Papa.unparse(dataToExport);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `shortlist_${jd.title.replace(/\s+/g, '_')}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const isAllSelected = selectedCandidates.size === candidates.length && candidates.length > 0;

  return (
    <>
      <div className="flex items-center gap-3 p-3 bg-white border-b flex-wrap">
        <button onClick={() => runFullAnalysis(false)} disabled={isLoading || fullAnalyzed || candidates.length===0} className="px-3 py-1.5 rounded bg-indigo-600 text-white text-sm disabled:bg-indigo-300 disabled:cursor-not-allowed" title={candidates.length===0 ? 'Upload resumes first' : ''}>{fullAnalyzed ? 'Analysis Ready' : 'Run Full Analysis'}</button>
        {hasAnalyzed && <>
          <button onClick={() => runFullAnalysis(true)} disabled={isLoading} className="px-3 py-1.5 rounded bg-slate-200 text-sm disabled:opacity-50" title="Re-run AI for all">Re-run (Force)</button>
          {hasPreliminary && <button onClick={analyzePreliminaryOnly} disabled={isLoading} className="px-3 py-1.5 rounded bg-emerald-600 text-white text-sm disabled:opacity-50" title="Analyze only candidates still Preliminary">Analyze Preliminary</button>}
        </>}

        {selectedCandidates.size > 0 && (
          <div className="bg-indigo-50 p-2 flex items-center gap-2 border-b rounded">
            <span className="text-sm font-semibold pl-2 text-indigo-800">{selectedCandidates.size} selected</span>
            <BulkStatusMenu onSet={onSetStatusBulk} />
            <button onClick={exportToCsv} className="flex items-center space-x-1 text-sm text-slate-700 hover:text-indigo-600"><FileDown size={14}/><span>Export CSV</span></button>
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-50 border-b">
            <tr>
              <th className="p-3 w-8"><input aria-label="Select all candidates" type="checkbox" onChange={handleSelectAll} checked={isAllSelected} /></th>
              <th className="p-3 font-medium text-slate-600">Candidate</th>
              <th className="p-3 font-medium text-slate-600 cursor-pointer" title="Sort by score">Score</th>
              <th className="p-3 font-medium text-slate-600">Match Rating</th>
              <th className="p-3 font-medium text-slate-600">Status</th>
              <th className="p-3 font-medium text-slate-600">Top Skills</th>
              <th className="p-3 w-12"></th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate) => {
              const rid = candidate.resume.id;
              const status = statusMap[rid] || "New";
              return (
                <React.Fragment key={rid}>
                  <tr className="border-b hover:bg-slate-50">
                    <td className="p-3"><input aria-label={`Select ${candidate.resume.candidate_name}`} type="checkbox" checked={selectedCandidates.has(rid)} onChange={() => handleSelect(rid)} /></td>
                    <td className="p-3 font-medium text-slate-800">{candidate.resume.candidate_name}</td>
                    <td className="p-3 text-slate-700 font-mono tabular-nums">
                      {`${candidate.score.toFixed(1)}%`}
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        {candidate.match_rating === 'Preliminary' ? (
                          <span className="font-semibold px-2 py-1 rounded-full text-xs bg-sky-100 text-sky-800 border border-sky-300" title="Heuristic estimate – run AI for verified score">Preliminary</span>
                        ) : (
                          <span className={`font-semibold px-2 py-1 rounded-full text-xs text-white ${
                            candidate.match_rating === 'Strong' ? 'bg-green-600' : 
                            candidate.match_rating === 'Good' ? 'bg-blue-600' : 
                            'bg-amber-600'
                          }`}>
                            {candidate.match_rating}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="p-3">
                      <StatusDropdown value={status} onChange={(s)=>onSetStatusOne(rid, s)} />
                    </td>
                    <td className="p-3">
                      <div className="flex flex-wrap gap-1">
                        {candidate.matched_skills.slice(0, 3).map(s => 
                          <span key={s} className="px-2 py-0.5 text-xs bg-green-100 text-green-800 rounded-full">{s}</span>
                        )}
                        {candidate.matched_skills.length === 0 && 
                          <span className="text-xs text-slate-500">No matched skills</span>
                        }
                      </div>
                    </td>
                    <td className="p-3">
                      <button onClick={() => toggleRow(rid)} className="p-1 rounded-full hover:bg-slate-200" aria-label={expandedRow === rid ? 'Collapse row' : 'Expand row'}>
                        {expandedRow === rid ? <ChevronUp size={18} /> : <ChevronRight size={18} />}
                      </button>
                    </td>
                  </tr>
                  {expandedRow === rid && (
                    <tr className="bg-white border-b">
                      <td colSpan="7" className="p-4 bg-slate-50/50">
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                          <AnalysisDetail 
                            analysis={analysisCache[jd.id] ? analysisCache[jd.id][rid] : null} 
                            isLoading={isAnalyzing === rid}
                            onForce={() => handleAnalyze(rid, true)}
                          />
                          <ResumePreview resumeId={rid} candidateName={candidate.resume.candidate_name} />
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
};

const StatusDropdown = ({ value, onChange }) => {
  return (
    <select
      value={value}
      onChange={(e)=>onChange(e.target.value)}
      className="text-xs border rounded px-2 py-1 bg-white"
      aria-label="Change candidate status"
    >
      {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
    </select>
  );
};

const BulkStatusMenu = ({ onSet }) => {
  return (
    <div className="flex items-center gap-1">
      {STATUS_OPTIONS.map(s => (
        <button key={s} onClick={()=>onSet(s)} className="text-xs px-2 py-1 bg-slate-200 hover:bg-slate-300 rounded">{s}</button>
      ))}
    </div>
  );
};

const AnalysisDetail = ({ analysis, isLoading, onForce }) => {
  if (isLoading) return <div className="text-center text-slate-500 py-4">Running AI analysis...</div>;
  if (!analysis) return <div className="text-center text-red-500 py-4">Analysis could not be loaded.</div>;

  const { rationale, matched_skills, missing_skills, score, analyzed_at, similarity } = analysis;
  return (
    <div className="border rounded-lg bg-white p-4">
      <div className="flex items-center space-x-2 mb-3">
        <h4 className="font-semibold text-slate-700">AI Match Analysis</h4>
        <span className="text-xs bg-indigo-100 text-indigo-800 px-2 py-1 rounded-full">{score.toFixed(1)}% Match</span>
        {similarity !== undefined && <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded-full" title="Embedding similarity to JD">sim {similarity}</span>}
        <button onClick={onForce} className="text-xs px-2 py-1 bg-slate-200 hover:bg-slate-300 rounded" title="Force re-run analysis for this candidate">Re-run</button>
      </div>
      <p className="italic text-slate-600 leading-relaxed">"{rationale}"</p>
      {analyzed_at && <p className="mt-2 text-xs text-slate-500">Analyzed at: {analyzed_at}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <div>
          <h4 className="font-semibold text-slate-700 mb-2">✓ Required Skills Matched</h4>
          <div className="flex flex-wrap gap-2">
            {matched_skills.length > 0 ? 
              matched_skills.map(s => (
                <span key={s} className="flex items-center space-x-1 px-2 py-1 text-xs bg-green-100 text-green-800 rounded-full">
                  <Check size={12}/>
                  <span>{s}</span>
                </span>
              )) : 
              <p className="text-xs text-slate-500">No required skills matched</p>
            }
          </div>
        </div>
        <div>
          <h4 className="font-semibold text-slate-700 mb-2">⨯ Required Skills Missing</h4>
          <div className="flex flex-wrap gap-2">
            {missing_skills.length > 0 ? 
              missing_skills.map(s => (
                <span key={s} className="flex items-center space-x-1 px-2 py-1 text-xs bg-red-100 text-red-800 rounded-full">
                  <X size={12}/>
                  <span>{s}</span>
                </span>
              )) : 
              <p className="text-xs text-slate-500">No required skills missing</p>
            }
          </div>
        </div>
      </div>
    </div>
  );
};

const ResumePreview = ({ resumeId, candidateName }) => {
  const [objectUrl, setObjectUrl] = useState(null);
  const [isImage, setIsImage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    let urlToRevoke = null;
    const load = async () => {
      setLoading(true);
      setErrorText("");
      try {
        const blob = await api.getResumePreviewBlob(resumeId);
        if (blob && blob.type && blob.type.startsWith('image/')) {
          setIsImage(true);
        } else {
          setIsImage(false);
        }
        const url = URL.createObjectURL(blob);
        urlToRevoke = url;
        setObjectUrl(url);
      } catch (e) {
        setErrorText("Preview unavailable.");
      } finally {
        setLoading(false);
      }
    };
    load();
    return () => {
      if (urlToRevoke) URL.revokeObjectURL(urlToRevoke);
    };
  }, [resumeId]);

  const openFull = async () => {
    try {
      const blob = await api.getResumeFileBlob(resumeId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
      toast.error("Failed to open resume.");
    }
  };

  const downloadFile = async () => {
    try {
      const blob = await api.getResumeFileBlob(resumeId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${candidateName.replace(/\s+/g, '_')}_resume`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
      toast.error("Failed to download resume.");
    }
  };

  return (
    <div className="border rounded-lg bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-semibold text-slate-700">Resume Preview</h4>
        <div className="flex items-center gap-2">
          <button onClick={openFull} className="text-xs px-2 py-1 bg-slate-200 hover:bg-slate-300 rounded inline-flex items-center gap-1" title="Open full resume">
            <ExternalLink size={14} /> Open
          </button>
          <button onClick={downloadFile} className="text-xs px-2 py-1 bg-slate-200 hover:bg-slate-300 rounded inline-flex items-center gap-1" title="Download file">
            <FileDown size={14} /> Download
          </button>
        </div>
      </div>
      <div className="h-[360px] border rounded bg-slate-50 overflow-auto flex items-center justify-center">
        {loading && <span className="text-slate-500 text-sm">Loading preview…</span>}
        {!loading && errorText && <span className="text-slate-500 text-sm">{errorText}</span>}
        {!loading && !errorText && objectUrl && (
          isImage ? (
            <img src={objectUrl} alt={`${candidateName} resume preview`} className="max-h-full object-contain" />
          ) : (
            <pre className="whitespace-pre-wrap text-xs p-3 text-slate-700">
              <TextFromObjectUrl objectUrl={objectUrl} />
            </pre>
          )
        )}
      </div>
    </div>
  );
};

const TextFromObjectUrl = ({ objectUrl }) => {
  const [text, setText] = useState("Loading…");
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(objectUrl);
        const t = await res.text();
        if (!cancelled) setText(t || "No preview text available.");
      } catch {
        if (!cancelled) setText("Unable to load preview text.");
      }
    })();
    return () => { cancelled = true; };
  }, [objectUrl]);
  return <>{text}</>;
};

const SkeletonLoader = () => (
  <div className="p-4 space-y-4">
    {[...Array(5)].map((_, i) => (
      <div key={i} className="flex items-center space-x-4 animate-pulse">
        <div className="h-5 w-5 bg-slate-200 rounded"></div>
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-slate-200 rounded w-1/4"></div>
        </div>
        <div className="h-6 w-20 bg-slate-200 rounded-full"></div>
        <div className="h-4 w-1/3 bg-slate-200 rounded"></div>
      </div>
    ))}
  </div>
);

// --- Modal Components ---

const JDModal = ({ isOpen, onClose, onUploadSuccess }) => {
  const [title, setTitle] = useState('');
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsUploading(true);
    try {
      const response = await api.uploadJd(title, file);
      toast.success("JD uploaded successfully!");
      onUploadSuccess(response.data);
      onClose();
      setTitle(''); setFile(null);
    } catch(e) {
      // Error handled by global interceptor
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add New Job Description">
      <form onSubmit={handleSubmit} className="space-y-4 p-4">
        <input type="text" placeholder="Job Title" value={title} onChange={(e) => setTitle(e.target.value)} className="w-full p-2 border rounded" required />
        <input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files[0])} className="w-full text-sm" required />
        <div className="flex justify-end gap-2 pt-4">
          <button type="button" onClick={onClose} className="px-4 py-2 bg-slate-200 rounded hover:bg-slate-300">Cancel</button>
          <button type="submit" disabled={isUploading} className="px-4 py-2 bg-indigo-600 text-white rounded disabled:bg-indigo-400">{isUploading ? 'Uploading...' : 'Upload'}</button>
        </div>
      </form>
    </Modal>
  );
};

const ResumeModal = ({ isOpen, onClose, onUploadSuccess }) => {
  const [files, setFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (files.length === 0) {
      toast.error("Please select at least one resume file.");
      return;
    }
    setIsUploading(true);
    try {
      const response = await api.bulkUploadResumes(Array.from(files));
      // Backend may return duplicates array and possibly no job_id if nothing new
      const { job_id, duplicates } = response.data;
      if (duplicates && duplicates.length > 0 && !job_id) {
        // Only duplicates were detected; notify user and do NOT trigger job polling.
        toast((t) => (
          <div className="flex flex-col">
            <div className="font-semibold">Duplicate resumes detected</div>
            <div className="text-sm">{duplicates.join(', ')}</div>
          </div>
        ));
        // Close modal and clear selected files, but don't call onUploadSuccess(null)
        onClose();
        setFiles([]);
        return;
      }

      if (job_id) {
        toast.success("Resume upload started!");
        onUploadSuccess(job_id);
        onClose();
        setFiles([]);
      } else {
        // No job_id and no duplicates -> something went wrong reading files
        toast.error('No new resumes were uploaded (duplicates or read errors).');
        onClose();
        setFiles([]);
      }
    } catch(e) {
      // Error handled by global interceptor
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Bulk Add Resumes">
      <form onSubmit={handleSubmit} className="space-y-4 p-4">
        <input type="file" multiple accept=".pdf,.docx,.txt" onChange={(e) => setFiles(e.target.files)} className="w-full text-sm" required />
        <p className="text-xs text-slate-500">You can select multiple files to upload at once.</p>
        <div className="flex justify-end gap-2 pt-4">
          <button type="button" onClick={onClose} className="px-4 py-2 bg-slate-200 rounded hover:bg-slate-300">Cancel</button>
          <button type="submit" disabled={isUploading || files.length === 0} className="px-4 py-2 bg-indigo-600 text-white rounded disabled:bg-indigo-400">{isUploading ? 'Uploading...' : `Upload ${files.length} Resumes`}</button>
        </div>
      </form>
    </Modal>
  );
}

export default Dashboard;

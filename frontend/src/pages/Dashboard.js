import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';
import Modal from '../components/Modal';

// --- SVG Icons ---
const icons = {
  briefcase: <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>,
  users: <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>,
  plus: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>,
  trash: <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>,
  upload: <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>,
  logOut: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>,
};

function Header({ onLogout }) {
  return (
    <header className="bg-white/80 backdrop-blur-sm shadow-sm sticky top-0 z-30">
      <div className="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8 flex justify-between items-center">
        <div className="flex items-center space-x-2">
          {icons.briefcase}
          <h1 className="text-xl font-bold text-slate-800">AI Recruiter</h1>
        </div>
        <button onClick={onLogout} className="flex items-center space-x-2 px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 rounded-md hover:bg-red-50 hover:text-red-600 transition-colors">
          {icons.logOut}<span>Logout</span>
        </button>
      </div>
    </header>
  );
}

function Dashboard() {
  const [jds, setJds] = useState([]);
  const [selectedJd, setSelectedJd] = useState(null);
  const [candidatesByJd, setCandidatesByJd] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false); // For smart refresh
  const [error, setError] = useState('');
  const [isJdModalOpen, setIsJdModalOpen] = useState(false);
  const [isResumeModalOpen, setIsResumeModalOpen] = useState(false);
  
  const navigate = useNavigate();

  const fetchJds = useCallback(async (selectFirst = false) => {
    try {
      setIsLoading(true);
      const response = await api.listJds();
      setJds(response.data);
      if (selectFirst && response.data.length > 0 && !selectedJd) {
        setSelectedJd(response.data[0]);
      }
    } catch (err) { setError('Failed to load job descriptions.'); }
    finally { setIsLoading(false); }
  }, [selectedJd]);

  useEffect(() => {
    fetchJds(true);
  }, [fetchJds]);

  useEffect(() => {
    const fetchCandidates = async () => {
      if (selectedJd && !candidatesByJd[selectedJd.id]) {
        setIsLoading(true);
        setError('');
        try {
          const response = await api.getCandidatesForJd(selectedJd.id);
          setCandidatesByJd(prev => ({ ...prev, [selectedJd.id]: response.data }));
        } catch (err) { setError(`Failed to load candidates for ${selectedJd.title}.`); }
        finally { setIsLoading(false); }
      }
    };
    fetchCandidates();
  }, [selectedJd, candidatesByJd]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };
  
  const handleJdDelete = async (jdId, e) => {
    e.stopPropagation();
    if (window.confirm("Are you sure?")) {
      await api.deleteJd(jdId);
      const newJds = jds.filter(jd => jd.id !== jdId);
      setJds(newJds);
      if (selectedJd?.id === jdId) setSelectedJd(newJds[0] || null);
    }
  };

  const handleClearResumes = async () => {
    if (window.confirm("Are you sure? This will delete ALL resumes and analyses.")) {
      await api.deleteAllResumes();
      setCandidatesByJd({});
    }
  };

  const handleResumeUploadSuccess = async () => {
    // This is the smart refresh logic
    if (selectedJd) {
      setIsRefreshing(true);
      try {
        const response = await api.getCandidatesForJd(selectedJd.id);
        setCandidatesByJd(prev => ({ ...prev, [selectedJd.id]: response.data }));
      } catch (err) { setError('Failed to refresh candidates.'); }
      finally { setIsRefreshing(false); }
    }
  };

  const currentCandidates = selectedJd ? candidatesByJd[selectedJd.id] || [] : [];
  const hasAnyResumes = Object.values(candidatesByJd).some(c => c.length > 0);

  return (
    <div className="min-h-screen bg-slate-50">
      <Header onLogout={handleLogout} />
      <main>
        <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-md">
              {error}
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-4 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-700">Job Descriptions</h2>
                <button onClick={() => setIsJdModalOpen(true)} className="flex items-center space-x-2 px-3 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg shadow-sm hover:bg-indigo-700">
                  {icons.plus}<span>New JD</span>
                </button>
              </div>
              <div className="bg-white p-3 rounded-lg shadow-sm space-y-2">
                {jds.map(jd => (
                  <div key={jd.id} onClick={() => setSelectedJd(jd)} className={`p-3 rounded-md cursor-pointer border-2 ${selectedJd?.id === jd.id ? 'bg-indigo-50 border-indigo-500' : 'hover:bg-slate-50 border-transparent'}`}>
                    <div className="flex justify-between items-start">
                      <p className={`font-semibold ${selectedJd?.id === jd.id ? 'text-indigo-800' : 'text-slate-800'}`}>{jd.title}</p>
                      <button onClick={(e) => handleJdDelete(jd.id, e)} className="text-slate-400 hover:text-red-500 p-1">{icons.trash}</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="lg:col-span-8">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold text-slate-700">{selectedJd ? `Candidates for ${selectedJd.title}` : 'Select a Job'}</h2>
                  {selectedJd && <p className="text-sm text-slate-500">{ (isLoading || isRefreshing) ? 'Analyzing...' : `${currentCandidates.length} candidate(s) found`}</p>}
                </div>
                <button onClick={() => setIsResumeModalOpen(true)} className="flex items-center space-x-2 px-3 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg shadow-sm hover:bg-indigo-700">
                  {icons.upload}<span>Add Resumes</span>
                </button>
              </div>
              <div className="bg-white p-3 rounded-lg shadow-sm space-y-3 min-h-[300px]">
                { (isLoading || isRefreshing) && <div className="text-center py-10 text-slate-500">{isRefreshing ? 'Analyzing new resumes...' : 'Analyzing candidates...'}</div>}
                {!(isLoading || isRefreshing) && currentCandidates.length === 0 && <div className="text-center py-10 text-slate-500">No candidates found for this role.</div>}
                {currentCandidates.map(candidate => (
                  <CandidateCard key={candidate.resume.id} candidate={candidate} jd={selectedJd} />
                ))}
              </div>
              {hasAnyResumes && <div className="mt-4 flex justify-end"><button onClick={handleClearResumes} className="text-sm text-slate-500 hover:text-red-600">Clear All Resumes</button></div>}
            </div>
          </div>
        </div>
      </main>
      <JDModal isOpen={isJdModalOpen} onClose={() => setIsJdModalOpen(false)} onUploadSuccess={() => fetchJds(true)} />
      <ResumeModal isOpen={isResumeModalOpen} onClose={() => setIsResumeModalOpen(false)} onUploadSuccess={handleResumeUploadSuccess} />
    </div>
  );
}

const CandidateCard = ({ candidate, jd }) => {
    const navigate = useNavigate();
    const { resume, match_percentage, matched_skills } = candidate;
    
    const handleNavigate = () => {
      navigate(`/candidate/${resume.id}/${jd.id}`, { state: { candidate, jd } });
    };

    return (
        <div onClick={handleNavigate} className="bg-slate-50 p-4 rounded-lg border hover:border-indigo-500 cursor-pointer">
            <div className="flex justify-between items-center">
                <div>
                    <h3 className="font-bold text-slate-800">{resume.candidate_name}</h3>
                    <p className="text-sm text-slate-500">{resume.parsed_json?.email || 'N/A'}</p>
                </div>
                <p className="text-2xl font-bold text-indigo-600">{match_percentage}%</p>
            </div>
            <div className="mt-3 pt-3 border-t">
                <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Top Matched Skills</h4>
                <div className="flex flex-wrap gap-2">
                    {(matched_skills || []).slice(0, 4).map((skill, idx) => <span key={idx} className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded-full font-medium">{skill}</span>)}
                </div>
            </div>
        </div>
    );
};

const JDModal = ({ isOpen, onClose, onUploadSuccess }) => {
    const [title, setTitle] = useState('');
    const [file, setFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsUploading(true);
        try {
            await api.uploadJd(title, file);
            onUploadSuccess();
            onClose();
            setTitle(''); setFile(null);
        } catch(e) { console.error(e) }
        finally { setIsUploading(false); }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Add New JD">
             <form onSubmit={handleSubmit} className="space-y-4 p-4">
                  <input type="text" placeholder="Job Title" value={title} onChange={(e) => setTitle(e.target.value)} className="w-full p-2 border rounded" required />
                  <input type="file" onChange={(e) => setFile(e.target.files[0])} className="w-full text-sm" required />
                  <div className="flex justify-end gap-2 pt-4">
                    <button type="button" onClick={onClose} className="px-4 py-2 bg-slate-200 rounded">Cancel</button>
                    <button type="submit" disabled={isUploading} className="px-4 py-2 bg-indigo-600 text-white rounded disabled:bg-indigo-300">{isUploading ? 'Uploading...' : 'Upload'}</button>
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
        setIsUploading(true);
        try {
            await api.uploadResumes(Array.from(files));
            onUploadSuccess();
            onClose();
            setFiles([]);
        } catch(e) { console.error(e) }
        finally { setIsUploading(false); }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Add Resumes">
             <form onSubmit={handleSubmit} className="space-y-4 p-4">
                  <input type="file" multiple onChange={(e) => setFiles(e.target.files)} className="w-full text-sm" required />
                   <div className="flex justify-end gap-2 pt-4">
                    <button type="button" onClick={onClose} className="px-4 py-2 bg-slate-200 rounded">Cancel</button>
                    <button type="submit" disabled={isUploading} className="px-4 py-2 bg-indigo-600 text-white rounded disabled:bg-indigo-300">{isUploading ? 'Uploading...' : 'Upload'}</button>
                  </div>
            </form>
        </Modal>
    );
}

export default Dashboard;


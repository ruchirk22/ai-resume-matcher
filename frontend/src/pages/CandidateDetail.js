import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const icons = {
    arrowLeft: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>,
    check: <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="text-green-500"><polyline points="20 6 9 17 4 12"></polyline></svg>,
    x: <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="text-red-500"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>,
};

function CandidateDetail() {
  const navigate = useNavigate();
  const location = useLocation();
  
  // Data is now passed via navigation state, not fetched.
  const { candidate, jd } = location.state || {};

  if (!candidate || !jd) {
    // Fallback if the page is accessed directly without state
    return (
      <div className="min-h-screen bg-slate-50 p-6 text-center">
          <p>Candidate data not found. Please return to the dashboard.</p>
          <button onClick={() => navigate('/dashboard')} className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-md">Go Back</button>
      </div>
    );
  }

  const { resume, match_percentage, rationale, matched_skills, missing_skills } = candidate;
  const { name, email, phone, skills, experience } = resume.parsed_json || {};

  return (
    <div className="min-h-screen bg-slate-50">
       <header className="bg-white/80 backdrop-blur-sm shadow-sm sticky top-0 z-30">
            <div className="max-w-7xl mx-auto py-4 px-4">
                <button onClick={() => navigate('/dashboard')} className="flex items-center space-x-2 text-sm font-semibold">
                    {icons.arrowLeft}<span>Back to Dashboard</span>
                </button>
            </div>
        </header>

      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="bg-white shadow-sm rounded-xl p-6 mb-8">
            <div className="flex justify-between">
                <div>
                    <h1 className="text-3xl font-bold">{name}</h1>
                    <p className="text-slate-500 mt-1">Analysis for: {jd.title}</p>
                </div>
                <p className="text-4xl font-bold text-indigo-600">{match_percentage}%</p>
            </div>
            <div className="mt-4 pt-4 border-t">
                <p className="text-sm font-semibold mb-1">AI Rationale:</p>
                <p className="italic">"{rationale}"</p>
            </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-5 space-y-6">
                <InfoCard title="Contact">
                    <p><strong>Email:</strong> {email || 'N/A'}</p><p><strong>Phone:</strong> {phone || 'N/A'}</p>
                </InfoCard>
                <InfoCard title="All Skills from Resume">
                     <div className="flex flex-wrap gap-2">{(skills || []).map(s => <span key={s} className="px-2 py-1 text-xs bg-slate-100 rounded-full">{s}</span>)}</div>
                </InfoCard>
                 <InfoCard title="Work Experience">
                     <div className="space-y-4">
                        {(experience || []).map((exp, i) => (
                            <div key={i}>
                                <h4 className="font-bold">{exp.title}</h4>
                                <p className="text-sm">{exp.company} • {exp.duration}</p>
                                <ul className="list-disc list-inside mt-1 space-y-1">
                                    {exp.responsibilities?.map((r, j) => <li key={j}>{r}</li>)}
                                </ul>
                            </div>
                        ))}
                    </div>
                </InfoCard>
            </div>

            <div className="lg:col-span-7">
                <InfoCard title="AI Skill Gap Analysis">
                    <div className="space-y-4">
                        <div>
                            <h4 className="font-semibold mb-2">✓ Skills Matched</h4>
                            <div className="p-3 bg-green-50/50 rounded-lg space-y-2">
                                {(matched_skills || []).map(s => <div key={s} className="flex items-center space-x-2">{icons.check}<span>{s}</span></div>)}
                            </div>
                        </div>
                         <div>
                            <h4 className="font-semibold mb-2">⨯ Skills Missing</h4>
                             <div className="p-3 bg-red-50/50 rounded-lg space-y-2">
                                {(missing_skills || []).length > 0 ? missing_skills.map(s => <div key={s} className="flex items-center space-x-2">{icons.x}<span>{s}</span></div>) : <p>No gaps identified.</p>}
                            </div>
                        </div>
                    </div>
                </InfoCard>
            </div>
        </div>
      </main>
    </div>
  );
}

const InfoCard = ({ title, children }) => (
    <div className="bg-white shadow-sm rounded-xl p-5">
        <h3 className="text-lg font-semibold mb-3">{title}</h3>
        <div>{children}</div>
    </div>
);

export default CandidateDetail;


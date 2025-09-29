// frontend/src/services/api.js
import axios from 'axios';
import toast from 'react-hot-toast';

const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

const apiClient = axios.create({
  baseURL: API_URL,
});

apiClient.interceptors.request.use(
  (config) => {
  const token = localStorage.getItem('token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add a response interceptor for global error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'An unknown error occurred.';
    // Don't show toast for validation errors as they are expected
    if (error.response?.status !== 422) {
      toast.error(message);
    }
    return Promise.reject(error);
  }
);

// --- Auth ---
export const signup = (email, password) => apiClient.post('/auth/signup', { email, password });
export const login = (email, password) => apiClient.post('/auth/login', { email, password });

// --- Job Descriptions ---
export const listJds = () => apiClient.get('/jd');
export const uploadJd = (title, file) => {
  const formData = new FormData();
  formData.append('title', title);
  formData.append('file', file);
  return apiClient.post('/jd/upload', formData);
};
export const deleteJd = (jdId) => apiClient.delete(`/jd/${jdId}`);

// --- Resumes ---
export const bulkUploadResumes = (files) => {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  return apiClient.post('/resume/bulk-upload', formData);
};
export const getUploadStatus = (jobId) => apiClient.get(`/resume/bulk-upload/status/${jobId}`);
export const deleteAllResumes = () => apiClient.delete('/resume/all');

// NEW: preview & file fetchers (binary)
export const getResumePreviewBlob = async (resumeId) => {
  const res = await apiClient.get(`/resume/${resumeId}/preview`, { responseType: 'blob' });
  return res.data; // Blob (image/png for PDFs, text/plain for others)
};

export const getResumeFileBlob = async (resumeId) => {
  const res = await apiClient.get(`/resume/${resumeId}/file`, { responseType: 'blob' });
  return res.data; // Blob of original file
};

// --- Candidates ---
export const getCandidatesForJd = (jdId) => apiClient.get(`/candidates/${jdId}`);

// FINAL FIX: Updated to ensure the parameters are sent properly
// Ensures the request matches the backend API signature exactly
export const analyzeCandidate = (jdId, resumeId, force=false) => {
  return apiClient.post(`/candidates/analyze?jd_id=${jdId}&resume_id=${resumeId}&force=${force}`);
};

// Unified full analysis (ranking + rationale for every candidate)
export const fullAnalysis = (jdId, force = false) => 
  apiClient.get(`/candidates/full-analysis/${jdId}?force=${force}`);

export const analyzePreliminary = (jdId) => apiClient.post(`/candidates/analyze/preliminary/${jdId}`);

// --- Candidate Status (NEW) ---
export const getCandidateStatuses = (jdId) => apiClient.get(`/candidates/status/${jdId}`);

export const bulkUpdateCandidateStatus = (jdId, resumeIds, status, note = null) =>
  apiClient.patch('/candidates/status/bulk', { jd_id: jdId, resume_ids: resumeIds, status, note });

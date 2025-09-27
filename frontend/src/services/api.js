import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

const apiClient = axios.create({
  baseURL: API_URL,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) config.headers['Authorization'] = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error)
);

// Auth
export const signup = (email, password) => {
  return apiClient.post('/auth/signup', { email, password });
};

export const login = (email, password) => {
  const formData = new URLSearchParams();
  formData.append('username', email);
  formData.append('password', password);
  return apiClient.post('/auth/login', formData);
};

// Job Descriptions
export const listJds = () => apiClient.get('/jd');
export const uploadJd = (title, file) => {
  const formData = new FormData();
  formData.append('title', title);
  formData.append('file', file);
  return apiClient.post('/jd/upload', formData);
};
export const deleteJd = (jdId) => apiClient.delete(`/jd/${jdId}`);

// Resumes
export const uploadResumes = (files) => {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  return apiClient.post('/resume/upload', formData);
};
export const deleteAllResumes = () => apiClient.delete('/resume/all');

// Candidates (Only one endpoint needed now)
export const getCandidatesForJd = (jdId) => apiClient.get(`/candidates/${jdId}`);


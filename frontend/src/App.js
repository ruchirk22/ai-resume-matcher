import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login.js';
import Signup from './pages/Signup.js';
import Dashboard from './pages/Dashboard.js'; // Import the real dashboard
import CandidateDetail from './pages/CandidateDetail.js'; // Import the new candidate detail page
import ProtectedRoute from './components/ProtectedRoute.js'; // Import the protector

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate replace to="/login" />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        
        {/* Protected Routes */}
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/candidate/:resumeId/:jdId" element={<CandidateDetail />} />
        </Route>

      </Routes>
    </Router>
  );
}

export default App;


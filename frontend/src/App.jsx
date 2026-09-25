// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { ProtectedRoute, AdminRoute } from './router/index';
import './App.css';
import TopBar from './components/layout/TopBar';
import Sidebar from './components/layout/Sidebar';
import LoginPage from './pages/LoginPage';
import JobListPage from './pages/JobListPage';
import CreateJobPage from './pages/CreateJobPage';
import JobDetailPage from './pages/JobDetailPage';
import FailedJobsPage from './pages/FailedJobsPage';
import NotFoundPage from './pages/NotFoundPage';

function Layout({ children }) {
  return (
    <div className="workbench-shell">
      <Sidebar />
      <div className="workbench-main">
        <TopBar />
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            {/* Public */}
            <Route path="/login" element={<LoginPage />} />

            {/* Protected */}
            <Route
              path="/jobs"
              element={
                <ProtectedRoute>
                  <Layout><JobListPage /></Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/jobs/new"
              element={
                <ProtectedRoute>
                  <Layout><CreateJobPage /></Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/jobs/:jobId"
              element={
                <ProtectedRoute>
                  <Layout><JobDetailPage /></Layout>
                </ProtectedRoute>
              }
            />

            {/* Admin */}
            <Route
              path="/admin/failures"
              element={
                <ProtectedRoute>
                  <AdminRoute>
                    <Layout><FailedJobsPage /></Layout>
                  </AdminRoute>
                </ProtectedRoute>
              }
            />

            {/* Redirects */}
            <Route path="/" element={<Navigate to="/jobs" replace />} />
            <Route path="*" element={<Layout><NotFoundPage /></Layout>} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

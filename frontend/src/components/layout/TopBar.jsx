// src/components/layout/TopBar.jsx
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function TopBar() {
  const { status, isAdmin, userEmail, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  if (status === 'loading' || status === 'signedOut') return null;

  // Derive current section name for breadcrumb/workbench header
  const getSectionName = () => {
    if (location.pathname.startsWith('/jobs/new')) return 'New Posting';
    if (location.pathname.startsWith('/jobs/')) return 'Job Pipeline';
    if (location.pathname.startsWith('/admin') || location.pathname.startsWith('/failed-jobs')) return 'Failures';
    return 'Pipeline Overview';
  };

  return (
    <header className="topbar" aria-label="Main workbench navigation">
      <div className="topbar__left">
        <NavLink to="/jobs" className="topbar__brand" title="Resume Screener Workbench">
          <svg className="topbar__logo" width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <rect x="2" y="2" width="14" height="14" rx="3" stroke="#4F8CFF" strokeWidth="1.5" />
            <line x1="5" y1="6" x2="13" y2="6" stroke="#4F8CFF" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="5" y1="9" x2="10" y2="9" stroke="#E8EDF2" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="5" y1="12" x2="12" y2="12" stroke="#8C98A6" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span className="topbar__brand-text">RESUME SCREENER</span>
        </NavLink>
        <span className="topbar__divider" aria-hidden="true">/</span>
        <span className="topbar__section">{getSectionName()}</span>
      </div>



      <div className="topbar__user">
        <div className="topbar__identity">
          <span className="topbar__email" title={userEmail || 'Active Recruiter'}>
            {userEmail || 'recruiter'}
          </span>
          <span className={`topbar__role-badge ${isAdmin ? 'topbar__role-badge--admin' : ''}`}>
            {isAdmin ? 'ADMIN' : 'RECRUITER'}
          </span>
        </div>
        <button
          id="logout-btn"
          className="topbar__logout-btn"
          onClick={handleLogout}
          aria-label="Sign out"
          title="Sign out of recruiting workbench"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

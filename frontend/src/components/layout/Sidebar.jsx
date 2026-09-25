// src/components/layout/Sidebar.jsx
// Persistent ATS recruiting operations navigation rail.
// Adapts React Bits LineSidebar with accessible semantic links, active line indicators,
// and role-based access control.

import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Tooltip from '../ui/Tooltip';

export default function Sidebar() {
  const { status, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (status === 'loading' || status === 'signedOut') return null;

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const navItems = [
    {
      to: '/jobs',
      label: 'Jobs Pipeline',
      shortLabel: 'Pipeline',
      tooltip: 'View active requisitions and candidate pools',
      end: location.pathname === '/jobs',
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <rect x="2.5" y="3" width="13" height="3" rx="1" stroke="currentColor" strokeWidth="1.5" />
          <rect x="2.5" y="7.5" width="13" height="3" rx="1" stroke="currentColor" strokeWidth="1.5" />
          <rect x="2.5" y="12" width="13" height="3" rx="1" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      ),
    },
    {
      to: '/jobs/new',
      label: 'New Requisition',
      shortLabel: 'Create',
      tooltip: 'Create new job posting and define screening criteria',
      end: true,
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.5" />
          <line x1="9" y1="6" x2="9" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="6" y1="9" x2="12" y2="9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      ),
    },
  ];

  if (isAdmin) {
    navItems.push({
      to: '/admin/failures',
      label: 'Pipeline Failures',
      shortLabel: 'Failures',
      tooltip: 'Inspect ingestion and scoring dead-letter errors',
      end: false,
      adminOnly: true,
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path d="M9 2.5L16 14.5H2L9 2.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          <line x1="9" y1="7" x2="9" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <circle cx="9" cy="12.5" r="0.75" fill="currentColor" />
        </svg>
      ),
    });
  }

  return (
    <aside className="workbench-sidebar" aria-label="Recruiting workbench navigation">
      <div className="sidebar-brand">
        <NavLink to="/jobs" className="sidebar-brand__link" title="Resume Screener Workbench">
          <svg className="sidebar-brand__logo" width="20" height="20" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <rect x="2" y="2" width="14" height="14" rx="3" stroke="#4F8CFF" strokeWidth="1.75" />
            <line x1="5" y1="6" x2="13" y2="6" stroke="#4F8CFF" strokeWidth="1.75" strokeLinecap="round" />
            <line x1="5" y1="9" x2="10" y2="9" stroke="#E8EDF2" strokeWidth="1.75" strokeLinecap="round" />
            <line x1="5" y1="12" x2="12" y2="12" stroke="#8C98A6" strokeWidth="1.75" strokeLinecap="round" />
          </svg>
          <div className="sidebar-brand__meta">
            <span className="sidebar-brand__title">TALENT OPS</span>
            <span className="sidebar-brand__sub">SCREENER v2</span>
          </div>
        </NavLink>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-nav__label">PIPELINE</div>
        <ul className="sidebar-nav__list">
          {navItems.map((item) => {
            const isItemActive = item.end
              ? location.pathname === item.to
              : location.pathname.startsWith(item.to);

            return (
              <li key={item.to} className="sidebar-nav__item">
                <Tooltip content={item.tooltip} position="right">
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={`sidebar-nav__link ${isItemActive ? 'active' : ''}`}
                    aria-current={isItemActive ? 'page' : undefined}
                  >
                    <span className="sidebar-nav__active-indicator" aria-hidden="true" />
                    <span className="sidebar-nav__icon">{item.icon}</span>
                    <span className="sidebar-nav__text">{item.label}</span>
                    {item.adminOnly && <span className="sidebar-nav__badge">ADMIN</span>}
                  </NavLink>
                </Tooltip>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <Tooltip content="Sign out of the recruiting workbench" position="right">
          <button
            type="button"
            className="sidebar-logout-btn"
            onClick={handleLogout}
            aria-label="Sign out"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M6 2H3a1 1 0 00-1 1v10a1 1 0 001 1h3M10 11.5L13.5 8 10 4.5M13.5 8H5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="sidebar-logout-text">Sign Out</span>
          </button>
        </Tooltip>
      </div>
    </aside>
  );
}

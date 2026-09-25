// src/router/index.jsx
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import NoAccessPage from '../pages/NoAccessPage';

/**
 * Redirects unauthenticated users to /login?next=<current path>.
 * Shows NoAccessPage for authenticated users with no group.
 */
export function ProtectedRoute({ children }) {
  const { status, hasAccess } = useAuth();
  const location = useLocation();

  if (status === 'loading') return null; // AuthContext is still resolving

  if (status === 'signedOut') {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (!hasAccess) return <NoAccessPage />;

  return children;
}

/**
 * Renders a "You don't have access" page for non-admin users.
 * The topbar still hides the Admin nav link — this guards the route itself.
 */
export function AdminRoute({ children }) {
  const { status, isAdmin } = useAuth();

  if (status === 'loading') return null;

  if (!isAdmin) {
    return (
      <div className="no-access-page">
        <h1>Access restricted</h1>
        <p>This page is only available to administrators.</p>
      </div>
    );
  }

  return children;
}

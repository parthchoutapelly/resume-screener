// src/pages/NotFoundPage.jsx
import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="empty-state" role="main">
      <h1 className="empty-state__title">Page not found</h1>
      <p className="empty-state__desc">The page you&rsquo;re looking for doesn&rsquo;t exist.</p>
      <Link to="/jobs" className="btn btn--primary">Back to jobs</Link>
    </div>
  );
}

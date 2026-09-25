// src/pages/LoginPage.jsx
// Two-step: credentials → optional new-password challenge.
// Maps Cognito errors to generic copy; never echoes raw Cognito messages.
import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const COGNITO_ERROR_MAP = {
  UserNotFoundException: 'Incorrect email or password.',
  NotAuthorizedException: 'Incorrect email or password.',
  PasswordResetRequiredException: 'Your password needs to be reset. Contact an administrator.',
  UserNotConfirmedException: 'Your account is not confirmed. Contact an administrator.',
};

function mapCognitoError(err) {
  return COGNITO_ERROR_MAP[err?.name] || COGNITO_ERROR_MAP[err?.code] || 'Incorrect email or password.';
}

export default function LoginPage() {
  const { status, login, completeNewPassword } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState('credentials'); // 'credentials' | 'newPassword'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [pwError, setPwError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const expiredMsg = searchParams.get('reason') === 'expired';
  const emailRef = useRef(null);
  const newPwRef = useRef(null);

  useEffect(() => {
    if (status === 'signedIn') {
      const next = searchParams.get('next') || '/jobs';
      navigate(next, { replace: true });
    }
  }, [status, navigate, searchParams]);

  useEffect(() => {
    if (step === 'credentials') emailRef.current?.focus();
    if (step === 'newPassword') newPwRef.current?.focus();
  }, [step]);

  const handleCredentials = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.done) {
        // AuthContext will update and the useEffect will navigate
      } else if (result.needsNewPassword) {
        setStep('newPassword');
      }
    } catch (err) {
      setError(mapCognitoError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleNewPassword = async (e) => {
    e.preventDefault();
    setPwError('');
    if (newPassword !== confirmPassword) {
      setPwError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 8) {
      setPwError('Password must be at least 8 characters.');
      return;
    }
    setSubmitting(true);
    try {
      await completeNewPassword(newPassword);
      // AuthContext will update and navigate
    } catch (err) {
      setPwError(err?.message || 'Could not set password. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-card__logo" aria-hidden="true">
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <rect width="40" height="40" rx="8" fill="#2563eb"/>
            <path d="M12 14h16M12 20h10M12 26h12" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
          </svg>
        </div>

        {step === 'credentials' ? (
          <>
            <h1 className="login-card__title">Sign in</h1>
            <p className="login-card__subtitle">Resume Screener</p>
            {expiredMsg && (
              <div className="error-message" role="alert" style={{ marginBottom: 'var(--space-4)' }}>
                Your session expired. Please sign in again.
              </div>
            )}
            <form className="login-form" id="login-form" onSubmit={handleCredentials} noValidate>
              {error && (
                <div className="error-message" role="alert" id="login-error">{error}</div>
              )}
              <div className="field">
                <label className="field__label" htmlFor="email">Email</label>
                <input
                  id="email"
                  ref={emailRef}
                  type="email"
                  className="input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                  aria-describedby={error ? 'login-error' : undefined}
                />
              </div>
              <div className="field">
                <label className="field__label" htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  className="input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
              <button
                id="sign-in-btn"
                type="submit"
                className="btn btn--primary btn--full btn--lg"
                disabled={submitting || !email || !password}
              >
                {submitting ? 'Signing in\u2026' : 'Sign in'}
              </button>
            </form>
            <p style={{ textAlign: 'center', marginTop: 'var(--space-4)', fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
              Forgot your password? Contact your administrator.
            </p>
          </>
        ) : (
          <>
            <h1 className="login-card__title">Set a new password</h1>
            <p className="login-card__subtitle">You must set a new password before you can sign in.</p>
            <form className="login-form" id="new-password-form" onSubmit={handleNewPassword} noValidate>
              {pwError && (
                <div className="error-message" role="alert" id="pw-error">{pwError}</div>
              )}
              <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
                Minimum 8 characters, including a number and a special character.
              </p>
              <div className="field">
                <label className="field__label" htmlFor="new-password">New password</label>
                <input
                  id="new-password"
                  ref={newPwRef}
                  type="password"
                  className="input"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  aria-describedby={pwError ? 'pw-error' : undefined}
                />
              </div>
              <div className="field">
                <label className="field__label" htmlFor="confirm-password">Confirm new password</label>
                <input
                  id="confirm-password"
                  type="password"
                  className="input"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>
              <button
                id="set-password-btn"
                type="submit"
                className="btn btn--primary btn--full btn--lg"
                disabled={submitting || !newPassword || !confirmPassword}
              >
                {submitting ? 'Setting password\u2026' : 'Set password and sign in'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

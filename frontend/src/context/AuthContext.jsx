// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getIdToken, getGroups, login as cognitoLogin, completeNewPassword as cognitoCompletePassword, logout as cognitoLogout } from '../auth/cognito';

const AuthContext = createContext(null);

/**
 * status: 'loading' | 'signedOut' | 'signedIn'
 * groups: string[]
 * isAdmin: boolean
 * hasAccess: boolean  (Recruiter or Admin group)
 */
export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading');
  const [groups, setGroups] = useState([]);
  const [userEmail, setUserEmail] = useState('');

  const refreshAuth = useCallback(async () => {
    try {
      const token = await getIdToken();
      if (!token) {
        setStatus('signedOut');
        setGroups([]);
        setUserEmail('');
        return;
      }
      try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        setUserEmail(payload.email || payload['cognito:username'] || '');
      } catch {
        setUserEmail('');
      }
      const g = await getGroups();
      setGroups(g);
      setStatus('signedIn');
    } catch {
      setStatus('signedOut');
      setGroups([]);
      setUserEmail('');
    }
  }, []);

  useEffect(() => { refreshAuth(); }, [refreshAuth]);

  const login = useCallback(async (email, password) => {
    const result = await cognitoLogin(email, password);
    if (result.done) await refreshAuth();
    return result;
  }, [refreshAuth]);

  const completeNewPassword = useCallback(async (newPassword) => {
    await cognitoCompletePassword(newPassword);
    await refreshAuth();
  }, [refreshAuth]);

  const logout = useCallback(async () => {
    await cognitoLogout();
    setStatus('signedOut');
    setGroups([]);
    setUserEmail('');
  }, []);

  const isAdmin = groups.includes('Admin');
  const hasAccess = groups.includes('Recruiter') || isAdmin;

  return (
    <AuthContext.Provider value={{ status, groups, isAdmin, hasAccess, userEmail, login, completeNewPassword, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

/**
 * Auth context for the LUMEN mobile app.
 * Supports email/password login and one-tap demo investor access.
 * Persists the Bearer session token in AsyncStorage.
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, setToken } from './api';

export type User = {
  user_id?: string;
  email?: string;
  name?: string;
  role?: string;
  roles?: string[];
} | null;

type AuthState = {
  user: User;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  demoInvestor: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthCtx = createContext<AuthState>({} as AuthState);
export const useAuth = () => useContext(AuthCtx);

function extractToken(data: any): string | null {
  return data?.session_token || data?.token || null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await api.get('/auth/me');
      setUser(me?.user || me || null);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const finishAuth = async (data: any) => {
    const token = extractToken(data);
    if (token) await setToken(token);
    setUser(data?.user || data || null);
    if (!data?.user && !data?.email) await refresh();
  };

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.post('/auth/login', { email, password });
    await finishAuth(data);
  }, []);

  const demoInvestor = useCallback(async () => {
    const data = await api.post('/auth/quick', { email: 'client@atlas.dev' });
    await finishAuth(data);
  }, []);

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout', {}); } catch { /* ignore */ }
    await setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, login, demoInvestor, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

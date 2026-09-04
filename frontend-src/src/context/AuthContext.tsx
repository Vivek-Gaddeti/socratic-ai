'use client';
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '@/lib/api';

interface User {
  id: string;
  name: string;
  email: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('socratic_token');
    if (storedToken) {
      setToken(storedToken);
      api.getMe(storedToken)
        .then(setUser)
        .catch(() => {
          localStorage.removeItem('socratic_token');
          setToken(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const data = await api.login(email, password);
    localStorage.setItem('socratic_token', data.access_token);
    setToken(data.access_token);
    const me = await api.getMe(data.access_token);
    setUser(me);
  };

  const register = async (name: string, email: string, password: string) => {
    const data = await api.register(name, email, password);
    localStorage.setItem('socratic_token', data.access_token);
    setToken(data.access_token);
    setUser({ id: data.user_id, name: data.name, email });
  };

  const logout = () => {
    localStorage.removeItem('socratic_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

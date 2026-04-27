import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, type ReactNode } from 'react';

interface User {
  id: string;
  email: string;
  name?: string;
  role?: string;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  refreshAccessToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const storedAccessToken = localStorage.getItem('accessToken');
    const storedUser = localStorage.getItem('user');

    if (storedAccessToken && storedUser) {
      setAccessToken(storedAccessToken);
      setUser(JSON.parse(storedUser));
    }
    setIsLoading(false);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('user');
    setAccessToken(null);
    setUser(null);
  }, []);

  // Periodic token expiry check (every 60s)
  useEffect(() => {
    if (!accessToken) return;
    const interval = setInterval(() => {
      try {
        const payload = JSON.parse(atob(accessToken.split('.')[1]));
        if (payload.exp && Date.now() >= payload.exp * 1000) {
          logout();
        }
      } catch {
        logout();
      }
    }, 60000);
    return () => clearInterval(interval);
  }, [accessToken, logout]);

  useEffect(() => {
    if (!accessToken || !user) {
      return;
    }

    try {
      const payload = JSON.parse(atob(accessToken.split('.')[1]));
      if (payload.exp && Date.now() >= payload.exp * 1000) {
        logout();
      }
    } catch {
      logout();
    }
  }, [accessToken, user, logout]);

  useEffect(() => {
    const handleStorage = () => {
      const storedAccessToken = localStorage.getItem('accessToken');
      const storedUser = localStorage.getItem('user');

      if (!storedAccessToken || !storedUser) {
        logout();
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [logout]);

  useEffect(() => {
    const handleAuthExpired = () => {
      logout();
    };

    window.addEventListener('auth:expired', handleAuthExpired as EventListener);
    return () => window.removeEventListener('auth:expired', handleAuthExpired as EventListener);
  }, [logout]);

  useEffect(() => {
    const handleTokenRefreshed = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.access_token) {
        setAccessToken(detail.access_token);
        if (detail.user) {
          setUser(detail.user);
          localStorage.setItem('user', JSON.stringify(detail.user));
        }
      }
    };

    window.addEventListener('auth:token_refreshed', handleTokenRefreshed as EventListener);
    return () => window.removeEventListener('auth:token_refreshed', handleTokenRefreshed as EventListener);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || error.detail || 'Login failed');
    }

    const data = await response.json();
    localStorage.setItem('accessToken', data.access_token);
    if (data.refresh_token) {
      localStorage.setItem('refreshToken', data.refresh_token);
    }
    localStorage.setItem('user', JSON.stringify(data.user));
    setAccessToken(data.access_token);
    setUser(data.user);
  }, []);

  const signup = useCallback(async (email: string, password: string, name?: string) => {
    const response = await fetch(`${API_BASE_URL}/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || error.detail || 'Signup failed');
    }

    const data = await response.json();
    localStorage.setItem('accessToken', data.access_token);
    if (data.refresh_token) {
      localStorage.setItem('refreshToken', data.refresh_token);
    }
    localStorage.setItem('user', JSON.stringify(data.user));
    setAccessToken(data.access_token);
    setUser(data.user);
  }, []);

  const refreshAccessToken = useCallback(async (): Promise<string | null> => {
    const storedRefreshToken = localStorage.getItem('refreshToken');
    if (!storedRefreshToken) return null;
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: storedRefreshToken }),
      });
      if (!response.ok) return null;
      const data = await response.json();
      localStorage.setItem('accessToken', data.access_token);
      if (data.refresh_token) {
        localStorage.setItem('refreshToken', data.refresh_token);
      }
      setAccessToken(data.access_token);
      return data.access_token;
    } catch {
      return null;
    }
  }, []);

  const value = useMemo(() => ({
    user,
    accessToken,
    isAuthenticated: !!user,
    isLoading,
    login,
    signup,
    logout,
    refreshAccessToken,
  }), [user, accessToken, isLoading, login, signup, logout, refreshAccessToken]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

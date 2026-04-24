import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import AgentBuilder from './pages/AgentBuilder';
import Orchestrator from './pages/Orchestrator';
import Monitor from './pages/Monitor';
import Tools from './pages/Tools';
import Settings from './pages/Settings';
import WorkflowBuilder from './pages/WorkflowBuilder';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return null;
  }

  // Ground-truth check: localStorage token must exist.
  // This prevents temporary React state mismatches from causing
  // unwanted redirects when the token is actually valid.
  const hasToken = !!localStorage.getItem('accessToken');
  if (!hasToken && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

function AppRoutes() {
  const { isAuthenticated } = useAuth();
  
  return (
    <Routes>
      <Route 
        path="/" 
        element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Landing />} 
      />
      <Route 
        path="/login" 
        element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Login />} 
      />
      <Route 
        path="/signup" 
        element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Signup />} 
      />
      
      {/* Authenticated Routes wrapped in Layout */}
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/builder" element={<AgentBuilder />} />
        <Route path="/orchestrator" element={<Orchestrator />} />
        <Route path="/workflows/builder" element={<WorkflowBuilder />} />
        <Route path="/monitor" element={<Monitor />} />
        <Route path="/tools" element={<Tools />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <AppRoutes />
      </Router>
    </AuthProvider>
  );
}

export default App;

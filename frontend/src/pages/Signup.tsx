import { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Layers, ArrowLeft } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Signup = () => {
  const navigate = useNavigate();
  const { signup } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    
    try {
      await signup(email, password, name || undefined);
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Signup failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row overflow-hidden">
      
      {/* Decorative Side Panel */}
      <div className="hidden md:flex flex-1 bg-surface-low relative flex-col justify-between p-12 border-r border-outline/10">
        <div className="z-10">
          <div className="flex items-center gap-2 mb-12">
            <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
              <Layers className="w-5 h-5 text-primary" />
            </div>
            <span className="font-semibold text-xl tracking-tight">AgentOS</span>
          </div>
          <h2 className="text-4xl font-bold tracking-tight mb-4">
            Create Your <br/> Account.
          </h2>
          <p className="text-secondaryText text-lg max-w-sm">
            Join AgentOS to orchestrate intelligent multi-agent workflows.
          </p>
        </div>
        
        {/* Abstract Ambient Shape */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[100px] mix-blend-screen pointer-events-none"></div>
      </div>

      {/* Signup Form */}
      <div className="flex-1 flex items-center justify-center p-6 relative">
        <button 
          onClick={() => navigate('/')}
          className="absolute top-8 left-8 text-secondaryText hover:text-primaryText flex items-center gap-2 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm"
        >
          <div className="mb-10 text-center md:text-left">
            <h1 className="text-3xl font-bold tracking-tight mb-2">Sign Up</h1>
            <p className="text-secondaryText">Create your working account.</p>
          </div>

          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                {error}
              </div>
            )}
            
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Name</label>
                <input 
                  type="text" 
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full obsidian-input"
                  placeholder="Your name"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Email</label>
                <input 
                  type="email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full obsidian-input"
                  placeholder="admin@agentos.io"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Password</label>
                <input 
                  type="password" 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full obsidian-input"
                  placeholder="••••••••"
                  required
                  minLength={8}
                />
                <p className="text-xs text-secondaryText mt-1">Min 8 characters with uppercase, lowercase, and digit</p>
              </div>
            </div>

            <button 
              type="submit" 
              disabled={isLoading}
              className="w-full btn-primary py-3 flex justify-center items-center shadow-glow-cyan mt-8 disabled:opacity-50"
            >
              {isLoading ? 'Creating Account...' : 'Create Account'}
            </button>
            
            <p className="text-center text-sm text-secondaryText mt-6">
              Already have an account?{' '}
              <button 
                type="button"
                onClick={() => navigate('/login')}
                className="text-primary hover:text-primary-container"
              >
                Sign In
              </button>
            </p>
          </form>
        </motion.div>
      </div>
    </div>
  );
};

export default Signup;

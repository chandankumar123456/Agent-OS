import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Layers, ArrowLeft } from 'lucide-react';
import { buttonTap } from '../lib/animations';
import { useAuth } from '../context/AuthContext';

const Login = () => {
 const navigate = useNavigate();
 const { login } = useAuth();
 const [email, setEmail] = useState('');
 const [password, setPassword] = useState('');
 const [error, setError] = useState('');
 const [isLoading, setIsLoading] = useState(false);

 const handleSubmit = async (e: React.FormEvent) => {
 e.preventDefault();
 setError('');
 setIsLoading(true);
 
 try {
 await login(email, password);
 navigate('/dashboard');
 } catch (err) {
 setError(err instanceof Error ? err.message : 'Login failed');
 } finally {
 setIsLoading(false);
 }
 };

 return (
 <div className="min-h-screen bg-surface-lowest flex flex-col md:flex-row overflow-hidden font-retro">
 
 {/* Decorative Side Panel */}
 <div className="hidden md:flex flex-1 bg-surface relative flex-col justify-between p-8 border-r-4 border-outline">
 <div className="z-10">
 <div className="flex items-center gap-2 mb-8 cursor-pointer" onClick={() => navigate('/')}>
 <div className="w-12 h-12 border-4 border-outline bg-primary flex items-center justify-center shadow-pixel">
 <Layers className="w-7 h-7 text-white" />
 </div>
 <span className="font-pixel text-lg tracking-tighter uppercase">AgentOS</span>
 </div>
 <h2 className="text-4xl font-pixel uppercase tracking-tight mb-6 leading-tight">
 Welcome to the <br/> Command Center.
 </h2>
 <p className="text-secondaryText text-xl max-w-sm leading-relaxed">
 Access your multi-agent workflows, monitor live executions, and orchestrate intelligence.
 </p>
 </div>
 
 {/* Pixel Grid Background Effect */}
 <div className="absolute inset-0 opacity-[0.03] pointer-events-none" 
 style={{backgroundImage: 'radial-gradient(#1A1A2E 1px, transparent 1px)', backgroundSize: '20px 20px'}}></div>
 </div>

 {/* Login Form */}
 <div className="flex-1 flex items-center justify-center p-6 relative">
 <motion.button
 {...buttonTap}
 onClick={() => navigate('/')}
 className="absolute top-8 left-8 text-primaryText hover:underline flex items-center gap-2 font-pixel text-[10px] uppercase"
 >
 <ArrowLeft className="w-4 h-4" /> [ Back ]
 </motion.button>

 <motion.div 
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 transition={{ duration: 0.1 }}
 className="w-full max-w-sm"
 >
 <div className="mb-8 text-center md:text-left">
 <h1 className="text-4xl font-pixel uppercase mb-4">Sign In</h1>
 <p className="text-secondaryText text-xl">Initialize your working session.</p>
 </div>

 <form className="space-y-8" onSubmit={handleSubmit}>
 <AnimatePresence>
 {error && (
 <motion.div
 initial={{ opacity: 0, y: -4 }}
 animate={{ opacity: 1, y: 0 }}
 exit={{ opacity: 0, y: -4 }}
 className="p-4 border-4 border-[#FF4B4B] bg-white text-[#FF4B4B] font-pixel text-[10px] uppercase shadow-pixel"
 >
 {error}
 </motion.div>
 )}
 </AnimatePresence>
 
 <div className="space-y-6">
 <div>
 <label className="block text-xs font-pixel tracking-widest uppercase text-secondaryText mb-4">Email</label>
 <input
 type="email"
 value={email}
 onChange={(e) => setEmail(e.target.value)}
 className="w-full pixel-input"
 placeholder="admin@agentos.io"
 required
 />
 </div>
 <div>
 <div className="flex justify-between items-center mb-4">
 <label className="block text-xs font-pixel tracking-widest uppercase text-secondaryText">Password</label>
 </div>
 <input
 type="password"
 value={password}
 onChange={(e) => setPassword(e.target.value)}
 className="w-full pixel-input"
 placeholder="••••••••"
 required
 />
 </div>
 </div>

 <motion.button
 type="submit"
 disabled={isLoading}
 {...buttonTap}
 className="w-full btn-primary py-4 flex justify-center items-center shadow-pixel mt-8 disabled:opacity-50"
 >
 {isLoading ? 'Authenticating...' : 'Authenticate Session'}
 </motion.button>
 
 <p className="text-center text-lg text-secondaryText mt-8 font-retro">
 No access protocol?{' '}
 <motion.button
 type="button"
 {...buttonTap}
 onClick={() => navigate('/signup')}
 className="text-primary hover:underline font-pixel text-[10px] uppercase ml-2"
 >
 Sign Up
 </motion.button>
 </p>
 </form>
 </motion.div>
 </div>
 </div>
 );
};

export default Login;

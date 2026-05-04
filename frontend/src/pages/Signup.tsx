import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Layers, ArrowLeft } from 'lucide-react';
import { buttonTap } from '../lib/animations';
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
 <div className="min-h-screen bg-background flex flex-col md:flex-row overflow-hidden font-retro">
 
 {/* Decorative Side Panel */}
 <div className="hidden md:flex flex-1 bg-white relative flex-col justify-between p-8 border-r-4 border-outline">
 <div className="z-10">
 <div className="flex items-center gap-4 mb-8">
 <div className="w-12 h-12 border-4 border-outline bg-primary flex items-center justify-center shadow-pixel">
 <Layers className="w-6 h-6 text-white" />
 </div>
 <span className="font-pixel text-2xl uppercase tracking-tighter">Agent_OS</span>
 </div>
 <h2 className="text-6xl font-pixel uppercase tracking-tight mb-8 leading-tight">
 INITIATE <br/> ACCESS_ID.
 </h2>
 <p className="text-xl font-retro uppercase text-secondaryText max-w-sm leading-relaxed opacity-70">
 REGISTER_ACCOUNT: JOIN THE NEURAL ORCHESTRATION NETWORK.
 </p>
 </div>
 
 {/* Retro Grid Pattern */}
 <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle, #000 1px, transparent 1px)', backgroundSize: '24px 24px' }}></div>
 </div>

 {/* Signup Form */}
 <div className="flex-1 flex items-center justify-center p-8 relative bg-surface-high">
 <motion.button
 onClick={() => navigate('/')}
 className="absolute top-10 left-10 text-secondaryText hover:text-primary flex items-center gap-2 font-pixel text-[10px] uppercase border-4 border-transparent hover:border-outline p-2 "
 {...buttonTap}
 >
 <ArrowLeft className="w-4 h-4" /> [ BACK ]
 </motion.button>

 <motion.div 
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 className="w-full max-w-md pixel-panel p-8 bg-white"
 >
 <div className="mb-8 text-center md:text-left">
 <h1 className="text-xs font-pixel uppercase tracking-widest text-primary mb-4">SYSTEM_SIGNUP</h1>
 <h2 className="text-4xl font-pixel uppercase tracking-tighter">NEW_OPERATOR</h2>
 </div>

 <form className="space-y-8" onSubmit={handleSubmit}>
 <AnimatePresence>
 {error && (
 <motion.div
 initial={{ opacity: 0, x: -10 }}
 animate={{ opacity: 1, x: 0 }}
 exit={{ opacity: 0, x: 10 }}
 className="p-4 border-4 border-[#FF4B4B] bg-[#FF4B4B]/10 text-[#FF4B4B] font-retro text-lg uppercase"
 >
 !! ERROR: {error}
 </motion.div>
 )}
 </AnimatePresence>
 
 <div className="space-y-6">
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Identity_Alias</label>
 <input
 type="text"
 value={name}
 onChange={(e) => setName(e.target.value)}
 className="w-full pixel-input py-4 text-xl font-retro uppercase"
 placeholder="OPERATOR_NAME"
 />
 </div>
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Comm_Link_Email</label>
 <input
 type="email"
 value={email}
 onChange={(e) => setEmail(e.target.value)}
 className="w-full pixel-input py-4 text-xl font-retro uppercase"
 placeholder="USER@AGENTOS.LOCAL"
 required
 />
 </div>
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Security_Cipher</label>
 <input
 type="password"
 value={password}
 onChange={(e) => setPassword(e.target.value)}
 className="w-full pixel-input py-4 text-xl font-retro uppercase"
 placeholder="••••••••"
 required
 minLength={8}
 />
 <p className="text-[10px] font-pixel uppercase text-secondaryText mt-4 opacity-50">SECURITY: MIN_8_CHARS_UPPER_LOWER_DIGIT</p>
 </div>
 </div>

 <motion.button
 type="submit"
 disabled={isLoading}
 className="w-full btn-primary py-4 flex justify-center items-center text-[10px] font-pixel uppercase mt-8"
 {...buttonTap}
 >
 {isLoading ? '[ AUTHORIZING... ]' : '[ INITIALIZE_ACCOUNT ]'}
 </motion.button>
 
 <div className="text-center text-[10px] font-pixel uppercase text-secondaryText mt-8 pt-6 border-t-4 border-outline/5">
 ALREADY_REGISTERED?{' '}
 <button
 type="button"
 onClick={() => navigate('/login')}
 className="text-primary hover:underline decoration-2 underline-offset-4"
 >
 SIGN_IN_OPERATOR
 </button>
 </div>
 </form>
 </motion.div>
 </div>
 </div>
 );
};

export default Signup;

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';
import { buttonTap } from '../lib/animations';

import { StatusBadge } from '../components/ui/StatusBadge';

const Orchestrator = () => {
 const [agents, setAgents] = useState<Array<{agent_id: string; name: string; role: string; status: string}>>([]);
 const [loading, setLoading] = useState(true);

 useEffect(() => {
 apiClient.listAgents()
 .then(setAgents)
 .finally(() => setLoading(false));
 }, []);

 const refreshAgents = async () => {
 setLoading(true);
 try {
 setAgents(await apiClient.listAgents());
 } finally {
 setLoading(false);
 }
 };

 return (
 <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10 h-full max-w-6xl mx-auto">
 <div className="flex justify-between items-end">
 <div>
 <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Process Orchestrator</h1>
 <p className="text-xl font-retro uppercase text-secondaryText opacity-60">Neural pipeline status and agent synchrony.</p>
 </div>
 <motion.button
 className="btn-secondary flex items-center gap-3 py-4 px-6 text-[10px] font-pixel uppercase"
 onClick={refreshAgents}
 {...buttonTap}
 >
 <RefreshCw className="w-5 h-5" /> [ RELOAD_PIPELINE ]
 </motion.button>
 </div>

 <div className="flex-1 flex justify-center py-8 pixel-panel bg-white/5 relative overflow-hidden">
 {loading ? (
 <div className="flex items-center justify-center py-8">
 <div className="flex flex-col items-center gap-6">
 <div className="w-16 h-16 border-4 border-primary border-t-transparent animate-spin" />
 <p className="font-pixel text-[10px] uppercase text-primary">SCANNING_PIPELINE...</p>
 </div>
 </div>
 ) : (
 <div className="w-full max-w-3xl relative px-8">
 <motion.div
 className="absolute left-[63px] top-10 bottom-10 w-1 bg-outline/20"
 initial={{ scaleY: 0 }}
 animate={{ scaleY: 1 }}
 transition={{ duration: 0.5 }}
 style={{ originY: 0 }}
 />
 <div className="flex flex-col gap-10">
 {agents.map((agent, idx) => (
 <motion.div
 key={agent.agent_id}
 initial={{ opacity: 0, x: -20 }}
 animate={{ opacity: 1, x: 0 }}
 className="flex items-center gap-10 z-10 relative"
 >
 <div className="flex flex-col items-center">
 <motion.div
 className={`w-14 h-14 border-4 flex items-center justify-center shadow-pixel ${
 agent.status === 'active' ? 'bg-secondary border-outline text-white' : 'bg-white border-outline text-primary'
 }`}
 {...buttonTap}
 >
 <CheckCircle2 className="w-6 h-6" />
 </motion.div>
 {idx < agents.length - 1 && (
 <div className="w-1 h-10 bg-outline/20 -mb-8" />
 )}
 </div>
 <div className="flex-1 pixel-card p-6 bg-white flex items-center justify-between border-4">
 <div>
 <h3 className="text-xs font-pixel uppercase tracking-tight text-primary mb-2">{agent.name}</h3>
 <p className="text-lg font-retro uppercase text-secondaryText leading-none">{agent.role}</p>
 </div>
 <div className="flex items-center gap-4">
 <div className="h-8 w-1 bg-outline/10" />
 <StatusBadge status={agent.status || 'idle'} />
 </div>
 </div>
 </motion.div>
 ))}
 </div>
 </div>
 )}
 </div>
 </motion.div>
 );
};

export default Orchestrator;

import React from 'react';
import { motion } from 'framer-motion';
import { Search, Calculator, FileText, GitBranch, Plus, ArrowRight, Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { buttonTap, cardInteractions } from '../lib/animations';

interface QuickStartPanelProps {
 onExecuteTask: (query: string) => void;
 collapsible?: boolean;
}

const QuickStartPanel: React.FC<QuickStartPanelProps> = ({ onExecuteTask, collapsible = false }) => {
 const navigate = useNavigate();
 const [isCollapsed, setIsCollapsed] = React.useState(false);

 const presets = [
 {
  id: 'research-ai',
  title: 'Research latest AI news',
  description: 'Discover and summarize the newest trends in artificial intelligence.',
  query: 'Research the latest AI news and summarize key trends',
  icon: Search,
  action: 'run',
  color: 'bg-accent-purple',
 },
 {
  id: 'calculate-formulas',
  title: 'Calculate complex formulas',
  description: 'Run advanced calculations like compound interest and projections.',
  query: 'Calculate the compound interest on $10,000 at 7% for 10 years',
  icon: Calculator,
  action: 'run',
  color: 'bg-accent-yellow',
 },
 {
  id: 'review-summarize',
  title: 'Review and summarize',
  description: 'Get a concise summary of effective agent design principles.',
  query: 'Review and summarize the key points of effective agent design',
  icon: FileText,
  action: 'run',
  color: 'bg-accent-pink',
 },
 {
  id: 'build-workflow',
  title: 'Build a workflow',
  description: 'Open the visual workflow builder to orchestrate agents.',
  icon: GitBranch,
  action: 'navigate',
  path: '/workflows/builder',
  color: 'bg-secondary',
 },
 {
  id: 'create-agent',
  title: 'Create a custom agent',
  description: 'Design and configure a new agent from scratch.',
  icon: Plus,
  action: 'navigate',
  path: '/builder',
  color: 'bg-primary',
 },
 ];

 const handleAction = (preset: typeof presets[0]) => {
 if (preset.action === 'run' && preset.query) {
  onExecuteTask(preset.query);
 } else if (preset.action === 'navigate' && preset.path) {
  navigate(preset.path);
 }
 };

 return (
 <motion.div
  initial={{ opacity: 0, y: 10 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.1 }}
  className="pixel-panel p-8 bg-white"
 >
  <div className="flex justify-between items-center mb-8">
  <div>
   <h2 className="text-xl font-pixel uppercase tracking-tight">Quick Start</h2>
   <p className="text-secondaryText text-xl mt-2 font-retro uppercase opacity-60">
   Jump in with a preset task or explore the builders.
   </p>
  </div>
  {collapsible && (
   <motion.button
   {...buttonTap}
   onClick={() => setIsCollapsed(!isCollapsed)}
   className="text-[10px] font-pixel uppercase text-secondaryText hover:text-black underline"
   >
   {isCollapsed ? '[ EXPAND ]' : '[ COLLAPSE ]'}
   </motion.button>
  )}
  </div>

  {!isCollapsed && (
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
   {presets.map((preset, idx) => (
   <motion.div
    key={preset.id}
    initial={{ opacity: 0, scale: 0.95 }}
    animate={{ opacity: 1, scale: 1 }}
    transition={{ duration: 0.1, delay: idx * 0.02 }}
    {...cardInteractions}
    className="flex flex-col gap-6 p-6 border-4 border-outline bg-background shadow-pixel group cursor-pointer"
   >
    <div className={`w-14 h-14 border-4 border-outline ${preset.color} flex items-center justify-center shadow-pixel-sm transition-none`}>
    <preset.icon className="w-7 h-7 text-white" />
    </div>
    <div className="flex-1">
    <h3 className="text-xs font-pixel uppercase text-black leading-tight">{preset.title}</h3>
    <p className="text-lg text-secondaryText mt-4 leading-none font-retro uppercase opacity-70">
     {preset.description}
    </p>
    </div>
    <motion.button
    {...buttonTap}
    onClick={() => handleAction(preset)}
    className="w-full mt-auto btn-primary py-3 flex items-center justify-center gap-3 text-[10px] font-pixel"
    >
    {preset.action === 'run' ? (
     <>
     <Play className="w-3 h-3 fill-current" /> [ RUN ]
     </>
    ) : (
     <>
     [ OPEN ] <ArrowRight className="w-3 h-3" />
     </>
    )}
    </motion.button>
   </motion.div>
   ))}
  </div>
  )}
 </motion.div>
 );
};

export default QuickStartPanel;

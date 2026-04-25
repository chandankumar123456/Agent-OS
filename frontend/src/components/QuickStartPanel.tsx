import React from 'react';
import { motion } from 'framer-motion';
import { Search, Calculator, FileText, GitBranch, Plus, ArrowRight, Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

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
    },
    {
      id: 'calculate-formulas',
      title: 'Calculate complex formulas',
      description: 'Run advanced calculations like compound interest and projections.',
      query: 'Calculate the compound interest on $10,000 at 7% for 10 years',
      icon: Calculator,
      action: 'run',
    },
    {
      id: 'review-summarize',
      title: 'Review and summarize',
      description: 'Get a concise summary of effective agent design principles.',
      query: 'Review and summarize the key points of effective agent design',
      icon: FileText,
      action: 'run',
    },
    {
      id: 'build-workflow',
      title: 'Build a workflow',
      description: 'Open the visual workflow builder to orchestrate agents.',
      icon: GitBranch,
      action: 'navigate',
      path: '/workflows/builder',
    },
    {
      id: 'create-agent',
      title: 'Create a custom agent',
      description: 'Design and configure a new agent from scratch.',
      icon: Plus,
      action: 'navigate',
      path: '/builder',
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
      transition={{ duration: 0.4 }}
      className="obsidian-panel border border-outline/10 p-6"
    >
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Quick Start</h2>
          <p className="text-secondaryText text-sm mt-1">
            Jump in with a preset task or explore the builders.
          </p>
        </div>
        {collapsible && (
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="text-xs text-secondaryText hover:text-primaryText transition-colors"
          >
            {isCollapsed ? 'Expand' : 'Collapse'}
          </motion.button>
        )}
      </div>

      {!isCollapsed && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
          {presets.map((preset, idx) => (
            <motion.div
              key={preset.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: idx * 0.05 }}
              whileTap={{ scale: 0.98 }}
              whileHover={{ y: -4, boxShadow: '0 8px 30px rgba(0,229,255,0.08)' }}
              className="flex flex-col gap-3 p-4 bg-surface-highest rounded-xl border border-outline/10 hover:border-primary/30 transition-all group"
            >
              <motion.div
                whileHover={{ rotate: 5, scale: 1.05 }}
                className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center"
              >
                <preset.icon className="w-5 h-5 text-primary" />
              </motion.div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-primaryText">{preset.title}</h3>
                <p className="text-xs text-secondaryText mt-1 leading-relaxed">
                  {preset.description}
                </p>
              </div>
              <motion.button
                whileTap={{ scale: 0.95 }}
                onClick={() => handleAction(preset)}
                className="w-full mt-auto flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-surface-low border border-outline/10 text-xs font-medium text-primaryText hover:bg-primary/10 hover:border-primary/30 hover:text-primary transition-all"
              >
                {preset.action === 'run' ? (
                  <>
                    <Play className="w-3 h-3" /> Run
                  </>
                ) : (
                  <>
                    Open <ArrowRight className="w-3 h-3" />
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

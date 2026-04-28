import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { HelpCircle, X, Search } from 'lucide-react';
import { useLocation } from 'react-router-dom';

const HELP_ARTICLES = [
  { title: 'How to create an agent', content: 'Go to Agent Builder, select a template, customize identity and tools, then test and save.', routes: ['/builder'] },
  { title: 'How to build a workflow', content: 'Open Workflow Builder, drag nodes, connect edges, and click Execute.', routes: ['/workflows/builder', '/orchestrator'] },
  { title: 'Understanding task modes', content: 'Task: single execution. Workflow: predefined steps. Autonomous: self-replanning. Collaboration: parallel.', routes: ['/dashboard'] },
  { title: 'Tool binding', content: 'Connect Agent nodes to Tool nodes in Workflow Builder. Map parameters on the edge.', routes: ['/workflows/builder'] },
  { title: 'Managing API Keys', content: 'Go to Settings > API Keys to create and revoke keys for programmatic access.', routes: ['/settings/api-keys'] },
  { title: 'Using the Knowledge Base', content: 'Upload documents in the Knowledge Base to ground agent responses.', routes: ['/knowledge'] },
  { title: 'Chat with agents', content: 'Open Chat to have interactive conversations with your configured agents.', routes: ['/chat'] },
];

export const HelpWidget = () => {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const currentPath = location.pathname;

  const sortedArticles = [...HELP_ARTICLES].sort((a, b) => {
    const aRelevant = a.routes.some((r) => currentPath.startsWith(r)) ? 1 : 0;
    const bRelevant = b.routes.some((r) => currentPath.startsWith(r)) ? 1 : 0;
    return bRelevant - aRelevant;
  });

  const filtered = sortedArticles.filter(a => a.title.toLowerCase().includes(query.toLowerCase()) || a.content.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            className="mb-4 w-80 bg-surface-high border border-outline/20 rounded-xl shadow-2xl overflow-hidden"
          >
            <div className="p-4 border-b border-outline/10 flex items-center justify-between">
              <h3 className="font-semibold text-sm">Help</h3>
              <button onClick={() => setOpen(false)} className="text-secondaryText hover:text-primaryText"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-3">
              <div className="flex items-center gap-2 bg-surface-highest rounded-lg px-3 py-2 mb-3">
                <Search className="w-4 h-4 text-secondaryText" />
                <input className="bg-transparent text-sm w-full focus:outline-none text-primaryText" placeholder="Search help..." value={query} onChange={(e) => setQuery(e.target.value)} />
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {filtered.map((article) => {
                  const isRelevant = article.routes.some((r) => currentPath.startsWith(r));
                  return (
                    <motion.div
                      key={article.title}
                      whileHover={{ x: 2 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <details className="group">
                        <summary className={`text-sm font-medium cursor-pointer list-none flex items-center justify-between ${isRelevant ? 'text-primary' : 'text-primaryText'}`}>
                          <span className="flex items-center gap-2">
                            {article.title}
                            {isRelevant && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">Relevant</span>}
                          </span>
                          <span className="text-secondaryText text-xs group-open:rotate-180 transition-transform">▼</span>
                        </summary>
                        <p className="text-xs text-secondaryText mt-2 pl-2">{article.content}</p>
                      </details>
                    </motion.div>
                  );
                })}
                {filtered.length === 0 && (
                  <p className="text-xs text-secondaryText text-center py-2">No help articles found.</p>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <motion.button
        onClick={() => setOpen(!open)}
        whileTap={{ scale: 0.9 }}
        whileHover={{ scale: 1.1 }}
        className="w-12 h-12 rounded-full bg-primary text-black shadow-lg hover:bg-primary/90 transition-colors flex items-center justify-center"
      >
        {open ? <X className="w-5 h-5" /> : <HelpCircle className="w-5 h-5" />}
      </motion.button>
    </div>
  );
};

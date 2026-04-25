import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, BrainCircuit, BarChart3, Wrench, Settings, LogOut, Terminal, Waypoints, GitBranch, MessageSquare, BookOpen } from 'lucide-react';
import { motion, useScroll, useSpring } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import { HelpWidget } from './Onboarding/HelpWidget';
import { CursorGlow } from './CursorGlow';
import { layoutId, navItemInteractions, pageTransition } from '../lib/animations';

const Layout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { logout, user } = useAuth();
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'Agent Builder', path: '/builder', icon: BrainCircuit },
    { name: 'Chat', path: '/chat', icon: MessageSquare },
    { name: 'Workflow Orchestrator', path: '/orchestrator', icon: Waypoints },
    { name: 'Workflow Builder', path: '/workflows/builder', icon: GitBranch },
    { name: 'Analytics', path: '/monitor', icon: BarChart3 },
    { name: 'Knowledge Base', path: '/knowledge', icon: BookOpen },
    { name: 'Tool Registry', path: '/tools', icon: Wrench },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-background flex text-primaryText selection:bg-primary/30">
      {/* Sidebar */}
      <aside className="w-64 border-r border-outline/10 bg-surface-low flex flex-col justify-between py-6">
        <div>
          <div className="px-6 mb-10 flex items-center gap-2 cursor-pointer" onClick={() => navigate('/')}>
            <div className="w-8 h-8 rounded-md bg-primary/10 flex items-center justify-center">
              <Terminal className="w-4 h-4 text-primary" />
            </div>
            <span className="font-semibold tracking-tight text-lg">AgentOS</span>
          </div>

          <nav className="flex flex-col gap-1 px-4">
            {navItems.map((item) => {
              const isActive = location.pathname.startsWith(item.path);
              return (
                <motion.button
                  {...navItemInteractions}
                  key={item.name}
                  onClick={() => navigate(item.path)}
                  className={`flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-200 w-full text-left font-medium relative overflow-visible ${
                    isActive 
                      ? 'bg-surface-high text-primaryText' 
                      : 'text-secondaryText hover:bg-surface-highest hover:text-primaryText'
                  }`}
                >
                  {isActive && (
                    <motion.div
                      layoutId={layoutId}
                      className="absolute left-0 w-1 h-5 bg-primary rounded-r-full"
                      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                    />
                  )}
                  <item.icon className={`w-5 h-5 ${isActive ? 'text-primary' : ''}`} />
                  {item.name}
                </motion.button>
              );
            })}
          </nav>
        </div>

        <div className="px-4">
          <div className="flex items-center gap-3 px-4 py-2 mb-2 text-sm text-secondaryText">
            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-sm">{user?.email}</p>
            </div>
          </div>
          <motion.button
            {...navItemInteractions}
            onClick={() => { logout(); navigate('/login'); }}
            className="flex items-center gap-3 px-4 py-2 w-full text-left text-secondaryText hover:text-primaryText hover:bg-surface-highest transition-colors rounded-lg font-medium"
          >
            <LogOut className="w-5 h-5" />
            End Session
          </motion.button>
        </div>
      </aside>

      <CursorGlow />
      {/* Main Content Area */}
      <main className="flex-1 h-screen overflow-y-auto relative">
        <motion.div
          className="fixed top-0 left-64 right-0 h-0.5 bg-primary origin-left z-50"
          style={{ scaleX }}
        />
        <motion.div
          key={location.pathname}
          {...pageTransition}
          className="p-8 max-w-7xl mx-auto"
        >
          <Outlet />
        </motion.div>
        <HelpWidget />
      </main>
    </div>
  );
};

export default Layout;

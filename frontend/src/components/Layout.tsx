import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, BrainCircuit, BarChart3, Wrench, Settings, LogOut, Terminal, Waypoints, GitBranch, MessageSquare, BookOpen, Sun, Moon } from 'lucide-react';
import { motion, useScroll, useSpring } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { HelpWidget } from './Onboarding/HelpWidget';

import { navItemInteractions, pageTransition } from '../lib/animations';

const Layout = () => {
 const navigate = useNavigate();
 const location = useLocation();
  const { logout, user } = useAuth();
  const { theme, toggleTheme } = useTheme();
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
  <aside className="w-64 border-r-4 border-outline bg-primary flex flex-col justify-between py-6 z-40">
  <div>
   <div className="px-6 mb-10 flex items-center gap-3 cursor-pointer" onClick={() => navigate('/')}>
   <div className="w-12 h-12 border-4 border-outline bg-white flex items-center justify-center shadow-pixel">
    <Terminal className="w-7 h-7 text-primary" />
   </div>
   <span className="font-pixel text-lg tracking-tighter uppercase text-white">AgentOS</span>
   </div>

   <nav className="flex flex-col gap-3 px-4">
   {navItems.map((item) => {
    const isActive = location.pathname.startsWith(item.path);
    return (
    <motion.button
     {...navItemInteractions}
     key={item.name}
     onClick={() => navigate(item.path)}
     className={`flex items-center gap-3 px-4 py-3 w-full text-left font-retro text-xl relative overflow-visible border-4 ${
     isActive 
      ? 'bg-accent-yellow text-black border-outline shadow-pixel' 
      : 'text-white border-transparent hover:border-outline hover:bg-white/10 hover:text-white'
     }`}
    >
     <item.icon className={`w-5 h-5 ${isActive ? 'text-black' : 'text-white'}`} />
     {item.name}
    </motion.button>
    );
   })}
   </nav>
  </div>

   <div className="px-4">
    <motion.button
    {...navItemInteractions}
    onClick={toggleTheme}
    className="flex items-center gap-3 px-4 py-3 mb-4 w-full text-left text-white hover:text-white hover:bg-white/10 border-4 border-transparent hover:border-outline font-pixel text-[10px] uppercase"
    >
    {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
    </motion.button>
    <div className="flex items-center gap-3 px-4 py-3 mb-4 text-sm text-black border-4 border-outline bg-white shadow-pixel">
   <div className="w-8 h-8 border-4 border-outline bg-accent-pink flex items-center justify-center text-black font-pixel text-[10px]">
    {user?.email?.charAt(0).toUpperCase() || 'U'}
   </div>
   <div className="flex-1 overflow-hidden">
    <p className="truncate font-retro text-lg leading-none">{user?.email}</p>
   </div>
   </div>
   <motion.button
   {...navItemInteractions}
   onClick={() => { logout(); navigate('/login'); }}
   className="flex items-center gap-3 px-4 py-3 w-full text-left text-white hover:text-white hover:bg-white/10 border-4 border-transparent hover:border-outline font-pixel text-[10px] uppercase"
   >
   <LogOut className="w-5 h-5" />
   End Session
   </motion.button>
  </div>
  </aside>

  {/* Main Content Area */}
  <main className="flex-1 h-screen overflow-y-auto relative bg-background">
  <motion.div
   className="fixed top-0 left-64 right-0 h-1 bg-primary origin-left z-50 border-b-4 border-outline"
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

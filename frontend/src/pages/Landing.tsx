import { motion, type Variants } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Layers, Activity, BrainCircuit, ArrowRight } from 'lucide-react';

const Landing = () => {
  const navigate = useNavigate();

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { 
      opacity: 1,
      transition: { staggerChildren: 0.2 }
    }
  };

  const itemVariants: Variants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" as const } }
  };

  return (
    <div className="min-h-screen bg-background relative overflow-hidden flex flex-col">
      {/* Navbar */}
      <nav className="w-full flex justify-between items-center px-12 py-6 absolute top-0 z-50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
            <Layers className="w-4 h-4 text-primary" />
          </div>
          <span className="font-semibold text-lg tracking-tight">AgentOS</span>
        </div>
        <div className="flex items-center gap-6">
          <button 
            onClick={() => navigate('/login')}
            className="text-secondaryText hover:text-primaryText transition-colors text-sm font-medium"
          >
            Sign In
          </button>
          <button 
            onClick={() => navigate('/signup')}
            className="btn-primary flex items-center gap-2"
          >
            Get Started <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 mt-32">
        <motion.div 
          className="max-w-4xl w-full text-center"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <motion.div variants={itemVariants} className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface-high text-primaryText text-xs font-semibold tracking-widest mb-8 border border-outline/10 uppercase">
            <span className="w-2 h-2 rounded-full bg-primary shadow-glow-cyan animate-pulse"></span>
            The Digital Obsidian
          </motion.div>
          
          <motion.h1 
            variants={itemVariants}
            className="text-6xl md:text-7xl font-bold tracking-tighter leading-[1.1] mb-6"
          >
            The Operating System <br />
            <span className="text-secondaryText">for Intelligence.</span>
          </motion.h1>
          
          <motion.p 
            variants={itemVariants}
            className="text-lg md:text-xl text-secondaryText max-w-2xl mx-auto mb-12 font-light leading-relaxed"
          >
            Orchestrate complex multi-agent workflows with precision-engineered 
            sophistication. Turn isolated AI models into reliable, cohesive systems.
          </motion.p>
          
          <motion.div variants={itemVariants} className="flex justify-center gap-4">
            <button 
              onClick={() => navigate('/login')}
              className="btn-primary px-8 py-4 text-lg shadow-glow-cyan"
            >
              Initialize Workspace
            </button>
          </motion.div>
        </motion.div>

        {/* Feature Cards */}
        <motion.div 
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-6xl w-full mt-32 mb-24"
        >
          {features.map((feature, idx) => (
            <motion.div 
              key={idx}
              variants={itemVariants}
              whileHover={{ scale: 1.02 }}
              className="obsidian-glass p-8 rounded-2xl flex flex-col gap-4 group cursor-pointer"
            >
              <div className="w-12 h-12 rounded-xl bg-surface-highest flex items-center justify-center transition-colors group-hover:bg-primary/10">
                <feature.icon className="w-6 h-6 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mt-2">{feature.title}</h3>
              <p className="text-secondaryText leading-relaxed">
                {feature.description}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </main>
    </div>
  );
};

const features = [
  {
    icon: Layers,
    title: "Monolithic Structure",
    description: "Build robust Agentic workflows using our intentional, layered orchestration model. No fragile chains."
  },
  {
    icon: BrainCircuit,
    title: "Multi-Agent Logic",
    description: "Deploy Planners, Verifiers, and Executors seamlessly communicating via strict MCP protocols."
  },
  {
    icon: Activity,
    title: "Tonal Authority",
    description: "Deep observability and runtime tracking. Command your agents with full visibility into their operations."
  }
];

export default Landing;

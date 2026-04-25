import { motion, type Variants } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Layers, Activity, BrainCircuit, ArrowRight, Search, GitBranch, Zap, Play } from 'lucide-react';

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
        <motion.div
          className="flex items-center gap-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
            <Layers className="w-4 h-4 text-primary" />
          </div>
          <span className="font-semibold text-lg tracking-tight">AgentOS</span>
        </motion.div>
        <div className="flex items-center gap-6">
          <motion.button
            whileTap={{ scale: 0.96 }}
            whileHover={{ scale: 1.02 }}
            onClick={() => navigate('/login')}
            className="text-secondaryText hover:text-primaryText transition-colors text-sm font-medium"
          >
            Sign In
          </motion.button>
          <motion.button
            whileTap={{ scale: 0.96 }}
            whileHover={{ scale: 1.02 }}
            onClick={() => navigate('/signup')}
            className="btn-primary flex items-center gap-2"
          >
            Get Started <ArrowRight className="w-4 h-4" />
          </motion.button>
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
            <motion.button
              whileTap={{ scale: 0.96 }}
              whileHover={{ scale: 1.02 }}
              onClick={() => navigate('/login')}
              className="btn-primary px-8 py-4 text-lg shadow-glow-cyan"
            >
              Initialize Workspace
            </motion.button>
            <motion.button
              whileTap={{ scale: 0.96 }}
              whileHover={{ scale: 1.02, backgroundColor: 'rgba(53,52,54,0.5)' }}
              onClick={() => {
                const el = document.getElementById('demo-section');
                if (el) el.scrollIntoView({ behavior: 'smooth' });
              }}
              className="px-8 py-4 text-lg rounded-lg border border-outline/20 text-primaryText hover:bg-surface-highest transition-colors flex items-center gap-2"
            >
              <Play className="w-4 h-4" /> See Demo
            </motion.button>
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
              whileHover={{ scale: 1.02, y: -4, boxShadow: '0 8px 30px rgba(0,229,255,0.08)' }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
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

        {/* Demo Section */}
        <motion.div
          id="demo-section"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          className="max-w-6xl w-full mb-24 scroll-mt-24"
        >
          <div className="text-center mb-10">
            <h2 className="text-3xl font-bold tracking-tight mb-3">What You Can Build</h2>
            <p className="text-secondaryText max-w-xl mx-auto">
              Explore example agents and workflows you can create with AgentOS.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {demoAgents.map((agent, idx) => (
              <motion.div
                key={idx}
                variants={itemVariants}
                whileHover={{ scale: 1.02, y: -4, boxShadow: '0 8px 30px rgba(0,229,255,0.08)' }}
                transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                className="obsidian-glass p-6 rounded-2xl flex flex-col gap-4 group cursor-default border border-outline/10 hover:border-primary/30 transition-all"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <agent.icon className="w-5 h-5 text-primary" />
                  </div>
                  <h3 className="text-lg font-semibold">{agent.title}</h3>
                </div>
                <p className="text-secondaryText text-sm leading-relaxed">
                  {agent.description}
                </p>
                <div className="mt-auto flex flex-wrap gap-2">
                  {agent.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] uppercase tracking-wider font-semibold px-2 py-1 rounded bg-surface-highest text-secondaryText border border-outline/10"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
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

const demoAgents = [
  {
    icon: Search,
    title: "Research Agent",
    description: "Autonomously gathers information from multiple sources, synthesizes findings, and delivers structured summaries with citations.",
    tags: ["Autonomous", "Summarization", "Web"]
  },
  {
    icon: GitBranch,
    title: "Workflow Orchestrator",
    description: "Chains specialized agents into deterministic pipelines. Routes outputs between planners, verifiers, and executors with retry logic.",
    tags: ["Pipeline", "Multi-Agent", "Reliability"]
  },
  {
    icon: Zap,
    title: "Guardian Agent",
    description: "Validates outputs against policies, detects hallucinations, and enforces safety constraints before results reach users.",
    tags: ["Safety", "Validation", "Policy"]
  }
];

export default Landing;

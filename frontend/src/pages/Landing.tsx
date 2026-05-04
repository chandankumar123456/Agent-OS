import { motion, type Variants } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Layers, Activity, BrainCircuit, ArrowRight, Search, GitBranch, Zap, Play } from 'lucide-react';
import { buttonTap, cardInteractions } from '../lib/animations';

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
 <div className="min-h-screen bg-surface-lowest relative overflow-hidden flex flex-col font-retro">
 {/* Navbar */}
 <nav className="w-full flex justify-between items-center px-8 py-6 absolute top-0 z-50">
 <motion.div
 className="flex items-center gap-2 cursor-pointer"
 initial={{ opacity: 0, x: -20 }}
 animate={{ opacity: 1, x: 0 }}
 onClick={() => navigate('/')}
 >
 <div className="w-10 h-10 border-4 border-outline bg-primary flex items-center justify-center shadow-pixel">
 <Layers className="w-6 h-6 text-white" />
 </div>
 <span className="font-pixel text-sm tracking-tighter uppercase">AgentOS</span>
 </motion.div>
 <div className="flex items-center gap-6">
 <motion.button
 {...buttonTap}
 onClick={() => navigate('/login')}
 className="text-primaryText hover:underline text-lg font-retro"
 >
 [ Sign In ]
 </motion.button>
 <motion.button
 {...buttonTap}
 onClick={() => navigate('/signup')}
 className="btn-primary flex items-center gap-2"
 >
 Get Started <ArrowRight className="w-4 h-4" />
 </motion.button>
 </div>
 </nav>

 {/* Hero Section */}
 <main className="flex-1 flex flex-col items-center justify-center px-6 mt-8">
 <motion.div 
 className="max-w-4xl w-full text-center"
 variants={containerVariants}
 initial="hidden"
 animate="visible"
 >
 <motion.div variants={itemVariants} className="inline-flex items-center gap-2 px-4 py-1 border-4 border-outline bg-accent-yellow text-primaryText font-pixel text-[10px] tracking-widest mb-8 shadow-pixel uppercase">
 <span className="w-2 h-2 bg-primary border border-outline animate-pulse"></span>
 The Digital Pixel
 </motion.div>
 
 <motion.h1 
 variants={itemVariants}
 className="text-5xl md:text-6xl font-pixel tracking-tighter leading-[1.1] mb-8 uppercase"
 >
 The Operating System <br />
 <span className="text-primary">for Intelligence.</span>
 </motion.h1>
 
 <motion.p 
 variants={itemVariants}
 className="text-xl md:text-2xl text-secondaryText max-w-2xl mx-auto mb-8 font-retro leading-relaxed"
 >
 Orchestrate complex multi-agent workflows with precision-engineered 
 sophistication. Turn isolated AI models into reliable, cohesive systems.
 </motion.p>
 
 <motion.div variants={itemVariants} className="flex justify-center gap-6">
 <motion.button
 {...buttonTap}
 onClick={() => navigate('/login')}
 className="btn-primary px-8 py-6 text-xs"
 >
 Initialize Workspace
 </motion.button>
 <motion.button
 {...buttonTap}
 onClick={() => {
 const el = document.getElementById('demo-section');
 if (el) el.scrollIntoView({ behavior: 'smooth' });
 }}
 className="btn-secondary px-8 py-6 text-xs flex items-center gap-2"
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
 className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl w-full mt-8 mb-8"
 >
 {features.map((feature, idx) => (
 <motion.div
 key={idx}
 variants={itemVariants}
 {...cardInteractions}
 className="pixel-card p-8 flex flex-col gap-4 group cursor-pointer"
 >
 <div className="w-14 h-14 border-4 border-outline bg-surface-high flex items-center justify-center group-hover:bg-primary/20">
 <feature.icon className="w-7 h-7 text-primary" />
 </div>
 <h3 className="text-xl font-pixel uppercase mt-2">{feature.title}</h3>
 <p className="text-secondaryText leading-relaxed text-lg font-retro">
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
 className="max-w-6xl w-full mb-8 scroll-mt-8"
 >
 <div className="text-center mb-8">
 <h2 className="text-3xl font-pixel uppercase mb-4">What You Can Build</h2>
 <p className="text-secondaryText max-w-xl mx-auto font-retro text-xl">
 Explore example agents and workflows you can create with AgentOS.
 </p>
 </div>
 <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
 {demoAgents.map((agent, idx) => (
 <motion.div
 key={idx}
 variants={itemVariants}
 {...cardInteractions}
 className="pixel-card p-6 flex flex-col gap-4 group cursor-default"
 >
 <div className="flex items-center gap-4">
 <div className="w-12 h-12 border-4 border-outline bg-accent-mint/30 flex items-center justify-center">
 <agent.icon className="w-6 h-6 text-primaryText" />
 </div>
 <h3 className="text-lg font-pixel uppercase">{agent.title}</h3>
 </div>
 <p className="text-secondaryText text-lg leading-relaxed font-retro">
 {agent.description}
 </p>
 <div className="mt-auto flex flex-wrap gap-2">
 {agent.tags.map((tag) => (
 <span
 key={tag}
 className="pixel-badge bg-surface-highest text-secondaryText"
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

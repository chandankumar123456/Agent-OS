import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bot, Save, Wrench, Database, Loader2, Trash2, Edit2, Check, X, MessageSquare, Play, FileText } from 'lucide-react';
import { buttonTap, cardInteractions } from '../lib/animations';
import { apiClient } from '../api/client';
import type { AgentInfo } from '../api/client';

const agentTemplates = [
 {
  id: 'researcher',
  name: 'Research Agent',
  role: 'researcher',
  system_prompt: 'You are a research specialist...',
  model: 'gpt-4o',
  temperature: 0.3,
  tools: ['web_search', 'text_processor'],
 },
 {
  id: 'coder',
  name: 'Code Agent',
  role: 'coder',
  system_prompt: 'You are a senior software engineer...',
  model: 'gpt-4o',
  temperature: 0.1,
  tools: ['shell'],
 },
 {
  id: 'reviewer',
  name: 'Review Agent',
  role: 'reviewer',
  system_prompt: 'You are a critical reviewer...',
  model: 'gpt-4o-mini',
  temperature: 0.2,
  tools: ['text_processor'],
 },
 {
  id: 'creative',
  name: 'Creative Agent',
  role: 'creative',
  system_prompt: 'You are a creative writer...',
  model: 'gpt-4o',
  temperature: 0.9,
  tools: ['text_processor'],
 },
];

const AgentBuilder = () => {
 const [agents, setAgents] = useState<AgentInfo[]>([]);
 const [tools, setTools] = useState<Array<{ name: string; description: string; type: string }>>([]);
 const [loading, setLoading] = useState(true);
 const [actionError, setActionError] = useState('');

 // Form state
 const [name, setName] = useState('');
 const [prompt, setPrompt] = useState('');
 const [model, setModel] = useState('gpt-4o');
 const [temperature, setTemperature] = useState(0.7);
 const [maxTokens, setMaxTokens] = useState(2048);
 const [assignedTools, setAssignedTools] = useState<string[]>([]);
 const [editingAgentId, setEditingAgentId] = useState<string | null>(null);

 // Test panel state
 const [testPrompt, setTestPrompt] = useState('');
 const [testResult, setTestResult] = useState('');
 const [testLoading, setTestLoading] = useState(false);
 const [testError, setTestError] = useState('');

 const refresh = async () => {
  setActionError('');
  try {
   const [agentData, toolData] = await Promise.all([apiClient.listAgents(), apiClient.getTools()]);
   setAgents(agentData);
   setTools(toolData.map((tool) => ({ name: tool.name, description: tool.description, type: tool.type || 'Other' })));
  } catch (error) {
   setActionError(error instanceof Error ? error.message : 'Failed to load agents');
  }
 };

 const resetForm = () => {
  setName('');
  setPrompt('');
  setModel('gpt-4o');
  setTemperature(0.7);
  setMaxTokens(2048);
  setAssignedTools([]);
  setEditingAgentId(null);
 };

 const applyTemplate = (template: typeof agentTemplates[0]) => {
  setName(template.name);
  setPrompt(template.system_prompt);
  setModel(template.model);
  setTemperature(template.temperature);
  setAssignedTools(template.tools);
  setMaxTokens(2048);
  setEditingAgentId(null);
  setActionError('');
 };

 const createAgent = async () => {
  if (!name.trim()) return;
  setActionError('');
  try {
   await apiClient.createAgent({
    name: name.trim(),
    role: 'custom',
    system_prompt: prompt.trim() || undefined,
    model,
    temperature,
    max_tokens: maxTokens,
    tools: assignedTools,
   });
   resetForm();
   await refresh();
  } catch (error) {
   setActionError(error instanceof Error ? error.message : 'Failed to create agent');
  }
 };

 const updateAgent = async () => {
  if (!editingAgentId || !name.trim()) return;
  setActionError('');
  try {
   await apiClient.updateAgent(editingAgentId, {
    name: name.trim(),
    role: 'custom',
    system_prompt: prompt.trim() || undefined,
    model,
    temperature,
    max_tokens: maxTokens,
    tools: assignedTools,
   });
   resetForm();
   await refresh();
  } catch (error) {
   setActionError(error instanceof Error ? error.message : 'Failed to update agent');
  }
 };

 const deleteAgent = async (agentId: string) => {
  if (!confirm('Are you sure you want to delete this agent?')) return;
  setActionError('');
  try {
   await apiClient.deleteAgent(agentId);
   await refresh();
  } catch (error) {
   setActionError(error instanceof Error ? error.message : 'Failed to delete agent');
  }
 };

 const startEdit = (agent: AgentInfo) => {
  setEditingAgentId(agent.agent_id);
  setName(agent.name);
  setPrompt(agent.system_prompt || '');
  setModel(agent.model || 'gpt-4o');
  setTemperature(agent.temperature || 0.7);
  setMaxTokens(agent.max_tokens || 2048);
  setAssignedTools(agent.tools || []);
 };

 const toggleTool = (toolName: string) => {
  setAssignedTools((prev) =>
   prev.includes(toolName) ? prev.filter((t) => t !== toolName) : [...prev, toolName]
  );
 };

 const runTest = async () => {
  if (!testPrompt.trim()) return;
  setTestLoading(true);
  setTestError('');
  setTestResult('');
  try {
   const { task_id } = await apiClient.createTask({
    query: testPrompt,
    mode: 'task',
    config: {},
   });
   const task = await apiClient.pollTaskStatus(task_id, undefined, 2000, 150);
   if (task.status === 'completed') {
    setTestResult(typeof task.result === 'string' ? task.result : JSON.stringify(task.result, null, 2));
   } else if (task.status === 'failed') {
    setTestError(task.error?.message || 'Task failed');
   } else {
    setTestError('Task did not complete in time');
   }
  } catch (err) {
   setTestError(err instanceof Error ? err.message : 'Test failed');
  } finally {
   setTestLoading(false);
  }
 };

 useEffect(() => {
  refresh().finally(() => setLoading(false));
 }, []);

 const toolsByCategory = tools.reduce((acc, tool) => {
  const category = tool.type || 'Other';
  if (!acc[category]) acc[category] = [];
  acc[category].push(tool);
  return acc;
 }, {} as Record<string, typeof tools>);

 const ToolRow = ({ tool }: { tool: typeof tools[0] }) => {
  const isSelected = assignedTools.includes(tool.name);
  return (
  <div className={`relative flex justify-between items-center p-4 border-4 ${isSelected ? 'border-primary bg-primary/5' : 'border-outline/10 bg-white'} hover:border-primary group transition-none`}>
   <div className="flex items-center gap-4">
    <div className={`w-10 h-10 border-4 border-outline ${isSelected ? 'bg-primary' : 'bg-white'} flex items-center justify-center shadow-pixel-sm transition-none`}>
     <Database className={`w-5 h-5 ${isSelected ? 'text-white' : 'text-primary'}`} />
    </div>
    <div>
     <span className="font-pixel text-[10px] uppercase text-black">{tool.name}</span>
     <p className="text-sm font-retro text-secondaryText uppercase opacity-60 leading-none mt-1 line-clamp-1">{tool.description}</p>
    </div>
   </div>
   <motion.button
    {...buttonTap}
    onClick={() => toggleTool(tool.name)}
    className={`w-12 h-8 border-4 border-outline p-1 ${isSelected ? 'bg-secondary' : 'bg-white'}`}
   >
    <div className={`w-4 h-full border-4 border-outline bg-white ${isSelected ? 'translate-x-5' : 'translate-x-0'} transition-transform duration-75`} />
   </motion.button>
  </div>
  );
 };

 return (
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10 h-full pb-8 max-w-[1600px] mx-auto px-6">
  {actionError && (
   <div className="p-4 border-4 border-[#FF4B4B] bg-[#FF4B4B]/10 font-retro text-2xl text-[#FF4B4B] uppercase">
    !! KERNEL_ERROR: {actionError}
   </div>
  )}

  <div className="flex justify-between items-end">
   <div>
    <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Agent Foundry</h1>
    <p className="text-xl font-retro uppercase text-secondaryText opacity-60">Architecting neural operators and capability matrices.</p>
   </div>
   <div className="flex gap-4">
    {editingAgentId && (
     <motion.button className="btn-ghost flex items-center gap-3 py-4 px-6" onClick={resetForm} {...buttonTap}>
      <X className="w-5 h-5" /> [ ABORT_EDIT ]
     </motion.button>
    )}
    <motion.button
     className="btn-primary flex items-center gap-3 py-4 px-8"
     onClick={editingAgentId ? updateAgent : createAgent}
     {...buttonTap}
    >
     {editingAgentId ? <Check className="w-5 h-5" /> : <Save className="w-5 h-5" />}
     {editingAgentId ? '[ UPDATE_MANIFEST ]' : '[ INITIALIZE_OPERATOR ]'}
    </motion.button>
   </div>
  </div>

  {loading ? (
   <div className="flex items-center gap-4 text-secondaryText py-12 font-pixel text-xs">
    <Loader2 className="w-6 h-6 animate-spin" /> LOADING_FOUNDRY_STATE...
   </div>
  ) : (
   <div className="flex flex-col lg:flex-row gap-10 h-full min-h-[800px]">
    <div className="flex-1 flex flex-col gap-10">
     {/* Templates */}
     <div className="pixel-panel p-8 bg-white">
      <h2 className="text-[10px] font-pixel uppercase tracking-tight mb-8 flex items-center gap-3">
       <FileText className="w-5 h-5 text-primary" /> Blueprint_Registry
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
       {agentTemplates.map((template) => (
        <motion.button
         {...buttonTap}
         key={template.id}
         onClick={() => applyTemplate(template)}
         className="p-4 border-4 border-outline bg-background hover:bg-white hover:border-primary text-left shadow-pixel-sm group"
        >
         <div className="font-pixel text-[10px] uppercase text-primary group-hover:text-primary ">{template.name}</div>
         <div className="font-retro text-lg uppercase text-secondaryText mt-2 opacity-60">{template.role}</div>
        </motion.button>
       ))}
      </div>
     </div>

     <div className="pixel-panel p-8 bg-white">
      <h2 className="text-[10px] font-pixel uppercase tracking-tight mb-8 flex items-center gap-3">
       <Bot className="w-5 h-5 text-primary" /> Core_Manifest
      </h2>
      <div className="space-y-8">
       <div>
        <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Operator_Alias</label>
        <input
         type="text"
         className="w-full pixel-input py-4 text-2xl"
         placeholder="E.G. DATA_SYNTHESIZER_01"
         value={name}
         onChange={(e) => setName(e.target.value)}
        />
       </div>
       <div>
        <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">System_Directive_Protocol</label>
        <textarea
         className="w-full pixel-input min-h-[160px] py-4 text-2xl resize-none"
         placeholder="DEFINE OPERATOR BEHAVIORAL PARAMETERS..."
         value={prompt}
         onChange={(e) => setPrompt(e.target.value)}
        />
       </div>
       <div className="grid grid-cols-3 gap-6">
        <div>
         <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Kernel_UID</label>
         <input type="text" className="w-full pixel-input py-4 text-2xl" value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
        <div>
         <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Entropy_MOD</label>
         <input
          type="number"
          step="0.1"
          min="0"
          max="2"
          className="w-full pixel-input py-4 text-2xl"
          value={temperature}
          onChange={(e) => setTemperature(parseFloat(e.target.value))}
         />
        </div>
        <div>
         <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Buffer_Limit</label>
         <input
          type="number"
          step="256"
          min="256"
          max="8192"
          className="w-full pixel-input py-4 text-2xl"
          value={maxTokens}
          onChange={(e) => setMaxTokens(parseInt(e.target.value))}
         />
        </div>
       </div>
      </div>
     </div>

     <div className="pixel-panel p-8 bg-white flex-1">
      <h2 className="text-[10px] font-pixel uppercase tracking-tight mb-8 flex items-center gap-3">
       <Wrench className="w-5 h-5 text-primary" /> Capability_Matrix
      </h2>
      <div className="space-y-10">
       {Object.entries(toolsByCategory).map(([category, categoryTools]) => (
        <div key={category}>
         <label className="block text-[10px] font-pixel uppercase text-black mb-6 flex items-center gap-3">
          <div className="w-3 h-3 bg-primary" /> {category}
         </label>
         <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {categoryTools.map((tool) => (
           <ToolRow key={tool.name} tool={tool} />
          ))}
         </div>
        </div>
       ))}
       {tools.length === 0 && (
        <p className="font-retro text-2xl uppercase text-secondaryText opacity-50 text-center py-12">NULL_TOOLS: NO CAPABILITIES FOUND.</p>
       )}
      </div>
     </div>

     {/* Test Agent Panel */}
     <div className="pixel-panel p-8 bg-accent-yellow/5">
      <h2 className="text-[10px] font-pixel uppercase tracking-tight mb-8 flex items-center gap-3">
       <MessageSquare className="w-5 h-5 text-primary" /> Diagnostic_Link
      </h2>
      <div className="space-y-8">
       <div>
        <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Input_Command</label>
        <textarea
         className="w-full pixel-input min-h-[120px] py-4 text-2xl resize-none bg-white"
         placeholder="ENTER TEST_DATA COMMAND..."
         value={testPrompt}
         onChange={(e) => setTestPrompt(e.target.value)}
        />
       </div>
       <motion.button
        className="btn-primary flex items-center gap-3 py-4 px-10 disabled:opacity-50"
        onClick={runTest}
        disabled={testLoading || !testPrompt.trim()}
        {...buttonTap}
       >
        {testLoading ? <Loader2 className="w-6 h-6 animate-spin" /> : <Play className="w-6 h-6" />}
        {testLoading ? '[ EXECUTING... ]' : '[ RUN_DIAGNOSTIC ]'}
       </motion.button>
       {testError && (
        <div className="p-6 border-4 border-[#FF4B4B] bg-[#FF4B4B]/10 font-retro text-2xl text-[#FF4B4B] uppercase">
         !! ERROR: {testError}
        </div>
       )}
       {testResult && (
        <div className="p-8 border-4 border-outline bg-white shadow-pixel-sm">
         <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-6">Diagnostic_Output</label>
         <pre className="text-2xl font-retro uppercase whitespace-pre-wrap break-words leading-tight">{testResult}</pre>
        </div>
       )}
      </div>
     </div>
    </div>

    <div className="w-full lg:w-1/3 pixel-panel p-0 flex flex-col bg-background overflow-hidden hidden lg:flex">
     <div className="p-6 border-b-4 border-outline bg-white">
      <h2 className="text-[10px] font-pixel uppercase tracking-tight flex items-center gap-3">
       <Database className="w-5 h-5 text-primary" /> Active_Operators
      </h2>
     </div>
     <div className="flex-1 p-6 flex flex-col gap-8 overflow-y-auto">
      <AnimatePresence mode="popLayout">
       {agents.map((agent) => (
        <motion.div
         key={agent.agent_id}
         layout
         initial={{ opacity: 0, x: 20 }}
         animate={{ opacity: 1, x: 0 }}
         exit={{ opacity: 0, x: -20 }}
         {...cardInteractions}
         className="pixel-card bg-white flex flex-col gap-6"
        >
         <div className="flex justify-between items-start">
          <div className="flex flex-col gap-2">
           <span className="font-pixel text-xs uppercase text-primary leading-none">{agent.name}</span>
           <span className="font-retro text-lg uppercase text-secondaryText opacity-60">{agent.role}</span>
          </div>
          <div className="flex gap-3">
           <motion.button onClick={() => startEdit(agent)} {...buttonTap} className="p-2 border-4 border-outline bg-background hover:bg-primary/10 text-primary">
            <Edit2 className="w-5 h-5" />
           </motion.button>
           <motion.button onClick={() => deleteAgent(agent.agent_id)} {...buttonTap} className="p-2 border-4 border-outline bg-background hover:bg-[#FF4B4B]/10 text-[#FF4B4B]">
            <Trash2 className="w-5 h-5" />
           </motion.button>
          </div>
         </div>
         <p className="text-xl font-retro uppercase text-secondaryText leading-tight line-clamp-3">{agent.system_prompt}</p>
         {agent.tools && agent.tools.length > 0 && (
          <div className="flex flex-wrap gap-3 mt-2">
           {agent.tools.map((t) => (
            <span key={t} className="text-[8px] font-pixel px-3 py-2 border-4 border-outline bg-accent-mint/20 text-black uppercase">
             {t}
            </span>
           ))}
          </div>
         )}
        </motion.div>
       ))}
      </AnimatePresence>
     </div>
    </div>
   </div>
  )}
  </motion.div>
 );
};

export default AgentBuilder;

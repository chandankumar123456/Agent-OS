import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bot,
  Brain,
  Wrench,
  Send,
  Loader2,
  Sparkles,
  Search,
  Terminal,
  PenTool,
  Save,
  Check,
  X,
  MessageSquare,
  Trash2,
  Cpu,
  RotateCcw,
  SlidersHorizontal,
  LayoutTemplate,
} from 'lucide-react';
import { apiClient } from '../api/client';
import type { AgentInfo } from '../api/client';

interface AgentConfigV2Form {
  agent_id: string;
  name: string;
  role: string;
  goal: string;
  backstory: string;
  model: string;
  temperature: number;
  max_tokens: number;
  reasoning: boolean;
  max_reasoning_attempts: number;
  tools: string[];
  allow_delegation: boolean;
  memory_enabled: boolean;
  knowledge_sources: string[];
  max_iter: number;
  max_execution_time: number;
  max_retry_limit: number;
  system_template: string;
  prompt_template: string;
  response_template: string;
}

// TODO: Integrate model selector fetching from /providers/models
// TODO: Integrate knowledge source selector fetching from /knowledge

const DEFAULT_CONFIG: AgentConfigV2Form = {
  agent_id: '',
  name: '',
  role: '',
  goal: '',
  backstory: '',
  model: 'gpt-4o',
  temperature: 0.7,
  max_tokens: 2048,
  reasoning: false,
  max_reasoning_attempts: 3,
  tools: [],
  allow_delegation: false,
  memory_enabled: true,
  knowledge_sources: [],
  max_iter: 20,
  max_execution_time: 300,
  max_retry_limit: 2,
  system_template: '',
  prompt_template: '',
  response_template: '',
};

const MOCK_TOOLS = [
  { name: 'web_search', description: 'Search the web for real-time information and sources.' },
  { name: 'text_processor', description: 'Summarize, rewrite, classify, and analyze text.' },
  { name: 'calculator', description: 'Evaluate mathematical expressions and logic.' },
  { name: 'shell', description: 'Execute safe shell commands in a sandboxed environment.' },
];

const MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'gpt-4-turbo',
  'claude-3-5-sonnet',
  'claude-3-haiku',
];

const TEMPLATES = [
  {
    id: 'researcher',
    name: 'Research Agent',
    description: 'Deep research with web search and text analysis.',
    icon: Search,
    config: {
      name: 'Research Agent',
      role: 'researcher',
      goal: 'Uncover cutting-edge developments in any topic with rigorous sourcing.',
      backstory: "You're a seasoned researcher with a knack for uncovering the latest developments across science, technology, and culture.",
      model: 'gpt-4o',
      temperature: 0.3,
      tools: ['web_search', 'text_processor'],
    } as Partial<AgentConfigV2Form>,
  },
  {
    id: 'coder',
    name: 'Code Agent',
    description: 'Write, review, and debug code efficiently.',
    icon: Terminal,
    config: {
      name: 'Code Agent',
      role: 'coder',
      goal: 'Write clean, efficient, and well-tested code across multiple languages.',
      backstory: 'Expert software engineer with 10 years of experience in distributed systems and developer tooling.',
      model: 'gpt-4o',
      temperature: 0.1,
      tools: ['shell'],
    } as Partial<AgentConfigV2Form>,
  },
  {
    id: 'creative',
    name: 'Creative Writer',
    description: 'Create compelling stories, copy, and creative content.',
    icon: PenTool,
    config: {
      name: 'Creative Writer',
      role: 'creative',
      goal: 'Create compelling creative content that captivates audiences.',
      backstory: 'Award-winning creative writer with a unique voice and deep understanding of narrative structure.',
      model: 'gpt-4o',
      temperature: 0.9,
      tools: ['text_processor'],
    } as Partial<AgentConfigV2Form>,
  },
  {
    id: 'custom',
    name: 'Custom',
    description: 'Start from scratch and build your own agent.',
    icon: Sparkles,
    config: {
      name: '',
      role: '',
      goal: '',
      backstory: '',
      model: 'gpt-4o',
      temperature: 0.7,
      tools: [],
    } as Partial<AgentConfigV2Form>,
  },
];

const TABS = [
  { id: 'identity', label: 'Identity', icon: Bot },
  { id: 'brain', label: 'Brain', icon: Brain },
  { id: 'tools', label: 'Tools', icon: Wrench },
  { id: 'advanced', label: 'Advanced', icon: SlidersHorizontal },
  { id: 'templates', label: 'Templates', icon: LayoutTemplate },
];

interface ChatMessageLocal {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  typing?: boolean;
}

const generateAgentId = () => `agent_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

export default function AgentBuilderV2() {
  const [config, setConfig] = useState<AgentConfigV2Form>({ ...DEFAULT_CONFIG });
  const [activeTab, setActiveTab] = useState('identity');
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [savedAgents, setSavedAgents] = useState<AgentInfo[]>([]);
  const [availableTools, setAvailableTools] = useState<Array<{ name: string; description: string }>>(MOCK_TOOLS);
  const [availableModels, setAvailableModels] = useState<string[]>(MODELS);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessageLocal[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load saved agents, tools, and models from API
  useEffect(() => {
    apiClient.listAgents().then((agents) => setSavedAgents(agents)).catch(() => {});
    apiClient.getToolsV2()
      .then((tools) => setAvailableTools(tools.map((t) => ({ name: t.tool_id, description: t.description }))))
      .catch(() => setAvailableTools(MOCK_TOOLS));
    apiClient.getModels()
      .then((modelMap) => {
        const allModels = Object.values(modelMap).flat();
        setAvailableModels(allModels.length > 0 ? allModels : MODELS);
      })
      .catch(() => setAvailableModels(MODELS));
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isTyping]);

  const updateField = <K extends keyof AgentConfigV2Form>(field: K, value: AgentConfigV2Form[K]) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
    setSaveSuccess(false);
  };

  const applyTemplate = (templateId: string) => {
    const template = TEMPLATES.find((t) => t.id === templateId);
    if (!template) return;
    setSelectedTemplate(templateId);
    setConfig((prev) => ({
      ...prev,
      ...template.config,
      agent_id: prev.agent_id || generateAgentId(),
    }));
    setSaveSuccess(false);
  };

  const toggleTool = (toolName: string) => {
    setConfig((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolName)
        ? prev.tools.filter((t) => t !== toolName)
        : [...prev.tools, toolName],
    }));
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    if (!config.name.trim()) {
      setSaveError('Agent name is required');
      return;
    }
    setSaveError('');
    setIsSaving(true);
    try {
      const payload = {
        agent_id: config.agent_id || generateAgentId(),
        name: config.name.trim(),
        role: config.role || 'custom',
        goal: config.goal,
        backstory: config.backstory,
        model: config.model,
        temperature: config.temperature,
        max_tokens: config.max_tokens,
        reasoning: config.reasoning,
        max_reasoning_attempts: config.max_reasoning_attempts,
        tools: config.tools.map((t) => ({ tool_name: t })),
        allow_delegation: config.allow_delegation,
        memory_enabled: config.memory_enabled,
        knowledge_sources: config.knowledge_sources,
        max_iter: config.max_iter,
        max_execution_time: config.max_execution_time,
        max_retry_limit: config.max_retry_limit,
        system_template: config.system_template || null,
        prompt_template: config.prompt_template || null,
        response_template: config.response_template || null,
      };
      await apiClient.createAgentV2(payload);
      setSaveSuccess(true);
      const agents = await apiClient.listAgents();
      setSavedAgents(agents);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save agent');
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestSend = useCallback(async () => {
    if (!chatInput.trim() || isTyping) return;
    const userMsg: ChatMessageLocal = {
      id: `u_${Date.now()}`,
      role: 'user',
      content: chatInput.trim(),
    };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput('');
    setIsTyping(true);

    // Mock response after 1s
    setTimeout(() => {
      const responses = [
        `I've analyzed your request as **${config.name || 'Agent'}**. Based on my configuration (model: ${config.model}, temp: ${config.temperature}), here's what I found:\n\nThis is a simulated response for testing purposes. In production, this would stream from the LangGraph executor.`,
        `Hello! I'm ${config.name || 'your agent'}. My role is *${config.role || 'assistant'}* and I'm ready to help.\n\nThis is a mock echo response to demonstrate the chat interface.`,
        `Understood. With ${config.tools.length} tool(s) enabled and reasoning ${config.reasoning ? 'on' : 'off'}, I would proceed to handle your query.\n\n> This is a test response from the composition studio.`,
      ];
      const response = responses[Math.floor(Math.random() * responses.length)];
      setChatMessages((prev) => [
        ...prev,
        { id: `a_${Date.now()}`, role: 'assistant', content: response },
      ]);
      setIsTyping(false);
    }, 1000);
  }, [chatInput, isTyping, config]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleTestSend();
    }
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'identity':
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                Role
              </label>
              <input
                type="text"
                className="w-full obsidian-input"
                placeholder="e.g. Senior Research Analyst"
                value={config.role}
                onChange={(e) => updateField('role', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                Goal
              </label>
              <textarea
                className="w-full obsidian-input min-h-[100px] resize-none"
                placeholder="What is the primary objective this agent should achieve?"
                value={config.goal}
                onChange={(e) => updateField('goal', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                Backstory
              </label>
              <textarea
                className="w-full obsidian-input min-h-[140px] resize-none"
                placeholder="Give the agent a rich backstory to shape its personality and perspective..."
                value={config.backstory}
                onChange={(e) => updateField('backstory', e.target.value)}
              />
            </div>
          </div>
        );
      case 'brain':
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                Model
              </label>
              <select
                className="w-full obsidian-input"
                value={config.model}
                onChange={(e) => updateField('model', e.target.value)}
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText">
                  Temperature
                </label>
                <span className="text-xs text-primary font-mono">{config.temperature.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={config.temperature}
                onChange={(e) => updateField('temperature', parseFloat(e.target.value))}
                className="w-full accent-primary"
              />
              <div className="flex justify-between text-[10px] text-secondaryText mt-1">
                <span>Precise</span>
                <span>Creative</span>
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                Max Tokens
              </label>
              <input
                type="number"
                min={256}
                max={16384}
                step={256}
                className="w-full obsidian-input"
                value={config.max_tokens}
                onChange={(e) => updateField('max_tokens', parseInt(e.target.value) || 0)}
              />
            </div>
            <div className="flex items-center justify-between p-4 rounded-lg bg-surface-highest border border-outline/10">
              <div className="flex items-center gap-3">
                <Brain className="w-5 h-5 text-primary" />
                <div>
                  <div className="text-sm font-medium">Reasoning</div>
                  <div className="text-xs text-secondaryText">Enable step-by-step reasoning before responding</div>
                </div>
              </div>
              <button
                onClick={() => updateField('reasoning', !config.reasoning)}
                className={`relative w-11 h-6 rounded-full transition-colors ${config.reasoning ? 'bg-primary' : 'bg-surface-highest border border-outline/20'}`}
              >
                <motion.span
                  layout
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-background transition-transform ${config.reasoning ? 'translate-x-5' : ''}`}
                />
              </button>
            </div>
            {config.reasoning && (
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                  Max Reasoning Attempts
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  className="w-full obsidian-input"
                  value={config.max_reasoning_attempts}
                  onChange={(e) => updateField('max_reasoning_attempts', parseInt(e.target.value) || 1)}
                />
              </div>
            )}
          </div>
        );
      case 'tools':
        return (
          <div className="space-y-4">
            {availableTools.map((tool) => {
              const checked = config.tools.includes(tool.name);
              return (
                <motion.div
                  key={tool.name}
                  onClick={() => toggleTool(tool.name)}
                  whileTap={{ scale: 0.99 }}
                  className={`flex items-start gap-4 p-4 rounded-xl border cursor-pointer transition-all ${
                    checked
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-outline/10 bg-surface-highest hover:border-outline/30'
                  }`}
                >
                  <div
                    className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 mt-0.5 ${
                      checked ? 'bg-primary border-primary' : 'border-outline/30'
                    }`}
                  >
                    {checked && <Check className="w-3.5 h-3.5 text-background" />}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Wrench className="w-4 h-4 text-primary" />
                      <span className="text-sm font-medium capitalize">{tool.name.replace('_', ' ')}</span>
                    </div>
                    <p className="text-xs text-secondaryText mt-1">{tool.description}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        );
      case 'advanced':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                  Max Iterations
                </label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  className="w-full obsidian-input"
                  value={config.max_iter}
                  onChange={(e) => updateField('max_iter', parseInt(e.target.value) || 1)}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                  Max Exec Time (s)
                </label>
                <input
                  type="number"
                  min={10}
                  max={3600}
                  className="w-full obsidian-input"
                  value={config.max_execution_time}
                  onChange={(e) => updateField('max_execution_time', parseInt(e.target.value) || 10)}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                  Max Retries
                </label>
                <input
                  type="number"
                  min={0}
                  max={10}
                  className="w-full obsidian-input"
                  value={config.max_retry_limit}
                  onChange={(e) => updateField('max_retry_limit', parseInt(e.target.value) || 0)}
                />
              </div>
            </div>
            <div className="flex items-center justify-between p-4 rounded-lg bg-surface-highest border border-outline/10">
              <div className="flex items-center gap-3">
                <RotateCcw className="w-5 h-5 text-primary" />
                <div>
                  <div className="text-sm font-medium">Allow Delegation</div>
                  <div className="text-xs text-secondaryText">Let this agent delegate tasks to other agents</div>
                </div>
              </div>
              <button
                onClick={() => updateField('allow_delegation', !config.allow_delegation)}
                className={`relative w-11 h-6 rounded-full transition-colors ${config.allow_delegation ? 'bg-primary' : 'bg-surface-highest border border-outline/20'}`}
              >
                <motion.span
                  layout
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-background transition-transform ${config.allow_delegation ? 'translate-x-5' : ''}`}
                />
              </button>
            </div>
            <div className="flex items-center justify-between p-4 rounded-lg bg-surface-highest border border-outline/10">
              <div className="flex items-center gap-3">
                <Cpu className="w-5 h-5 text-primary" />
                <div>
                  <div className="text-sm font-medium">Memory Enabled</div>
                  <div className="text-xs text-secondaryText">Persist context across executions</div>
                </div>
              </div>
              <button
                onClick={() => updateField('memory_enabled', !config.memory_enabled)}
                className={`relative w-11 h-6 rounded-full transition-colors ${config.memory_enabled ? 'bg-primary' : 'bg-surface-highest border border-outline/20'}`}
              >
                <motion.span
                  layout
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-background transition-transform ${config.memory_enabled ? 'translate-x-5' : ''}`}
                />
              </button>
            </div>
          </div>
        );
      case 'templates':
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                System Template
              </label>
              <textarea
                className="w-full obsidian-input min-h-[120px] resize-none"
                placeholder="Optional Jinja2 template for the system prompt..."
                value={config.system_template}
                onChange={(e) => updateField('system_template', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                Prompt Template
              </label>
              <textarea
                className="w-full obsidian-input min-h-[120px] resize-none"
                placeholder="Optional Jinja2 template for user prompts..."
                value={config.prompt_template}
                onChange={(e) => updateField('prompt_template', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">
                Response Template
              </label>
              <textarea
                className="w-full obsidian-input min-h-[120px] resize-none"
                placeholder="Optional Jinja2 template for formatting responses..."
                value={config.response_template}
                onChange={(e) => updateField('response_template', e.target.value)}
              />
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-8">
      {/* Top Bar */}
      <div className="px-8 pt-8 pb-4 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agent Builder V2</h1>
          <p className="text-secondaryText text-sm mt-0.5">Compose agents with precision.</p>
        </div>
        <div className="flex items-center gap-3">
          {saveError && (
            <span className="text-xs text-[#FF4B4B]">{saveError}</span>
          )}
          {saveSuccess && (
            <span className="text-xs text-[#00FF88] flex items-center gap-1">
              <Check className="w-3 h-3" /> Saved
            </span>
          )}
          <motion.button
            onClick={() => {
              setConfig({ ...DEFAULT_CONFIG });
              setSelectedTemplate(null);
              setSaveSuccess(false);
              setSaveError('');
            }}
            whileTap={{ scale: 0.96 }}
            className="btn-secondary flex items-center gap-2 text-xs"
          >
            <X className="w-3.5 h-3.5" /> Reset
          </motion.button>
          <motion.button
            onClick={handleSave}
            disabled={isSaving}
            whileTap={{ scale: 0.96 }}
            whileHover={{ scale: 1.02 }}
            className="btn-primary flex items-center gap-2 shadow-glow-cyan disabled:opacity-50 text-xs"
          >
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {isSaving ? 'Saving...' : 'Save Agent'}
          </motion.button>
        </div>
      </div>

      {/* 3-Panel Workspace */}
      <div className="flex flex-1 min-h-0 px-8 pb-8 gap-4">
        {/* Left Panel: Templates */}
        <aside className="w-72 flex flex-col gap-3 shrink-0">
          <div className="text-xs font-semibold tracking-widest uppercase text-secondaryText px-1">
            Template Library
          </div>
          <div className="flex flex-col gap-3 overflow-y-auto pr-1">
            {TEMPLATES.map((template) => {
              const Icon = template.icon;
              const isActive = selectedTemplate === template.id;
              return (
                <motion.button
                  key={template.id}
                  onClick={() => applyTemplate(template.id)}
                  whileTap={{ scale: 0.98 }}
                  whileHover={{ y: -2, transition: { type: 'spring', stiffness: 400 } }}
                  className={`text-left p-4 rounded-xl border transition-all ${
                    isActive
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-outline/10 bg-surface-low hover:border-outline/30'
                  }`}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isActive ? 'bg-primary/10' : 'bg-surface-highest'}`}>
                      <Icon className={`w-4 h-4 ${isActive ? 'text-primary' : 'text-secondaryText'}`} />
                    </div>
                    <span className="text-sm font-medium">{template.name}</span>
                  </div>
                  <p className="text-xs text-secondaryText leading-relaxed">{template.description}</p>
                </motion.button>
              );
            })}
          </div>

          {savedAgents.length > 0 && (
            <>
              <div className="text-xs font-semibold tracking-widest uppercase text-secondaryText px-1 mt-2">
                Saved Agents
              </div>
              <div className="flex flex-col gap-2 overflow-y-auto pr-1">
                {savedAgents.map((agent) => (
                  <motion.div
                    key={agent.agent_id}
                    whileHover={{ x: 2 }}
                    whileTap={{ scale: 0.98 }}
                    className="flex items-center justify-between p-3 rounded-lg bg-surface-low border border-outline/10"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Bot className="w-4 h-4 text-primary shrink-0" />
                      <span className="text-sm truncate">{agent.name}</span>
                    </div>
                    <span className="text-[10px] uppercase text-secondaryText bg-surface-highest px-1.5 py-0.5 rounded shrink-0">
                      {agent.role}
                    </span>
                  </motion.div>
                ))}
              </div>
            </>
          )}
        </aside>

        {/* Center Panel: Tabbed Editor */}
        <main className="flex-1 flex flex-col min-w-0 obsidian-panel border border-outline/10 overflow-hidden">
          {/* Tabs */}
          <div className="flex items-center gap-1 px-4 pt-3 pb-0 border-b border-outline/10 overflow-x-auto">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <motion.button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  whileTap={{ scale: 0.98 }}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-t-lg text-sm font-medium transition-all border-b-2 ${
                    isActive
                      ? 'border-primary text-primary bg-primary/5'
                      : 'border-transparent text-secondaryText hover:text-primaryText hover:bg-surface-highest'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </motion.button>
              );
            })}
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-6">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
              >
                {renderTabContent()}
              </motion.div>
            </AnimatePresence>
          </div>
        </main>

        {/* Right Panel: Live Test Chat */}
        <aside className="w-80 flex flex-col shrink-0 obsidian-panel border border-outline/10 overflow-hidden">
          <div className="px-4 py-3 border-b border-outline/10 flex items-center justify-between bg-surface-lowest">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold">Live Test</span>
            </div>
              <motion.button
                onClick={() => {
                  setChatMessages([]);
                  setIsTyping(false);
                }}
                whileTap={{ scale: 0.9 }}
                className="p-1 rounded hover:bg-surface-highest text-secondaryText hover:text-primaryText transition-colors"
                title="Clear chat"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </motion.button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {chatMessages.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-center text-secondaryText gap-3">
                <div className="w-12 h-12 rounded-full bg-surface-highest flex items-center justify-center">
                  <Sparkles className="w-5 h-5 text-primary" />
                </div>
                <div className="text-sm">Test your agent here</div>
                <div className="text-xs max-w-[200px]">
                  Configure the agent and send messages to preview behavior.
                </div>
              </div>
            )}
            {chatMessages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 8, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[90%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-primary text-background rounded-br-md'
                      : 'bg-surface-highest text-primaryText border border-outline/10 rounded-bl-md'
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              </motion.div>
            ))}
            {isTyping && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex justify-start"
              >
                <div className="bg-surface-highest border border-outline/10 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-secondaryText animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-secondaryText animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-secondaryText animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </motion.div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-outline/10 bg-surface-lowest">
            <div className="flex items-end gap-2">
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a test message..."
                rows={1}
                className="flex-1 bg-surface-highest border border-outline/20 rounded-xl px-3.5 py-2.5 text-sm text-primaryText placeholder:text-secondaryText/50 focus:outline-none focus:border-primary/50 resize-none max-h-32"
                style={{ minHeight: '40px' }}
              />
              <motion.button
                onClick={handleTestSend}
                disabled={!chatInput.trim() || isTyping}
                whileTap={{ scale: 0.9 }}
                whileHover={{ scale: 1.05 }}
                className="p-2.5 rounded-xl bg-primary text-background hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed transition-opacity"
              >
                <Send className="w-4 h-4" />
              </motion.button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

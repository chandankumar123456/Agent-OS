import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
 MessageSquare,
 Plus,
 Send,
 Trash2,
 Bot,
 User,
 Loader2,
 PanelLeft,
 PanelLeftClose,
 Sparkles,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { buttonTap } from '../lib/animations';
import type { ChatSession, AgentInfo } from '../api/client';
import { chatMessageVariants } from '../lib/animations';

// Lightweight markdown renderer
function Markdown({ content }: { content: string }) {
 const lines = content.split('\n');
 const elements: React.ReactElement[] = [];
 let inCodeBlock = false;
 let codeContent = '';

 lines.forEach((line, i) => {
 if (line.startsWith('```')) {
 if (inCodeBlock) {
 elements.push(
 <pre key={`code-${i}`} className="bg-[#1A1A2E] border-4 border-white/10 p-4 my-4 overflow-x-auto shadow-pixel">
 <code className="text-xs font-retro text-accent-mint">{codeContent.trimEnd()}</code>
 </pre>
 );
 codeContent = '';
 inCodeBlock = false;
 } else {
 inCodeBlock = true;
 }
 return;
 }

 if (inCodeBlock) {
 codeContent += line + '\n';
 return;
 }

 // Blockquote
 if (line.startsWith('> ')) {
 elements.push(
 <blockquote key={`bq-${i}`} className="border-l-4 border-accent-yellow pl-4 my-4 text-secondaryText italic text-lg font-retro">
 {parseInline(line.slice(2))}
 </blockquote>
 );
 return;
 }

 // Headers
 if (line.startsWith('# ')) {
 elements.push(<h1 key={`h-${i}`} className="text-xl font-pixel uppercase mt-6 mb-4 tracking-tighter text-primary">{parseInline(line.slice(2))}</h1>);
 return;
 }
 if (line.startsWith('## ')) {
 elements.push(<h2 key={`h-${i}`} className="text-lg font-pixel uppercase mt-6 mb-2 tracking-tighter">{parseInline(line.slice(3))}</h2>);
 return;
 }
 if (line.startsWith('### ')) {
 elements.push(<h3 key={`h-${i}`} className="text-sm font-pixel uppercase mt-4 mb-1 tracking-tighter">{parseInline(line.slice(4))}</h3>);
 return;
 }

 // Empty line
 if (line.trim() === '') {
 elements.push(<div key={`br-${i}`} className="h-2" />);
 return;
 }

 // List item
 if (line.startsWith('- ') || line.startsWith('* ')) {
 elements.push(
 <li key={`li-${i}`} className="ml-6 text-lg leading-relaxed font-retro list-none relative before:content-['■'] before:absolute before:-left-6 before:text-primary before:text-[10px] before:top-1">
 {parseInline(line.slice(2))}
 </li>
 );
 return;
 }

 // Paragraph
 elements.push(<p key={`p-${i}`} className="text-lg leading-relaxed font-retro">{parseInline(line)}</p>);
 });

 if (inCodeBlock && codeContent) {
 elements.push(
 <pre key="code-end" className="bg-[#1A1A2E] border-4 border-white/10 p-4 my-4 overflow-x-auto shadow-pixel">
 <code className="text-xs font-retro text-accent-mint">{codeContent.trimEnd()}</code>
 </pre>
 );
 }

 return <>{elements}</>;
}

function parseInline(text: string): React.ReactElement {
 const parts: (string | React.ReactElement)[] = [];
 let remaining = text;
 let key = 0;

 while (remaining.length > 0) {
 // Bold **text**
 const boldMatch = remaining.match(/^(.*?)\*\*(.+?)\*\*(.*)/);
 if (boldMatch) {
 if (boldMatch[1]) parts.push(boldMatch[1]);
 parts.push(<strong key={`b-${key++}`} className="font-semibold text-primaryText">{boldMatch[2]}</strong>);
 remaining = boldMatch[3];
 continue;
 }

 // Italic *text*
 const italicMatch = remaining.match(/^(.*?)\*(.+?)\*(.*)/);
 if (italicMatch) {
 if (italicMatch[1]) parts.push(italicMatch[1]);
 parts.push(<em key={`i-${key++}`} className="italic">{italicMatch[2]}</em>);
 remaining = italicMatch[3];
 continue;
 }

 // Inline code `text`
 const codeMatch = remaining.match(/^(.*?)`(.+?)`(.*)/);
 if (codeMatch) {
 if (codeMatch[1]) parts.push(codeMatch[1]);
 parts.push(
 <code key={`c-${key++}`} className="bg-surface-lowest px-1 py-1 rounded-none text-xs font-mono text-primary border border-outline/10">
 {codeMatch[2]}
 </code>
 );
 remaining = codeMatch[3];
 continue;
 }

 parts.push(remaining);
 break;
 }

 return <>{parts}</>;
}

interface DisplayMessage {
 id: string;
 role: 'user' | 'assistant';
 content: string;
 displayContent: string;
 isStreaming?: boolean;
}

export default function Chat() {
 const [sessions, setSessions] = useState<ChatSession[]>([]);
 const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
 const [messages, setMessages] = useState<DisplayMessage[]>([]);
 const [input, setInput] = useState('');
 const [isLoading, setIsLoading] = useState(false);
 const [sidebarOpen, setSidebarOpen] = useState(true);
 const [agents, setAgents] = useState<AgentInfo[]>([]);
 const [selectedAgentId, setSelectedAgentId] = useState<string>('');
 const [isCreatingSession, setIsCreatingSession] = useState(false);
 const messagesEndRef = useRef<HTMLDivElement>(null);
 const inputRef = useRef<HTMLTextAreaElement>(null);
 const streamTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

 // Load sessions and agents on mount
 useEffect(() => {
 apiClient.getSessions().then(setSessions).catch(() => {});
 apiClient.listAgents().then((a) => {
 setAgents(a);
 if (a.length > 0) setSelectedAgentId(a[0].agent_id);
 }).catch(() => {});
 }, []);

 // Load messages when session changes
 useEffect(() => {
 if (!currentSessionId) {
 setMessages([]);
 return;
 }
 apiClient.getMessages(currentSessionId)
 .then((msgs) => {
 setMessages(
 msgs.map((m) => ({
 id: m.id,
 role: m.role as 'user' | 'assistant',
 content: m.content,
 displayContent: m.content,
 }))
 );
 })
 .catch(() => setMessages([]));
 }, [currentSessionId]);

 useEffect(() => {
 messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
 }, [messages]);

 // Cleanup streaming timer on unmount
 useEffect(() => {
 return () => {
 if (streamTimerRef.current) {
 clearInterval(streamTimerRef.current);
 }
 };
 }, []);

 const createNewSession = async () => {
 setIsCreatingSession(true);
 try {
 const session = await apiClient.createSession(selectedAgentId || undefined, 'New Chat');
 setSessions((prev) => [session, ...prev]);
 setCurrentSessionId(session.id);
 setMessages([]);
 } catch (err) {
 console.error('Failed to create session:', err);
 } finally {
 setIsCreatingSession(false);
 }
 };

 const deleteSession = async (sessionId: string, e: React.MouseEvent) => {
 e.stopPropagation();
 try {
 await apiClient.deleteSession(sessionId);
 setSessions((prev) => prev.filter((s) => s.id !== sessionId));
 if (currentSessionId === sessionId) {
 setCurrentSessionId(null);
 setMessages([]);
 }
 } catch (err) {
 console.error('Failed to delete session:', err);
 }
 };

 const startStreaming = (msgId: string, fullContent: string) => {
 const words = fullContent.split(/(\s+)/);
 let idx = 0;

 if (streamTimerRef.current) clearInterval(streamTimerRef.current);

 streamTimerRef.current = setInterval(() => {
 idx += 1;
 const displayContent = words.slice(0, idx).join('');
 setMessages((prev) =>
 prev.map((m) =>
 m.id === msgId
 ? { ...m, displayContent, isStreaming: idx < words.length }
 : m
 )
 );
 if (idx >= words.length) {
 if (streamTimerRef.current) clearInterval(streamTimerRef.current);
 }
 }, 25);
 };

 const handleSend = async () => {
 if (!input.trim() || isLoading) return;

 let sessionId = currentSessionId;
 if (!sessionId) {
 try {
 const session = await apiClient.createSession(selectedAgentId || undefined, input.trim().slice(0, 40));
 if (!session?.id) {
 console.error('Created session missing id:', session);
 return;
 }
 sessionId = session.id;
 setSessions((prev) => [session, ...prev]);
 setCurrentSessionId(session.id);
 } catch (err) {
 console.error('Failed to create session:', err);
 return;
 }
 }

 if (!sessionId) {
 console.error('No session ID available');
 return;
 }

 const userMsg: DisplayMessage = {
 id: `u_${Date.now()}`,
 role: 'user',
 content: input.trim(),
 displayContent: input.trim(),
 };
 setMessages((prev) => [...prev, userMsg]);
 setInput('');
 setIsLoading(true);

 try {
 await apiClient.sendMessage(sessionId, userMsg.content);

 // Mock assistant response
 const mockResponses = [
 "I understand. Let me think through this step by step.\n\nFirst, I'll analyze the core components of your request. Then I'll provide a structured response based on my training data and available tools.\n\n**Key observations:**\n- The query is well-formed\n- I have sufficient context to proceed\n- No additional clarification needed\n\nHere's my detailed response based on the analysis above.",
 "Great question! Here's what I found:\n\n```python\ndef analyze(query: str) -> dict:\n return {\n 'status': 'success',\n 'confidence': 0.94,\n 'result': query.upper()\n }\n```\n\nThe function above demonstrates a simple pattern. In practice, I would invoke the appropriate tools and synthesize results.",
 "I've processed your request. Based on my current configuration and the context provided, here's the breakdown:\n\n1. **Intent Recognition**: Clear objective stated\n2. **Tool Selection**: No specialized tools required for this query\n3. **Response Generation**: Direct answer mode activated\n\n> Note: In a production environment, this would route through LangGraph with full tracing.",
 ];
 const responseText = mockResponses[Math.floor(Math.random() * mockResponses.length)];

 const assistantMsg: DisplayMessage = {
 id: `a_${Date.now()}`,
 role: 'assistant',
 content: responseText,
 displayContent: '',
 isStreaming: true,
 };
 setMessages((prev) => [...prev, assistantMsg]);
 startStreaming(assistantMsg.id, responseText);
 } catch (err) {
 console.error('Failed to send message:', err);
 } finally {
 setIsLoading(false);
 }
 };

 const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
 if (e.key === 'Enter' && !e.shiftKey) {
 e.preventDefault();
 handleSend();
 }
 };

 const currentSession = sessions.find((s) => s.id === currentSessionId);

 return (
 <div className="flex h-[calc(100vh-4rem)] -m-8">
 {/* Sidebar */}
 <AnimatePresence initial={false}>
 {sidebarOpen && (
 <motion.aside
 initial={{ width: 0, opacity: 0 }}
 animate={{ width: 300, opacity: 1 }}
 exit={{ width: 0, opacity: 0 }}
 transition={{ duration: 0.1 }}
 className="border-r-4 border-outline bg-surface flex flex-col overflow-hidden"
 >
 <div className="p-4 border-b-4 border-outline flex items-center justify-between bg-white">
 <div className="flex items-center gap-2">
 <MessageSquare className="w-5 h-5 text-primary" />
 <span className="font-pixel text-[10px] uppercase">Chat History</span>
 </div>
 <motion.button
 onClick={() => setSidebarOpen(false)}
 {...buttonTap}
 className="p-2 border-4 border-outline hover:bg-surface-high "
 >
 <PanelLeftClose className="w-4 h-4" />
 </motion.button>
 </div>

 <div className="p-4">
 <motion.button
 onClick={createNewSession}
 disabled={isCreatingSession}
 {...buttonTap}
 className="w-full btn-primary flex items-center justify-center gap-2 py-4"
 >
 {isCreatingSession ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
 [ NEW CHAT ]
 </motion.button>
 </div>

 <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
 {sessions.length === 0 && (
 <div className="text-center text-secondaryText font-retro text-lg py-8 uppercase opacity-50">
 No logs found.
 </div>
 )}
 {sessions.map((session) => (
 <motion.button
 key={session.id}
 onClick={() => setCurrentSessionId(session.id)}
 {...buttonTap}
 className={`w-full text-left p-4 group flex items-center gap-3 border-4 ${
 currentSessionId === session.id
 ? 'bg-primary text-white border-outline shadow-pixel'
 : 'hover:bg-surface-high bg-white border-transparent hover:border-outline'
 }`}
 >
 <MessageSquare className={`w-5 h-5 shrink-0 ${currentSessionId === session.id ? 'text-white' : 'text-primary'}`} />
 <div className="flex-1 min-w-0">
 <div className={`font-retro text-lg truncate uppercase ${currentSessionId === session.id ? 'text-white' : 'text-primaryText'}`}>
 {session.title || 'Untitled Session'}
 </div>
 <div className={`font-pixel text-[8px] uppercase mt-1 ${currentSessionId === session.id ? 'text-white/70' : 'text-secondaryText/60'}`}>
 {session.updated_at ? new Date(session.updated_at).toLocaleDateString() : ''}
 </div>
 </div>
 <motion.button
 onClick={(e) => deleteSession(session.id, e)}
 {...buttonTap}
 className="opacity-0 group-hover:opacity-100 p-2 border-4 border-outline hover:bg-[#FF4B4B] hover:text-white bg-white text-secondaryText"
 >
 <Trash2 className="w-3.5 h-3.5" />
 </motion.button>
 </motion.button>
 ))}
 </div>
 </motion.aside>
 )}
 </AnimatePresence>

 {/* Main Chat Area */}
 <main className="flex-1 flex flex-col min-w-0 bg-surface-lowest">
 {/* Header */}
 <div className="h-16 border-b-4 border-outline bg-white flex items-center justify-between px-6 shrink-0">
 <div className="flex items-center gap-4">
 {!sidebarOpen && (
 <motion.button
 onClick={() => setSidebarOpen(true)}
 {...buttonTap}
 className="p-2 border-4 border-outline hover:bg-surface-high "
 >
 <PanelLeft className="w-4 h-4" />
 </motion.button>
 )}
 <div className="flex items-center gap-3">
 {currentSession ? (
 <>
 <span className="font-pixel text-[10px] uppercase truncate max-w-[200px] md:max-w-md">
 {currentSession?.title || 'New Chat'}
 </span>
 <span className="font-pixel text-[8px] bg-accent-yellow border-4 border-outline px-2 py-1">
 {(currentSession?.id || 'unknown').slice(0, 8)}
 </span>
 </>
 ) : (
 <span className="font-retro text-lg text-secondaryText uppercase">[ Select Channel ]</span>
 )}
 </div>
 </div>

 <div className="flex items-center gap-4">
 <select
 value={selectedAgentId}
 onChange={(e) => setSelectedAgentId(e.target.value)}
 className="pixel-input py-2 text-[10px] font-pixel uppercase pr-8"
 >
 <option value="">No Agent</option>
 {agents.map((agent) => (
 <option key={agent.agent_id} value={agent.agent_id}>
 {agent.name}
 </option>
 ))}
 </select>
 </div>
 </div>

 {/* Messages */}
 <div className="flex-1 overflow-y-auto px-6 md:px-8 py-8">
 {messages.length === 0 && !currentSessionId && (
 <div className="h-full flex flex-col items-center justify-center text-center gap-6">
 <div className="w-24 h-24 border-4 border-outline bg-accent-mint flex items-center justify-center shadow-pixel">
 <Sparkles className="w-12 h-12 text-primaryText" />
 </div>
 <div>
 <h2 className="text-2xl font-pixel uppercase mb-4">AgentOS Chat</h2>
 <p className="text-xl font-retro text-secondaryText max-w-sm">
 Initialize communication link. Select an agent to begin orchestration.
 </p>
 </div>
 </div>
 )}

 {messages.length === 0 && currentSessionId && (
 <div className="h-full flex flex-col items-center justify-center text-center gap-4">
 <Bot className="w-12 h-12 text-primary" />
 <p className="text-xl font-retro text-secondaryText uppercase opacity-50">Signal connected. Awaiting input.</p>
 </div>
 )}

 <div className="max-w-4xl mx-auto space-y-10 pb-8">
 <AnimatePresence initial={false}>
 {messages.map((msg) => (
 <motion.div
 key={msg.id}
 custom={msg.role === 'user'}
 variants={chatMessageVariants}
 initial="hidden"
 animate="visible"
 layout
 className={`flex gap-6 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
 >
 <div className={`w-10 h-10 border-4 border-outline flex items-center justify-center shrink-0 mt-2 shadow-pixel ${
 msg.role === 'user' ? 'bg-primary' : 'bg-white'
 }`}>
 {msg.role === 'user' ? (
 <User className="w-6 h-6 text-white" />
 ) : (
 <Bot className="w-6 h-6 text-primary" />
 )}
 </div>
 <div className={`max-w-[85%] ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col`}>
 <div className={`font-pixel text-[8px] uppercase mb-2 ${msg.role === 'user' ? 'text-primary' : 'text-secondaryText'}`}>
 {msg.role === 'user' ? 'User_01' : 'Agent_Node'}
 </div>
 <div
 className={`px-6 py-4 border-4 border-outline shadow-pixel ${
 msg.role === 'user'
 ? 'bg-[#FF6B35] text-white'
 : 'bg-white text-primaryText'
 }`}
 >
 {msg.role === 'assistant' ? (
 <Markdown content={msg.displayContent} />
 ) : (
 <div className="whitespace-pre-wrap font-retro text-xl leading-relaxed">{msg.displayContent}</div>
 )}
 </div>
 </div>
 </motion.div>
 ))}
 </AnimatePresence>
 {isLoading && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
 <div className="flex gap-6">
 <div className="w-10 h-10 border-4 border-outline bg-white flex items-center justify-center shrink-0 mt-2 shadow-pixel">
 <Bot className="w-6 h-6 text-primary" />
 </div>
 <motion.div
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 className="bg-white border-4 border-outline px-6 py-4 flex items-center gap-3 shadow-pixel"
 >
 <span className="w-3 h-3 bg-primary animate-pulse" />
 <span className="w-3 h-3 bg-primary animate-pulse" style={{ animationDelay: '100ms' }} />
 <span className="w-3 h-3 bg-primary animate-pulse" style={{ animationDelay: '200ms' }} />
 </motion.div>
 </div>
 )}
 <div ref={messagesEndRef} />
 </div>
 </div>

 {/* Input */}
 <div className="border-t-4 border-outline bg-white p-6 shrink-0 shadow-[0_-4px_0_rgba(0,0,0,0.05)]">
 <div className="max-w-4xl mx-auto relative">
 <div className="flex items-end gap-4 border-4 border-outline p-2 bg-surface-lowest focus-within:bg-white ">
 <textarea
 ref={inputRef}
 value={input}
 onChange={(e) => setInput(e.target.value)}
 onKeyDown={handleKeyDown}
 placeholder="INPUT COMMAND..."
 rows={1}
 className="flex-1 bg-transparent px-4 py-4 font-retro text-xl text-primaryText placeholder:text-secondaryText/30 focus:outline-none resize-none max-h-60"
 style={{ minHeight: '52px' }}
 />
 <motion.button
 onClick={handleSend}
 disabled={!input.trim() || isLoading}
 {...buttonTap}
 className="btn-primary py-4 px-4 disabled:opacity-30 disabled:cursor-not-allowed mb-1"
 >
 {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
 </motion.button>
 </div>
 <div className="text-center mt-4">
 <span className="font-pixel text-[8px] text-secondaryText/40 uppercase">
 // AUTH_REQUIRED: VERIFY_OUTPUT_INTEGRITY
 </span>
 </div>
 </div>
 </div>
 </main>
 </div>
 );
}

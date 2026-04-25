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
          <pre key={`code-${i}`} className="bg-surface-lowest border border-outline/10 rounded-lg p-3 my-2 overflow-x-auto">
            <code className="text-xs font-mono text-primaryText">{codeContent.trimEnd()}</code>
          </pre>
        );
        codeContent = '';
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        // code language: line.slice(3).trim()
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
        <blockquote key={`bq-${i}`} className="border-l-2 border-primary/40 pl-3 my-2 text-secondaryText italic text-sm">
          {parseInline(line.slice(2))}
        </blockquote>
      );
      return;
    }

    // Headers
    if (line.startsWith('# ')) {
      elements.push(<h1 key={`h-${i}`} className="text-lg font-bold mt-3 mb-1">{parseInline(line.slice(2))}</h1>);
      return;
    }
    if (line.startsWith('## ')) {
      elements.push(<h2 key={`h-${i}`} className="text-base font-bold mt-3 mb-1">{parseInline(line.slice(3))}</h2>);
      return;
    }
    if (line.startsWith('### ')) {
      elements.push(<h3 key={`h-${i}`} className="text-sm font-bold mt-2 mb-1">{parseInline(line.slice(4))}</h3>);
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
        <li key={`li-${i}`} className="ml-4 text-sm leading-relaxed list-disc marker:text-primary">
          {parseInline(line.slice(2))}
        </li>
      );
      return;
    }

    // Numbered list
    const numMatch = line.match(/^\d+\.\s(.*)/);
    if (numMatch) {
      elements.push(
        <li key={`li-${i}`} className="ml-4 text-sm leading-relaxed list-decimal marker:text-primary">
          {parseInline(numMatch[1])}
        </li>
      );
      return;
    }

    // Paragraph
    elements.push(<p key={`p-${i}`} className="text-sm leading-relaxed">{parseInline(line)}</p>);
  });

  if (inCodeBlock && codeContent) {
    elements.push(
      <pre key="code-end" className="bg-surface-lowest border border-outline/10 rounded-lg p-3 my-2 overflow-x-auto">
        <code className="text-xs font-mono text-primaryText">{codeContent.trimEnd()}</code>
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
        <code key={`c-${key++}`} className="bg-surface-lowest px-1 py-0.5 rounded text-xs font-mono text-primary border border-outline/10">
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
        "Great question! Here's what I found:\n\n```python\ndef analyze(query: str) -> dict:\n    return {\n        'status': 'success',\n        'confidence': 0.94,\n        'result': query.upper()\n    }\n```\n\nThe function above demonstrates a simple pattern. In practice, I would invoke the appropriate tools and synthesize results.",
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
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-r border-outline/10 bg-surface-low flex flex-col overflow-hidden"
          >
            <div className="p-4 border-b border-outline/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-primary" />
                <span className="font-semibold">Chats</span>
              </div>
              <motion.button
                onClick={() => setSidebarOpen(false)}
                whileTap={{ scale: 0.9 }}
                className="p-1.5 rounded-lg hover:bg-surface-highest text-secondaryText hover:text-primaryText transition-colors"
              >
                <PanelLeftClose className="w-4 h-4" />
              </motion.button>
            </div>

            <div className="p-3">
              <motion.button
                onClick={createNewSession}
                disabled={isCreatingSession}
                whileTap={{ scale: 0.97 }}
                whileHover={{ scale: 1.01 }}
                transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                className="w-full flex items-center justify-center gap-2 p-2.5 rounded-xl bg-surface-highest border border-outline/10 hover:border-primary/30 text-primaryText transition-colors text-sm font-medium disabled:opacity-50"
              >
                {isCreatingSession ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                New Chat
              </motion.button>
            </div>

            <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-1">
              {sessions.length === 0 && (
                <div className="text-center text-secondaryText text-xs py-8">
                  No chats yet. Start a new conversation.
                </div>
              )}
              {sessions.map((session) => (
                <motion.button
                  key={session.id}
                  onClick={() => setCurrentSessionId(session.id)}
                  whileTap={{ scale: 0.98 }}
                  className={`w-full text-left p-3 rounded-xl transition-all group flex items-center gap-3 ${
                    currentSessionId === session.id
                      ? 'bg-primary/10 border border-primary/20'
                      : 'hover:bg-surface-highest border border-transparent'
                  }`}
                >
                  <MessageSquare className={`w-4 h-4 shrink-0 ${currentSessionId === session.id ? 'text-primary' : 'text-secondaryText'}`} />
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm truncate ${currentSessionId === session.id ? 'text-primaryText' : 'text-secondaryText'}`}>
                      {session.title || 'New Chat'}
                    </div>
                    <div className="text-[10px] text-secondaryText/60">
                      {session.updated_at ? new Date(session.updated_at).toLocaleDateString() : ''}
                    </div>
                  </div>
                  <motion.button
                    onClick={(e) => deleteSession(session.id, e)}
                    whileTap={{ scale: 0.85 }}
                    whileHover={{ scale: 1.1 }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[#FF4B4B]/10 text-secondaryText hover:text-[#FF4B4B] transition-all"
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
      <main className="flex-1 flex flex-col min-w-0 bg-surface">
        {/* Header */}
        <div className="h-14 border-b border-outline/10 flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <motion.button
                onClick={() => setSidebarOpen(true)}
                whileTap={{ scale: 0.9 }}
                className="p-1.5 rounded-lg hover:bg-surface-highest text-secondaryText hover:text-primaryText transition-colors"
              >
                <PanelLeft className="w-4 h-4" />
              </motion.button>
            )}
            <div className="flex items-center gap-2">
              {currentSession ? (
                <>
                  <span className="text-sm font-medium truncate max-w-[200px] md:max-w-md">
                    {currentSession?.title || 'New Chat'}
                  </span>
                  <span className="text-[10px] text-secondaryText bg-surface-highest px-1.5 py-0.5 rounded">
                    {(currentSession?.id || 'unknown').slice(0, 8)}
                  </span>
                </>
              ) : (
                <span className="text-sm text-secondaryText">Select or start a chat</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={selectedAgentId}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              className="bg-surface-highest border border-outline/20 rounded-lg px-3 py-1.5 text-xs text-primaryText focus:outline-none focus:border-primary/50"
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
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6">
          {messages.length === 0 && !currentSessionId && (
            <div className="h-full flex flex-col items-center justify-center text-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-surface-highest border border-outline/10 flex items-center justify-center">
                <Sparkles className="w-7 h-7 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-semibold mb-1">AgentOS Chat</h2>
                <p className="text-sm text-secondaryText max-w-sm">
                  Start a conversation with your agents. Select an agent from the dropdown above, or just start typing.
                </p>
              </div>
            </div>
          )}

          {messages.length === 0 && currentSessionId && (
            <div className="h-full flex flex-col items-center justify-center text-center gap-2">
              <Bot className="w-8 h-8 text-primary/60" />
              <p className="text-sm text-secondaryText">Send a message to start the conversation.</p>
            </div>
          )}

          <div className="max-w-3xl mx-auto space-y-6">
            <AnimatePresence initial={false}>
              {messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  custom={msg.role === 'user'}
                  variants={chatMessageVariants}
                  initial="hidden"
                  animate="visible"
                  layout
                  className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                    msg.role === 'user' ? 'bg-primary/20' : 'bg-surface-highest border border-outline/10'
                  }`}>
                    {msg.role === 'user' ? (
                      <User className="w-3.5 h-3.5 text-primary" />
                    ) : (
                      <Bot className="w-3.5 h-3.5 text-primary" />
                    )}
                  </div>
                  <div className={`max-w-[85%] ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col`}>
                    <div
                      className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                        msg.role === 'user'
                          ? 'bg-primary text-background rounded-br-md'
                          : 'bg-surface-highest border border-outline/10 rounded-bl-md text-primaryText'
                      }`}
                    >
                      {msg.role === 'assistant' ? (
                        <Markdown content={msg.displayContent} />
                      ) : (
                        <div className="whitespace-pre-wrap">{msg.displayContent}</div>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            {isLoading && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
              <div className="flex gap-3">
                <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 bg-surface-highest border border-outline/10">
                  <Bot className="w-3.5 h-3.5 text-primary" />
                </div>
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="bg-surface-highest border border-outline/10 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1.5"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-secondaryText animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-secondaryText animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-secondaryText animate-bounce" style={{ animationDelay: '300ms' }} />
                </motion.div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-outline/10 p-4 shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-2 bg-surface-highest border border-outline/20 rounded-2xl p-2 focus-within:border-primary/50 transition-colors">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message AgentOS..."
                rows={1}
                className="flex-1 bg-transparent px-3 py-2.5 text-sm text-primaryText placeholder:text-secondaryText/50 focus:outline-none resize-none max-h-40"
                style={{ minHeight: '40px' }}
              />
              <motion.button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                whileTap={{ scale: 0.9 }}
                whileHover={{ scale: 1.05 }}
                transition={{ type: 'spring', stiffness: 500, damping: 25 }}
                className="p-2.5 rounded-xl bg-primary text-background hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed transition-opacity shrink-0 mb-0.5"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </motion.button>
            </div>
            <div className="text-center mt-2">
              <span className="text-[10px] text-secondaryText/40">
                AgentOS can make mistakes. Verify important information.
              </span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

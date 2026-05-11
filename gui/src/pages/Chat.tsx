import { useState, useRef, useEffect } from 'react'
import { supervisorApi } from '../api/supervisor'
import { 
  Send, 
  Paperclip,
  Bot,
  User,
  Trash2,
  Copy
} from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! I\'m AgentOS. How can I help you today?',
      timestamp: new Date().toISOString(),
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const result = await supervisorApi.createTask(input)
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `I've started task ${result.taskId} to handle your request. You can monitor progress in the Dashboard.`,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Sorry, I couldn't start a task: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-2xl font-bold">Chat</h2>
        <p className="text-gray-400 mt-1">Have a conversation with AgentOS</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto p-6 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex gap-4 ${
              message.role === 'user' ? 'flex-row-reverse' : ''
            }`}
          >
            {/* Avatar */}
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                message.role === 'user'
                  ? 'bg-agentos-primary/20 text-agentos-primary'
                  : 'bg-gradient-to-br from-agentos-primary to-blue-600 text-white'
              }`}
            >
              {message.role === 'user' ? (
                <User className="w-5 h-5" />
              ) : (
                <Bot className="w-5 h-5" />
              )}
            </div>

            {/* Message content */}
            <div className={`flex-1 max-w-3xl ${message.role === 'user' ? 'items-end' : ''} flex flex-col`}>
              <div
                className={`rounded-2xl px-4 py-3 ${
                  message.role === 'user'
                    ? 'bg-agentos-primary text-white rounded-br-none'
                    : 'bg-agentos-dark border border-gray-800 rounded-bl-none'
                }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
              <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                <span>{formatTime(message.timestamp)}</span>
                {message.role === 'assistant' && (
                  <div className="flex gap-1">
                    <button className="p-1 hover:bg-gray-800 rounded">
                      <Copy className="w-3 h-3" />
                    </button>
                    <button className="p-1 hover:bg-gray-800 rounded">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-800">
        <div className="flex gap-3">
          <button className="p-3 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors">
            <Paperclip className="w-5 h-5" />
          </button>
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              rows={1}
              className="w-full bg-agentos-dark border border-gray-700 rounded-lg pl-4 pr-12 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-agentos-primary resize-none"
              style={{ minHeight: '48px', maxHeight: '120px' }}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="p-3 bg-agentos-primary hover:bg-blue-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <div className="text-center mt-2">
          <span className="text-xs text-gray-500">
            Press Enter to send, Shift+Enter for new line
          </span>
        </div>
      </div>
    </div>
  )
}

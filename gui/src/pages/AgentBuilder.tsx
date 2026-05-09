import { useState } from 'react'
import { 
  Bot, 
  Plus, 
  Play, 
  Settings, 
  Trash2,
  Copy,
  CheckCircle
} from 'lucide-react'

interface Agent {
  id: string
  name: string
  description: string
  status: 'active' | 'inactive' | 'error'
  lastRun: string | null
  successRate: number
}

export function AgentBuilder() {
  const [agents] = useState<Agent[]>([
    {
      id: 'agent-1',
      name: 'Web Researcher',
      description: 'Searches the web for information and summarizes findings',
      status: 'active',
      lastRun: '2024-01-15T10:30:00Z',
      successRate: 95,
    },
    {
      id: 'agent-2',
      name: 'File Organizer',
      description: 'Organizes files based on content analysis and naming patterns',
      status: 'active',
      lastRun: '2024-01-14T15:20:00Z',
      successRate: 88,
    },
    {
      id: 'agent-3',
      name: 'Desktop Automator',
      description: 'Performs desktop automation tasks like clicks and typing',
      status: 'inactive',
      lastRun: null,
      successRate: 0,
    },
  ])

  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-500/10 text-green-400 border-green-500/30'
      case 'error':
        return 'bg-red-500/10 text-red-400 border-red-500/30'
      default:
        return 'bg-gray-500/10 text-gray-400 border-gray-500/30'
    }
  }

  return (
    <div className="h-full flex">
      {/* Agent list */}
      <div className="w-80 border-r border-gray-800 flex flex-col">
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold">Agents</h2>
            <button className="p-2 bg-agentos-primary hover:bg-blue-600 rounded-lg transition-colors">
              <Plus className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-3">
          {agents.map((agent) => (
            <div
              key={agent.id}
              onClick={() => setSelectedAgent(agent)}
              className={`p-4 rounded-lg border cursor-pointer transition-colors ${
                selectedAgent?.id === agent.id
                  ? 'bg-agentos-primary/10 border-agentos-primary/50'
                  : 'bg-agentos-dark border-gray-800 hover:border-gray-700'
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="p-2 bg-gradient-to-br from-agentos-primary to-blue-600 rounded-lg">
                  <Bot className="w-5 h-5 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-white truncate">{agent.name}</h3>
                  <p className="text-sm text-gray-400 line-clamp-2 mt-1">{agent.description}</p>
                  <div className="flex items-center gap-2 mt-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${getStatusColor(agent.status)}`}>
                      {agent.status}
                    </span>
                    {agent.successRate > 0 && (
                      <span className="text-xs text-gray-500">
                        {agent.successRate}% success
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Agent details */}
      <div className="flex-1 overflow-auto">
        {selectedAgent ? (
          <div className="p-6">
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-agentos-primary to-blue-600 rounded-xl">
                  <Bot className="w-8 h-8 text-white" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold">{selectedAgent.name}</h1>
                  <p className="text-gray-400">{selectedAgent.description}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <button className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg font-medium transition-colors">
                  <Play className="w-4 h-4" />
                  Run
                </button>
                <button className="p-2 hover:bg-gray-800 rounded-lg transition-colors">
                  <Settings className="w-5 h-5 text-gray-400" />
                </button>
                <button className="p-2 hover:bg-gray-800 rounded-lg transition-colors">
                  <Copy className="w-5 h-5 text-gray-400" />
                </button>
                <button className="p-2 hover:bg-red-900/50 rounded-lg transition-colors">
                  <Trash2 className="w-5 h-5 text-red-400" />
                </button>
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-agentos-dark p-4 rounded-lg border border-gray-800">
                <div className="text-2xl font-bold text-green-400">{selectedAgent.successRate}%</div>
                <div className="text-sm text-gray-500">Success Rate</div>
              </div>
              <div className="bg-agentos-dark p-4 rounded-lg border border-gray-800">
                <div className="text-2xl font-bold text-blue-400">24</div>
                <div className="text-sm text-gray-500">Total Runs</div>
              </div>
              <div className="bg-agentos-dark p-4 rounded-lg border border-gray-800">
                <div className="text-2xl font-bold text-yellow-400">
                  {selectedAgent.lastRun ? new Date(selectedAgent.lastRun).toLocaleDateString() : 'Never'}
                </div>
                <div className="text-sm text-gray-500">Last Run</div>
              </div>
            </div>

            {/* Configuration */}
            <div className="bg-agentos-dark rounded-lg border border-gray-800 p-6">
              <h3 className="font-bold mb-4">Configuration</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Name</label>
                  <input
                    type="text"
                    value={selectedAgent.name}
                    readOnly
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Description</label>
                  <textarea
                    value={selectedAgent.description}
                    readOnly
                    rows={3}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white resize-none"
                  />
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Bot className="w-16 h-16 mb-4 opacity-50" />
            <p className="text-lg font-medium">Select an agent to view details</p>
          </div>
        )}
      </div>
    </div>
  )
}

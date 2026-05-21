import { useState, useEffect } from 'react'
import { useApp } from '../context/AppContext'
import { supervisorApi, type AgentConfig } from '../api/supervisor'
import { 
  Bot, 
  Plus, 
  Play, 
  Settings, 
  Trash2,
  RotateCcw,
  RefreshCw,
  AlertCircle
} from 'lucide-react'

export function AgentBuilder() {
  const { refreshTasks } = useApp()
  const [agents, setAgents] = useState<AgentConfig[]>([])
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAgents = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await supervisorApi.listAgentConfigs()
      setAgents(data)
      // Keep selection in sync if the selected agent still exists
      if (selectedAgent && !data.find(a => a.id === selectedAgent.id)) {
        setSelectedAgent(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agents')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAgents()
  }, [])

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
            <div className="flex gap-2">
              <button
                onClick={fetchAgents}
                disabled={loading}
                className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
                title="Refresh"
              >
                <RefreshCw className={`w-5 h-5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button className="p-2 bg-agentos-primary hover:bg-blue-600 rounded-lg transition-colors" title="Create Agent">
                <Plus className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-3">
          {loading && agents.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-gray-500">
              <RefreshCw className="w-5 h-5 animate-spin mr-2" />
              Loading agents...
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-8 text-red-400">
              <AlertCircle className="w-8 h-8 mb-2" />
              <p className="text-sm">{error}</p>
              <button onClick={fetchAgents} className="mt-2 text-xs text-agentos-primary hover:underline">
                Retry
              </button>
            </div>
          ) : agents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-gray-500">
              <Bot className="w-10 h-10 mb-2 opacity-50" />
              <p className="text-sm">No agents configured</p>
              <p className="text-xs mt-1">Click + to create one</p>
            </div>
          ) : (
            agents.map((agent) => (
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
                    <p className="text-sm text-gray-400 line-clamp-2 mt-1">{agent.description || 'No description'}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${getStatusColor(agent.status)}`}>
                        {agent.status}
                      </span>
                      <span className="text-xs text-gray-500">{agent.role}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
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
                  <p className="text-gray-400">{selectedAgent.description || 'No description'}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    if (!selectedAgent) return
                    setIsRunning(true)
                    try {
                      await supervisorApi.createTask(`Run agent: ${selectedAgent.name}. ${selectedAgent.description || selectedAgent.role}`)
                      await refreshTasks()
                    } catch (error) {
                      console.error('Failed to run agent:', error)
                    } finally {
                      setIsRunning(false)
                    }
                  }}
                  disabled={isRunning}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
                >
                  {isRunning ? (
                    <RotateCcw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  Run
                </button>
                <button className="p-2 hover:bg-gray-800 rounded-lg transition-colors" title="Settings">
                  <Settings className="w-5 h-5 text-gray-400" />
                </button>
                <button
                  onClick={async () => {
                    if (!selectedAgent) return
                    try {
                      await supervisorApi.deleteAgentConfig(selectedAgent.id)
                      setSelectedAgent(null)
                      await fetchAgents()
                    } catch (err) {
                      console.error('Failed to delete agent:', err)
                    }
                  }}
                  className="p-2 hover:bg-red-900/50 rounded-lg transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-5 h-5 text-red-400" />
                </button>
              </div>
            </div>

            {/* Agent info */}
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-agentos-dark p-4 rounded-lg border border-gray-800">
                <div className="text-sm text-gray-500 mb-1">Role</div>
                <div className="text-lg font-bold text-blue-400 capitalize">{selectedAgent.role}</div>
              </div>
              <div className="bg-agentos-dark p-4 rounded-lg border border-gray-800">
                <div className="text-sm text-gray-500 mb-1">Status</div>
                <div className={`text-lg font-bold capitalize ${selectedAgent.status === 'active' ? 'text-green-400' : 'text-yellow-400'}`}>
                  {selectedAgent.status}
                </div>
              </div>
              <div className="bg-agentos-dark p-4 rounded-lg border border-gray-800">
                <div className="text-sm text-gray-500 mb-1">Model</div>
                <div className="text-lg font-bold text-purple-400">{selectedAgent.model || 'Default'}</div>
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
                    value={selectedAgent.description || ''}
                    readOnly
                    rows={3}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white resize-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Temperature</label>
                    <input
                      type="text"
                      value={selectedAgent.temperature?.toFixed(1) || '0.7'}
                      readOnly
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Max Tokens</label>
                    <input
                      type="text"
                      value={selectedAgent.max_tokens?.toString() || '2048'}
                      readOnly
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Bot className="w-16 h-16 mb-4 opacity-50" />
            <p className="text-lg font-medium">Select an agent to view details</p>
            <p className="text-sm mt-1">Choose an agent from the list</p>
          </div>
        )}
      </div>
    </div>
  )
}

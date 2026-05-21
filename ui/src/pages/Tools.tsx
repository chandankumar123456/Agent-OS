import { useState, useEffect } from 'react'
import { useApp } from '../context/AppContext'
import { supervisorApi, type ToolDef } from '../api/supervisor'
import { 
  Wrench, 
  Play, 
  CheckCircle,
  AlertCircle,
  Terminal,
  FileText,
  Globe,
  Monitor,
  FolderOpen,
  RotateCcw,
  RefreshCw
} from 'lucide-react'

export function Tools() {
  const { refreshTasks } = useApp()
  const [tools, setTools] = useState<ToolDef[]>([])
  const [categories, setCategories] = useState<string[]>(['All'])
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [searchQuery, setSearchQuery] = useState('')
  const [testingTool, setTestingTool] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTools = async () => {
    setLoading(true)
    setError(null)
    try {
      const [toolsData, catsData] = await Promise.all([
        supervisorApi.listTools(selectedCategory === 'All' ? undefined : selectedCategory),
        supervisorApi.listToolCategories(),
      ])
      setTools(toolsData)
      setCategories(catsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tools')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTools()
  }, [selectedCategory])

  const filteredTools = tools.filter(tool => {
    if (searchQuery === '') return true
    const q = searchQuery.toLowerCase()
    return tool.name.toLowerCase().includes(q) ||
           tool.description.toLowerCase().includes(q)
  })

  const handleTestTool = async (tool: ToolDef) => {
    setTestingTool(tool.id)
    try {
      await supervisorApi.createTask(`Test tool: ${tool.name} (${tool.category}) - ${tool.description}`)
      await refreshTasks()
    } catch (error) {
      console.error('Failed to test tool:', error)
    } finally {
      setTestingTool(null)
    }
  }

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'Filesystem':
        return <FolderOpen className="w-4 h-4" />
      case 'Shell':
        return <Terminal className="w-4 h-4" />
      case 'Cloud API':
        return <Globe className="w-4 h-4" />
      case 'Desktop':
        return <Monitor className="w-4 h-4" />
      case 'Document':
        return <FileText className="w-4 h-4" />
      default:
        return <Wrench className="w-4 h-4" />
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'available':
        return <CheckCircle className="w-4 h-4 text-green-400" />
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-400" />
      default:
        return <AlertCircle className="w-4 h-4 text-gray-400" />
    }
  }

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <div className="w-64 border-r border-gray-800 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold">Categories</h3>
          <button onClick={fetchTools} disabled={loading} className="p-1 hover:bg-gray-800 rounded" title="Refresh">
            <RefreshCw className={`w-4 h-4 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div className="space-y-1">
          {categories.map((category) => (
            <button
              key={category}
              onClick={() => setSelectedCategory(category)}
              className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                selectedCategory === category
                  ? 'bg-agentos-primary/20 text-agentos-primary'
                  : 'text-gray-400 hover:bg-gray-800'
              }`}
            >
              {category}
            </button>
          ))}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-2xl font-bold">Tools</h2>
              <p className="text-gray-400 mt-1">Manage and test available tools</p>
            </div>
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tools..."
            className="w-full bg-agentos-dark border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-agentos-primary"
          />
        </div>

        {/* Tool grid */}
        <div className="flex-1 overflow-auto p-6">
          {loading && tools.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-gray-500">
              <RefreshCw className="w-6 h-6 animate-spin mr-3" />
              Loading tools...
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-16 text-red-400">
              <AlertCircle className="w-10 h-10 mb-3" />
              <p>{error}</p>
              <button onClick={fetchTools} className="mt-3 text-sm text-agentos-primary hover:underline">
                Retry
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredTools.map((tool) => (
                <div
                  key={tool.id}
                  className="bg-agentos-dark border border-gray-800 rounded-lg p-4 hover:border-agentos-primary/50 transition-colors"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-agentos-primary/10 rounded-lg text-agentos-primary">
                        {getCategoryIcon(tool.category)}
                      </div>
                      <div>
                        <h3 className="font-medium text-white">{tool.name}</h3>
                        <span className="text-xs text-gray-500">{tool.category}</span>
                      </div>
                    </div>
                    {getStatusIcon(tool.status)}
                  </div>
                  <p className="text-sm text-gray-400 mb-4">{tool.description}</p>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-500">{tool.type}</span>
                    <button
                      onClick={() => handleTestTool(tool)}
                      disabled={testingTool === tool.id}
                      className="flex items-center gap-1 px-3 py-1.5 bg-agentos-primary/10 hover:bg-agentos-primary/20 disabled:bg-gray-800 disabled:cursor-not-allowed text-agentos-primary rounded-lg text-sm transition-colors"
                    >
                      {testingTool === tool.id ? (
                        <RotateCcw className="w-3 h-3 animate-spin" />
                      ) : (
                        <Play className="w-3 h-3" />
                      )}
                      Test
                    </button>
                  </div>
                </div>
              ))}
              {!loading && filteredTools.length === 0 && (
                <div className="col-span-full flex flex-col items-center justify-center py-16 text-gray-500">
                  <Wrench className="w-12 h-12 mb-3 opacity-50" />
                  <p className="text-lg font-medium">No tools found</p>
                  <p className="text-sm mt-1">
                    {searchQuery ? 'Try a different search term' : 'No tools available in this category'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

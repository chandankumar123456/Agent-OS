import { useState } from 'react'
import { 
  Wrench, 
  Play, 
  CheckCircle,
  AlertCircle,
  Terminal,
  FileText,
  Globe,
  Monitor,
  FolderOpen
} from 'lucide-react'

interface Tool {
  id: string
  name: string
  description: string
  category: string
  status: 'available' | 'unavailable' | 'error'
  lastUsed: string | null
}

const tools: Tool[] = [
  { id: '1', name: 'Read File', description: 'Read contents of a file', category: 'Filesystem', status: 'available', lastUsed: '2024-01-15' },
  { id: '2', name: 'Write File', description: 'Write content to a file', category: 'Filesystem', status: 'available', lastUsed: '2024-01-14' },
  { id: '3', name: 'Execute Command', description: 'Run shell commands', category: 'Shell', status: 'available', lastUsed: '2024-01-15' },
  { id: '4', name: 'Search Web', description: 'Search the web using DuckDuckGo', category: 'Cloud API', status: 'available', lastUsed: null },
  { id: '5', name: 'Navigate Browser', description: 'Navigate to a URL in browser', category: 'Browser', status: 'available', lastUsed: '2024-01-13' },
  { id: '6', name: 'Screenshot', description: 'Take a screenshot', category: 'Desktop', status: 'available', lastUsed: '2024-01-15' },
  { id: '7', name: 'Click Element', description: 'Click at screen coordinates', category: 'Desktop', status: 'available', lastUsed: null },
  { id: '8', name: 'Type Text', description: 'Type text at current cursor', category: 'Desktop', status: 'available', lastUsed: null },
  { id: '9', name: 'Parse Document', description: 'Parse PDF/DOCX/TXT files', category: 'Document', status: 'available', lastUsed: '2024-01-12' },
  { id: '10', name: 'Execute Python', description: 'Execute Python code safely', category: 'Code', status: 'available', lastUsed: null },
]

const categories = ['All', 'Filesystem', 'Shell', 'Cloud API', 'Browser', 'Desktop', 'Document', 'Code']

export function Tools() {
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [searchQuery, setSearchQuery] = useState('')

  const filteredTools = tools.filter(tool => {
    const matchesCategory = selectedCategory === 'All' || tool.category === selectedCategory
    const matchesSearch = tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          tool.description.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesCategory && matchesSearch
  })

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
        <h3 className="font-bold mb-4">Categories</h3>
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
                  <span className="text-xs text-gray-500">
                    {tool.lastUsed ? `Last used: ${tool.lastUsed}` : 'Never used'}
                  </span>
                  <button className="flex items-center gap-1 px-3 py-1.5 bg-agentos-primary/10 hover:bg-agentos-primary/20 text-agentos-primary rounded-lg text-sm transition-colors">
                    <Play className="w-3 h-3" />
                    Test
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

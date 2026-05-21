import { 
  LayoutDashboard, 
  Bot, 
  Wrench, 
  MessageSquare, 
  Settings,
  Circle
} from 'lucide-react'

type Page = 'dashboard' | 'agents' | 'tools' | 'chat' | 'settings'

interface SidebarItemProps {
  icon: React.ReactNode
  label: string
  active: boolean
  onClick: () => void
}

function SidebarItem({ icon, label, active, onClick }: SidebarItemProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
        active
          ? 'bg-agentos-primary/20 text-agentos-primary border border-agentos-primary/30'
          : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
      }`}
    >
      {icon}
      <span className="font-medium">{label}</span>
    </button>
  )
}

export function Layout({ 
  children, 
  currentPage, 
  onNavigate, 
  daemonConnected 
}: { 
  children: React.ReactNode
  currentPage: Page
  onNavigate: (page: Page) => void
  daemonConnected: boolean
}) {
  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-64 bg-agentos-dark border-r border-gray-800 flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-agentos-primary to-blue-600 flex items-center justify-center">
              <Bot className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-lg">AgentOS</h1>
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <Circle className={`w-2 h-2 ${daemonConnected ? 'fill-green-500 text-green-500' : 'fill-red-500 text-red-500'}`} />
                <span>{daemonConnected ? 'Connected' : 'Disconnected'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          <SidebarItem
            icon={<LayoutDashboard className="w-5 h-5" />}
            label="Dashboard"
            active={currentPage === 'dashboard'}
            onClick={() => onNavigate('dashboard')}
          />
          <SidebarItem
            icon={<Bot className="w-5 h-5" />}
            label="Agents"
            active={currentPage === 'agents'}
            onClick={() => onNavigate('agents')}
          />
          <SidebarItem
            icon={<Wrench className="w-5 h-5" />}
            label="Tools"
            active={currentPage === 'tools'}
            onClick={() => onNavigate('tools')}
          />
          <SidebarItem
            icon={<MessageSquare className="w-5 h-5" />}
            label="Chat"
            active={currentPage === 'chat'}
            onClick={() => onNavigate('chat')}
          />
        </nav>

        {/* Bottom section */}
        <div className="p-4 border-t border-gray-800">
          <SidebarItem
            icon={<Settings className="w-5 h-5" />}
            label="Settings"
            active={currentPage === 'settings'}
            onClick={() => onNavigate('settings')}
          />
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  )
}

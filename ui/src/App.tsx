import { useState, useEffect } from 'react'
import { invoke } from '@tauri-apps/api/tauri'
import { getVersion } from '@tauri-apps/api/app'
import { Dashboard, AgentBuilder, Tools, Chat, Settings } from './pages'
import { Layout } from './components/Layout'
import { AppProvider } from './context/AppContext'
import './App.css'

type Page = 'dashboard' | 'agents' | 'tools' | 'chat' | 'settings'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard')
  const [version, setVersion] = useState<string>('')
  const [daemonConnected, setDaemonConnected] = useState(false)

  useEffect(() => {
    // Get app version
    getVersion().then(setVersion).catch(console.error)
    
    // Check daemon status
    checkDaemonStatus()
    const interval = setInterval(checkDaemonStatus, 5000)
    
    return () => clearInterval(interval)
  }, [])

  const checkDaemonStatus = async () => {
    try {
      const status = await invoke<{ running: boolean }>('get_daemon_status')
      setDaemonConnected(status.running)
    } catch (error) {
      setDaemonConnected(false)
    }
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <Dashboard />
      case 'agents':
        return <AgentBuilder />
      case 'tools':
        return <Tools />
      case 'chat':
        return <Chat />
      case 'settings':
        return <Settings version={version} daemonConnected={daemonConnected} />
      default:
        return <Dashboard />
    }
  }

  return (
    <AppProvider>
      <div className="h-screen w-screen bg-agentos-darker text-white overflow-hidden">
        <Layout
          currentPage={currentPage}
          onNavigate={setCurrentPage}
          daemonConnected={daemonConnected}
        >
          {renderPage()}
        </Layout>
      </div>
    </AppProvider>
  )
}

export default App

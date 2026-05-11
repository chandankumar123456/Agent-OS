import { useState, useEffect } from 'react'
import { invoke } from '@tauri-apps/api/tauri'
import { 
  Settings as SettingsIcon, 
  Bell, 
  Keyboard, 
  Server,
  Info,
  CheckCircle,
  XCircle,
  Key
} from 'lucide-react'

interface SettingsPageProps {
  version: string
  daemonConnected: boolean
}

export function Settings({ version, daemonConnected }: SettingsPageProps) {
  const [config, setConfig] = useState({
    autoStartDaemon: true,
    startMinimized: false,
    notificationsEnabled: true,
    globalShortcutsEnabled: true,
    daemonHost: '127.0.0.1',
    daemonPort: 8080,
  })
  const [saved, setSaved] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [apiKeySaved, setApiKeySaved] = useState(false)
  const [apiKeyLoading, setApiKeyLoading] = useState(false)

  useEffect(() => {
    // Load existing API key on mount
    loadApiKey()
  }, [])

  const loadApiKey = async () => {
    try {
      const result = await invoke<{ success: boolean; value?: string; error?: string }>('get_secret', { key: 'OPENAI_API_KEY' })
      if (result.success && result.value) {
        setApiKey('••••••••••••••••')
        setApiKeySaved(true)
      }
    } catch (error) {
      console.error('Failed to load API key:', error)
    }
  }

  const handleSaveApiKey = async () => {
    if (!apiKey || apiKey === '••••••••••••••••') return
    setApiKeyLoading(true)
    try {
      const result = await invoke<{ success: boolean; error?: string }>('set_secret', { key: 'OPENAI_API_KEY', value: apiKey })
      if (result.success) {
        setApiKey('••••••••••••••••')
        setApiKeySaved(true)
      } else {
        console.error('Failed to save API key:', result.error)
      }
    } catch (error) {
      console.error('Failed to save API key:', error)
    } finally {
      setApiKeyLoading(false)
    }
  }

  const handleDeleteApiKey = async () => {
    setApiKeyLoading(true)
    try {
      const result = await invoke<{ success: boolean; error?: string }>('delete_secret', { key: 'OPENAI_API_KEY' })
      if (result.success) {
        setApiKey('')
        setApiKeySaved(false)
      } else {
        console.error('Failed to delete API key:', result.error)
      }
    } catch (error) {
      console.error('Failed to delete API key:', error)
    } finally {
      setApiKeyLoading(false)
    }
  }

  const handleSave = async () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-3xl mx-auto p-6">
        <h2 className="text-2xl font-bold mb-6">Settings</h2>

        {/* Daemon Section */}
        <div className="bg-agentos-dark rounded-lg border border-gray-800 p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <Server className="w-5 h-5 text-agentos-primary" />
            <h3 className="text-lg font-bold">Daemon</h3>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="font-medium">Auto-start Daemon</label>
                <p className="text-sm text-gray-500">Start the supervisor daemon when AgentOS launches</p>
              </div>
              <button
                onClick={() => setConfig({ ...config, autoStartDaemon: !config.autoStartDaemon })}
                className={`w-12 h-6 rounded-full transition-colors relative ${
                  config.autoStartDaemon ? 'bg-agentos-primary' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                    config.autoStartDaemon ? 'left-7' : 'left-1'
                  }`}
                />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Host</label>
                <input
                  type="text"
                  value={config.daemonHost}
                  onChange={(e) => setConfig({ ...config, daemonHost: e.target.value })}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-agentos-primary"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Port</label>
                <input
                  type="number"
                  value={config.daemonPort}
                  onChange={(e) => setConfig({ ...config, daemonPort: parseInt(e.target.value) })}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-agentos-primary"
                />
              </div>
            </div>

            <div className="flex items-center gap-2 p-4 bg-gray-900 rounded-lg">
              {daemonConnected ? (
                <>
                  <CheckCircle className="w-5 h-5 text-green-400" />
                  <span className="text-green-400">Connected to daemon</span>
                </>
              ) : (
                <>
                  <XCircle className="w-5 h-5 text-red-400" />
                  <span className="text-red-400">Disconnected from daemon</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* API Keys Section */}
        <div className="bg-agentos-dark rounded-lg border border-gray-800 p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <Key className="w-5 h-5 text-agentos-primary" />
            <h3 className="text-lg font-bold">API Keys</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">OpenAI API Key</label>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => { setApiKey(e.target.value); setApiKeySaved(false) }}
                  placeholder={apiKeySaved ? '••••••••••••••••' : 'Enter your API key'}
                  className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-agentos-primary"
                />
                {apiKeySaved ? (
                  <button
                    onClick={handleDeleteApiKey}
                    disabled={apiKeyLoading}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 text-white rounded-lg font-medium transition-colors"
                  >
                    {apiKeyLoading ? '...' : 'Remove'}
                  </button>
                ) : (
                  <button
                    onClick={handleSaveApiKey}
                    disabled={apiKeyLoading || !apiKey}
                    className="px-4 py-2 bg-agentos-primary hover:bg-blue-600 disabled:bg-gray-700 text-white rounded-lg font-medium transition-colors"
                  >
                    {apiKeyLoading ? 'Saving...' : 'Save'}
                  </button>
                )}
              </div>
              {apiKeySaved && (
                <p className="text-xs text-green-400 mt-1">API key stored securely in OS keychain</p>
              )}
              <p className="text-xs text-gray-500 mt-1">
                Your API key is stored in the OS credential manager (Windows Credential Manager / macOS Keychain / Linux Secret Service)
              </p>
            </div>
          </div>
        </div>

        {/* Notifications Section */}
        <div className="bg-agentos-dark rounded-lg border border-gray-800 p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <Bell className="w-5 h-5 text-agentos-primary" />
            <h3 className="text-lg font-bold">Notifications</h3>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="font-medium">Enable Notifications</label>
              <p className="text-sm text-gray-500">Show system notifications for task events</p>
            </div>
            <button
              onClick={() => setConfig({ ...config, notificationsEnabled: !config.notificationsEnabled })}
              className={`w-12 h-6 rounded-full transition-colors relative ${
                config.notificationsEnabled ? 'bg-agentos-primary' : 'bg-gray-700'
              }`}
            >
              <span
                className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                  config.notificationsEnabled ? 'left-7' : 'left-1'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Shortcuts Section */}
        <div className="bg-agentos-dark rounded-lg border border-gray-800 p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <Keyboard className="w-5 h-5 text-agentos-primary" />
            <h3 className="text-lg font-bold">Global Shortcuts</h3>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="font-medium">Enable Global Shortcuts</label>
                <p className="text-sm text-gray-500">Use system-wide keyboard shortcuts</p>
              </div>
              <button
                onClick={() => setConfig({ ...config, globalShortcutsEnabled: !config.globalShortcutsEnabled })}
                className={`w-12 h-6 rounded-full transition-colors relative ${
                  config.globalShortcutsEnabled ? 'bg-agentos-primary' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                    config.globalShortcutsEnabled ? 'left-7' : 'left-1'
                  }`}
                />
              </button>
            </div>

            <div className="bg-gray-900 rounded-lg p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Show AgentOS</span>
                <span className="font-mono bg-gray-800 px-2 py-1 rounded">Ctrl + Shift + A</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Take Screenshot</span>
                <span className="font-mono bg-gray-800 px-2 py-1 rounded">Ctrl + Shift + S</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Quick Task</span>
                <span className="font-mono bg-gray-800 px-2 py-1 rounded">Ctrl + Shift + Q</span>
              </div>
            </div>
          </div>
        </div>

        {/* Window Section */}
        <div className="bg-agentos-dark rounded-lg border border-gray-800 p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <SettingsIcon className="w-5 h-5 text-agentos-primary" />
            <h3 className="text-lg font-bold">Window</h3>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="font-medium">Start Minimized</label>
              <p className="text-sm text-gray-500">Start AgentOS minimized to system tray</p>
            </div>
            <button
              onClick={() => setConfig({ ...config, startMinimized: !config.startMinimized })}
              className={`w-12 h-6 rounded-full transition-colors relative ${
                config.startMinimized ? 'bg-agentos-primary' : 'bg-gray-700'
              }`}
            >
              <span
                className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                  config.startMinimized ? 'left-7' : 'left-1'
                }`}
              />
            </button>
          </div>
        </div>

        {/* About Section */}
        <div className="bg-agentos-dark rounded-lg border border-gray-800 p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <Info className="w-5 h-5 text-agentos-primary" />
            <h3 className="text-lg font-bold">About</h3>
          </div>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Version</span>
              <span>{version}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Build</span>
              <span>2024.01.15</span>
            </div>
            <div className="pt-4 border-t border-gray-800">
              <p className="text-gray-500">
                AgentOS - Local-native autonomous agent runtime
              </p>
              <p className="text-gray-500 mt-1">
                © 2024 AgentOS Team
              </p>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            className="px-6 py-3 bg-agentos-primary hover:bg-blue-600 text-white rounded-lg font-medium transition-colors"
          >
            {saved ? 'Saved!' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

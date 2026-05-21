import { useState } from 'react'
import { supervisorApi } from '../api/supervisor'
import { Shield, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import type { Task } from '../api/supervisor'

interface SafetyDialogProps {
  task: Task
  onApprove: () => void
  onReject: () => void
}

export function SafetyDialog({ task, onApprove, onReject }: SafetyDialogProps) {
  const [reason, setReason] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleApprove = async () => {
    setIsSubmitting(true)
    try {
      await supervisorApi.approveTask(task.id, reason || 'Approved by user')
      onApprove()
    } catch (error) {
      console.error('Failed to approve task:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReject = async () => {
    setIsSubmitting(true)
    try {
      await supervisorApi.rejectTask(task.id, reason || 'Rejected by user')
      onReject()
    } catch (error) {
      console.error('Failed to reject task:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-agentos-dark border border-yellow-500/30 rounded-xl max-w-lg w-full p-6 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-yellow-500/10 rounded-lg">
            <Shield className="w-6 h-6 text-yellow-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-yellow-400">Action Approval Required</h3>
            <p className="text-sm text-gray-400">Task {task.id.slice(0, 8)} is awaiting your approval</p>
          </div>
        </div>

        <div className="bg-gray-900 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-yellow-400 mt-0.5" />
            <div>
              <p className="text-white font-medium">{task.query}</p>
              <p className="text-sm text-gray-400 mt-1">
                This task may perform desktop automation actions. Please review before approving.
              </p>
            </div>
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-1">Reason (optional)</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Add a note about your decision..."
            rows={2}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-agentos-primary resize-none"
          />
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleReject}
            disabled={isSubmitting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 text-white rounded-lg font-medium transition-colors"
          >
            <XCircle className="w-5 h-5" />
            Reject
          </button>
          <button
            onClick={handleApprove}
            disabled={isSubmitting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 text-white rounded-lg font-medium transition-colors"
          >
            <CheckCircle className="w-5 h-5" />
            Approve
          </button>
        </div>
      </div>
    </div>
  )
}

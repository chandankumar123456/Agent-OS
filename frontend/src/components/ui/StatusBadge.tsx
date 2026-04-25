import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, Loader2, XCircle, Clock } from 'lucide-react';
import { badgeVariants } from '../../lib/animations';

type StatusType = 'completed' | 'failed' | 'running' | 'pending' | 'cancelled' | 'waiting_approval';

interface StatusBadgeProps {
  status: StatusType | string;
  showIcon?: boolean;
  className?: string;
}

const statusConfig: Record<string, { icon: React.ElementType; bg: string; text: string; label: string }> = {
  completed: { icon: CheckCircle2, bg: 'bg-[#00FF88]/10', text: 'text-[#00FF88]', label: 'completed' },
  failed: { icon: XCircle, bg: 'bg-[#FF4B4B]/10', text: 'text-[#FF4B4B]', label: 'failed' },
  running: { icon: Loader2, bg: 'bg-primary/10', text: 'text-primary', label: 'running' },
  pending: { icon: Clock, bg: 'bg-secondaryText/10', text: 'text-secondaryText', label: 'pending' },
  cancelled: { icon: XCircle, bg: 'bg-secondaryText/10', text: 'text-secondaryText', label: 'cancelled' },
  waiting_approval: { icon: Clock, bg: 'bg-yellow-400/10', text: 'text-yellow-400', label: 'waiting' },
};

/**
 * Animated status badge with color crossfade and icon spin.
 * Wraps AnimatePresence for smooth status transitions.
 */
export function StatusBadge({ status, showIcon = true, className = '' }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.pending;
  const Icon = config.icon;
  const isRunning = status === 'running';

  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={status}
        variants={badgeVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        className={`inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest px-2.5 py-1 rounded-md ${config.bg} ${config.text} ${className}`}
      >
        {showIcon && (
          <Icon className={`w-3 h-3 ${isRunning ? 'animate-spin' : ''}`} />
        )}
        {config.label}
      </motion.span>
    </AnimatePresence>
  );
}

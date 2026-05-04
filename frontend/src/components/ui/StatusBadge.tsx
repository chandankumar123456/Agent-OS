import { motion, AnimatePresence } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { badgeVariants } from '../../lib/animations';

type StatusType = 'completed' | 'failed' | 'running' | 'pending' | 'cancelled' | 'waiting_approval';

interface StatusBadgeProps {
 status: StatusType | string;
 showIcon?: boolean;
 className?: string;
}

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
 completed: { bg: 'bg-secondary', text: 'text-white', label: 'OK' },
 failed: { bg: 'bg-[#FF4B4B]', text: 'text-white', label: 'ERR' },
 running: { bg: 'bg-primary', text: 'text-white', label: 'RUN' },
 pending: { bg: 'bg-white', text: 'text-outline', label: '...' },
 cancelled: { bg: 'bg-white', text: 'text-secondaryText', label: 'STOP' },
 waiting_approval: { bg: 'bg-accent-yellow', text: 'text-primaryText', label: 'WAIT' },
};

/**
 * Animated status badge with color crossfade and icon spin.
 * Wraps AnimatePresence for smooth status transitions.
 */
export function StatusBadge({ status, showIcon = true, className = '' }: StatusBadgeProps) {
 const config = statusConfig[status] || statusConfig.pending;
 const isRunning = status === 'running';

 return (
 <AnimatePresence mode="wait">
 <motion.span
 key={status}
 variants={badgeVariants}
 initial="initial"
 animate="animate"
 exit="exit"
 className={`inline-flex items-center gap-1.5 text-[8px] font-pixel uppercase tracking-tighter px-2 py-1 border-4 border-outline shadow-[2px_2px_0px_rgba(0,0,0,0.1)] ${config.bg} ${config.text} ${className}`}
 >
 {showIcon && isRunning && (
 <Loader2 className="w-2 h-2 animate-spin" />
 )}
 {config.label}
 </motion.span>
 </AnimatePresence>
 );
}

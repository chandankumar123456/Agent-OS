import React from 'react';
import { motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';
import { buttonTap } from '../lib/animations';

interface EmptyStateProps {
 icon: LucideIcon;
 title: string;
 description: string;
 actionLabel?: string;
 actionHref?: string;
 onAction?: () => void;
}

const EmptyState: React.FC<EmptyStateProps> = ({
 icon: Icon,
 title,
 description,
 actionLabel,
 actionHref,
 onAction,
}) => {
 return (
 <motion.div
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 transition={{ duration: 0.1 }}
 className="flex flex-col items-center justify-center text-center py-8 px-6 bg-white border-4 border-outline shadow-pixel"
 >
 <motion.div
 initial={{ scale: 0.8, opacity: 0 }}
 animate={{ scale: 1, opacity: 1 }}
 transition={{ delay: 0.05, duration: 0.1 }}
 className="w-24 h-24 border-4 border-outline bg-surface-high flex items-center justify-center mb-8 shadow-pixel"
 >
 <Icon className="w-12 h-12 text-primary" />
 </motion.div>
 <h3 className="text-xl font-pixel uppercase text-primaryText mb-4 tracking-tighter">{title}</h3>
 <p className="text-lg text-secondaryText max-w-sm mb-8 leading-relaxed font-retro">
 {description}
 </p>
 {actionLabel && (actionHref || onAction) && (
 <motion.a
 href={actionHref || '#'}
 onClick={(e) => {
 if (onAction) {
 e.preventDefault();
 onAction();
 }
 }}
 {...buttonTap}
 className="btn-primary flex items-center gap-2"
 >
 {actionLabel}
 </motion.a>
 )}
 </motion.div>
 );
};

export default EmptyState;

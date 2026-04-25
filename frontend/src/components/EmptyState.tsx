import React from 'react';
import { motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';

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
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      className="flex flex-col items-center justify-center text-center py-16 px-6 bg-surface-low border border-outline/10 rounded-2xl"
    >
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.1, type: 'spring', stiffness: 400 }}
        className="w-20 h-20 rounded-2xl bg-surface-highest border border-outline/10 flex items-center justify-center mb-6"
      >
        <Icon className="w-10 h-10 text-primary/60" />
      </motion.div>
      <h3 className="text-lg font-semibold text-primaryText mb-2">{title}</h3>
      <p className="text-sm text-secondaryText max-w-sm mb-6 leading-relaxed">
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
          whileTap={{ scale: 0.96 }}
          whileHover={{ scale: 1.02 }}
          className="btn-primary flex items-center gap-2"
        >
          {actionLabel}
        </motion.a>
      )}
    </motion.div>
  );
};

export default EmptyState;

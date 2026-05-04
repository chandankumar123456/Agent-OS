import { motion } from 'framer-motion';
import { skeletonVariants } from '../../lib/animations';

interface SkeletonProps {
 className?: string;
 variant?: 'rect' | 'circle' | 'text';
 lines?: number;
}

/**
 * Shimmer skeleton loader.
 * Use variant="text" with lines for multi-line placeholder.
 */
export function Skeleton({ className = '', variant = 'rect', lines = 1 }: SkeletonProps) {
 const baseClass = 'bg-surface-highest border-4 border-outline/10';

 if (variant === 'circle') {
 return (
 <motion.div
 variants={skeletonVariants}
 animate="animate"
 className={`${baseClass} ${className}`} // No circle in pixel retro
 />
 );
 }

 if (variant === 'text') {
 return (
 <div className={`flex flex-col gap-2 ${className}`}>
 {Array.from({ length: lines }).map((_, i) => (
 <motion.div
 key={i}
 variants={skeletonVariants}
 animate="animate"
 className={`${baseClass} h-4`}
 style={{ width: i === lines - 1 ? '70%' : '100%' }}
 />
 ))}
 </div>
 );
 }

 return (
 <motion.div
 variants={skeletonVariants}
 animate="animate"
 className={`${baseClass} ${className}`}
 />
 );
}

/** Skeleton card for stat panels, task cards, etc. */
export function SkeletonCard({ className = '' }: { className?: string }) {
 return (
 <div className={`pixel-card p-6 ${className}`}>
 <div className="flex justify-between items-start mb-6">
 <Skeleton className="h-4 w-24" />
 <Skeleton className="w-5 h-5" />
 </div>
 <Skeleton className="h-10 w-24 mb-4" />
 <Skeleton className="h-3 w-32" />
 </div>
 );
}

/** Skeleton for task list items */
export function SkeletonTaskItem() {
 return (
 <div className="flex items-center gap-4 p-6 border-4 border-outline bg-white">
 <Skeleton className="w-6 h-6" />
 <div className="flex-1 space-y-2">
 <Skeleton className="h-3 w-3/4" />
 <Skeleton className="h-2 w-1/2" />
 </div>
 <Skeleton className="h-6 w-16" />
 </div>
 );
}

/** Dashboard stats grid skeleton */
export function SkeletonStatsGrid() {
 return (
 <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
 {Array.from({ length: 4 }).map((_, i) => (
 <SkeletonCard key={i} />
 ))}
 </div>
 );
}

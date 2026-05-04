import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from 'lucide-react';

type ToastVariant = 'success' | 'error' | 'warning' | 'info';

interface Toast {
 id: string;
 message: string;
 variant: ToastVariant;
 duration: number;
}

interface ToastContextValue {
 showToast: (message: string, variant?: ToastVariant, duration?: number) => void;
 dismissToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const variantConfig: Record<ToastVariant, { icon: React.ElementType; borderColor: string; textColor: string; bgColor: string }> = {
 success: {
 icon: CheckCircle2,
 borderColor: 'border-[#00FF88]/20',
 textColor: 'text-[#00FF88]',
 bgColor: 'bg-[#00FF88]/10',
 },
 error: {
 icon: AlertCircle,
 borderColor: 'border-[#FF4B4B]/20',
 textColor: 'text-[#FF4B4B]',
 bgColor: 'bg-[#FF4B4B]/10',
 },
 warning: {
 icon: AlertTriangle,
 borderColor: 'border-yellow-400/20',
 textColor: 'text-yellow-400',
 bgColor: 'bg-yellow-400/10',
 },
 info: {
 icon: Info,
 borderColor: 'border-primary/20',
 textColor: 'text-primary',
 bgColor: 'bg-primary/10',
 },
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
 const [toasts, setToasts] = useState<Toast[]>([]);
 const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

 const dismissToast = useCallback((id: string) => {
 setToasts((prev) => prev.filter((t) => t.id !== id));
 if (timersRef.current[id]) {
 clearTimeout(timersRef.current[id]);
 delete timersRef.current[id];
 }
 }, []);

 const showToast = useCallback(
 (message: string, variant: ToastVariant = 'info', duration: number = 5000) => {
 const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
 const toast: Toast = { id, message, variant, duration };
 setToasts((prev) => [...prev, toast]);
 timersRef.current[id] = setTimeout(() => {
 dismissToast(id);
 }, duration);
 },
 [dismissToast]
 );

 useEffect(() => {
 return () => {
 Object.values(timersRef.current).forEach(clearTimeout);
 };
 }, []);

 return (
 <ToastContext.Provider value={{ showToast, dismissToast }}>
 {children}
 <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
 <AnimatePresence mode="popLayout">
 {toasts.map((toast) => {
 const config = variantConfig[toast.variant];
 const Icon = config.icon;
 return (
 <motion.div
 key={toast.id}
 layout
 initial={{ opacity: 0, y: 20, scale: 0.95 }}
 animate={{ opacity: 1, y: 0, scale: 1 }}
 exit={{ opacity: 0, x: 20, scale: 0.9 }}
 transition={{ type: 'spring', stiffness: 400, damping: 25 }}
 className={`pointer-events-auto min-w-[280px] max-w-sm px-4 py-4 rounded-none border ${config.borderColor} ${config.bgColor} backdrop-blur-sm shadow-pixel flex items-start gap-3`}
 >
 <Icon className={`w-5 h-5 mt-1 shrink-0 ${config.textColor}`} />
 <span className="text-sm text-primaryText flex-1">{toast.message}</span>
 <motion.button
 onClick={() => dismissToast(toast.id)}
 whileTap={{ scale: 0.95 }}
 className="text-secondaryText hover:text-primaryText shrink-0"
 aria-label="Dismiss toast"
 >
 <X className="w-4 h-4" />
 </motion.button>
 </motion.div>
 );
 })}
 </AnimatePresence>
 </div>
 </ToastContext.Provider>
 );
};

export const useToast = (): ToastContextValue => {
 const ctx = useContext(ToastContext);
 if (!ctx) {
 throw new Error('useToast must be used within a ToastProvider');
 }
 return ctx;
};

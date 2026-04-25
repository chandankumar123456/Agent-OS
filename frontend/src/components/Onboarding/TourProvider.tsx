import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronRight } from 'lucide-react';

interface TourProviderProps {
  tourId: string;
  steps: any[];
  onComplete?: () => void;
}

export const TourProvider: React.FC<TourProviderProps> = ({ tourId, steps, onComplete }) => {
  const [current, setCurrent] = useState<number>(-1);
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    const hasSeen = localStorage.getItem(`tour_${tourId}`);
    if (hasSeen || steps.length === 0) return;

    timerRef.current = window.setTimeout(() => {
      setCurrent(0);
      setVisible(true);
    }, 800);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [tourId, steps.length]);

  const handleNext = () => {
    if (current < steps.length - 1) {
      setCurrent((c) => c + 1);
    } else {
      finish();
    }
  };

  const handleSkip = () => {
    finish();
  };

  const finish = () => {
    localStorage.setItem(`tour_${tourId}`, 'true');
    setVisible(false);
    onComplete?.();
  };

  const step = steps[current];

  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!visible || !step?.attachTo?.element) {
      setTargetRect(null);
      return;
    }
    const el = document.querySelector(step.attachTo.element);
    if (el) {
      setTargetRect(el.getBoundingClientRect());
    } else {
      setTargetRect(null);
    }
  }, [visible, current, step]);

  if (!visible || !step) return null;

  const placement = step.attachTo?.on || 'bottom';

  const tooltipStyle: React.CSSProperties = { position: 'fixed', zIndex: 9999 };
  const padding = 12;

  if (targetRect) {
    if (placement === 'right') {
      tooltipStyle.left = targetRect.right + padding;
      tooltipStyle.top = targetRect.top + targetRect.height / 2;
      tooltipStyle.transform = 'translateY(-50%)';
    } else if (placement === 'left') {
      tooltipStyle.left = targetRect.left - padding;
      tooltipStyle.top = targetRect.top + targetRect.height / 2;
      tooltipStyle.transform = 'translate(-100%, -50%)';
    } else if (placement === 'top') {
      tooltipStyle.left = targetRect.left + targetRect.width / 2;
      tooltipStyle.top = targetRect.top - padding;
      tooltipStyle.transform = 'translate(-50%, -100%)';
    } else {
      tooltipStyle.left = targetRect.left + targetRect.width / 2;
      tooltipStyle.top = targetRect.bottom + padding;
      tooltipStyle.transform = 'translateX(-50%)';
    }
  } else {
    tooltipStyle.left = '50%';
    tooltipStyle.top = '50%';
    tooltipStyle.transform = 'translate(-50%, -50%)';
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/40 z-[9998]"
        onClick={handleSkip}
      />
      <motion.div
        layout
        initial={{ opacity: 0, scale: 0.95, y: placement === 'bottom' ? 8 : placement === 'top' ? -8 : 0 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        className="bg-surface-high border border-outline/20 rounded-xl shadow-lg p-4 w-80 text-primaryText"
        style={tooltipStyle}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={step.id ?? current}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.25 }}
          >
            <div className="flex items-start justify-between mb-2">
              <h4 className="font-semibold text-sm">{step.title}</h4>
              <motion.button onClick={handleSkip} whileTap={{ scale: 0.96 }} className="text-secondaryText hover:text-primaryText">
                <X className="w-4 h-4" />
              </motion.button>
            </div>
            <p className="text-sm text-secondaryText mb-4 leading-relaxed">{step.text}</p>
            <div className="flex items-center justify-between">
              <span className="text-xs text-secondaryText">
                {current + 1} / {steps.length}
              </span>
              <div className="flex gap-2">
                <motion.button
                  onClick={handleSkip}
                  whileTap={{ scale: 0.96 }}
                  className="px-3 py-1.5 text-xs rounded-md text-secondaryText hover:bg-surface-highest transition-colors"
                >
                  Skip
                </motion.button>
                <motion.button
                  onClick={handleNext}
                  whileTap={{ scale: 0.96 }}
                  className="px-3 py-1.5 text-xs rounded-md bg-primary text-background font-medium hover:brightness-110 transition-colors flex items-center gap-1"
                >
                  {current === steps.length - 1 ? 'Finish' : 'Next'}
                  <ChevronRight className="w-3 h-3" />
                </motion.button>
              </div>
            </div>
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </>
  );
};

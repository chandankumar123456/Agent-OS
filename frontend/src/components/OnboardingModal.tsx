import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Sparkles,
  Zap,
  Rocket,
  GitBranch,
  SkipForward,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';

interface OnboardingModalProps {
  onClose: () => void;
}

const OnboardingModal: React.FC<OnboardingModalProps> = ({ onClose }) => {
  const [step, setStep] = useState(0);
  const [isSeeding, setIsSeeding] = useState(false);
  const navigate = useNavigate();

  const runSeed = async () => {
    if (isSeeding) return;
    const alreadySeeded = localStorage.getItem('hasSeededExampleData');
    if (alreadySeeded === 'true') return;
    setIsSeeding(true);
    try {
      await apiClient.seedExampleData();
      localStorage.setItem('hasSeededExampleData', 'true');
    } catch {
      // Ignore seed errors
    } finally {
      setIsSeeding(false);
    }
  };

  const handleSelection = async (path: string) => {
    await runSeed();
    localStorage.setItem('hasCompletedOnboarding', 'true');
    onClose();
    navigate(path);
  };

  const handleSkip = async () => {
    await runSeed();
    localStorage.setItem('hasCompletedOnboarding', 'true');
    onClose();
  };

  const steps = [
    {
      icon: Sparkles,
      title: 'Welcome to AgentOS',
      content: (
        <div className="flex flex-col gap-5 items-center text-center">
          <div className="w-24 h-24 rounded-2xl bg-primary/10 flex items-center justify-center">
            <Sparkles className="w-12 h-12 text-primary" />
          </div>
          <p className="text-secondaryText leading-relaxed max-w-sm">
            AgentOS is your command center for intelligent agents. Submit tasks, build workflows,
            and orchestrate multi-agent systems with precision.
          </p>
          <motion.button
            onClick={() => setStep(1)}
            whileTap={{ scale: 0.96 }}
            className="btn-primary flex items-center gap-2 shadow-glow-cyan"
          >
            Get Started <Rocket className="w-4 h-4" />
          </motion.button>
        </div>
      ),
    },
    {
      icon: Zap,
      title: 'What would you like to do?',
      content: (
        <div className="flex flex-col gap-4 items-center">
          <p className="text-secondaryText text-sm text-center max-w-sm">
            Choose an option and we will set up example data to help you explore.
          </p>
          <div className="grid grid-cols-1 gap-3 w-full max-w-sm">
            <motion.button
              onClick={() => handleSelection('/dashboard')}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-3 p-4 bg-surface-highest rounded-xl border border-outline/10 hover:border-primary/30 transition-all group text-left"
            >
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                <Zap className="w-5 h-5 text-primary" />
              </div>
              <div>
                <span className="text-sm font-semibold text-primaryText block">Run a task</span>
                <span className="text-xs text-secondaryText">Execute your first agent task</span>
              </div>
            </motion.button>
            <motion.button
              onClick={() => handleSelection('/builder')}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-3 p-4 bg-surface-highest rounded-xl border border-outline/10 hover:border-primary/30 transition-all group text-left"
            >
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                <Rocket className="w-5 h-5 text-primary" />
              </div>
              <div>
                <span className="text-sm font-semibold text-primaryText block">Build an agent</span>
                <span className="text-xs text-secondaryText">Create a custom agent with tools</span>
              </div>
            </motion.button>
            <motion.button
              onClick={() => handleSelection('/workflows/builder')}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-3 p-4 bg-surface-highest rounded-xl border border-outline/10 hover:border-primary/30 transition-all group text-left"
            >
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                <GitBranch className="w-5 h-5 text-primary" />
              </div>
              <div>
                <span className="text-sm font-semibold text-primaryText block">Create a workflow</span>
                <span className="text-xs text-secondaryText">Design a multi-agent pipeline</span>
              </div>
            </motion.button>
          </div>
          <motion.button
            onClick={handleSkip}
            whileTap={{ scale: 0.96 }}
            className="text-xs text-secondaryText hover:text-primaryText transition-colors flex items-center gap-1 mt-2"
          >
            <SkipForward className="w-3 h-3" /> Skip for now
          </motion.button>
        </div>
      ),
    },
  ];

  const CurrentStep = steps[step];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        className="w-full max-w-lg bg-surface-high border border-outline/20 rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-outline/10">
          <div className="flex items-center gap-2">
            <CurrentStep.icon className="w-5 h-5 text-primary" />
            <h2 className="text-base font-semibold text-primaryText">{CurrentStep.title}</h2>
          </div>
          <motion.button
            onClick={handleSkip}
            whileTap={{ scale: 0.96 }}
            className="text-secondaryText hover:text-primaryText transition-colors"
            aria-label="Close onboarding"
          >
            <X className="w-5 h-5" />
          </motion.button>
        </div>

        {/* Body */}
        <div className="px-6 py-6 min-h-[280px]">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
            >
              {CurrentStep.content}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-outline/10 flex items-center justify-between">
          <motion.button
            onClick={handleSkip}
            whileTap={{ scale: 0.96 }}
            className="text-xs text-secondaryText hover:text-primaryText transition-colors"
          >
            Skip
          </motion.button>

          <div className="flex items-center gap-2">
            {steps.map((_, i) => (
              <motion.button
                key={i}
                onClick={() => setStep(i)}
                whileTap={{ scale: 0.96 }}
                className={`w-2 h-2 rounded-full transition-all ${
                  i === step ? 'bg-primary w-4' : 'bg-secondaryText/30 hover:bg-secondaryText/50'
                }`}
                aria-label={`Go to step ${i + 1}`}
              />
            ))}
          </div>

          <div className="w-16" />
        </div>
      </motion.div>
    </motion.div>
  );
};

export default OnboardingModal;

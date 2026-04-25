import { useEffect, useState } from 'react';
import { useSpring, useTransform, motion } from 'framer-motion';
import { numberSpring, prefersReducedMotion } from '../../lib/animations';

interface AnimatedNumberProps {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  className?: string;
}

/**
 * Animated number that counts up from 0 to target value.
 * Uses Framer Motion spring for smooth, natural motion.
 * Respects prefers-reduced-motion.
 */
export function AnimatedNumber({
  value,
  duration = 1.2,
  prefix = '',
  suffix = '',
  decimals = 0,
  className = '',
}: AnimatedNumberProps) {
  const [hasAnimated, setHasAnimated] = useState(false);

  const spring = useSpring(0, {
    ...numberSpring,
    duration: prefersReducedMotion ? 0 : duration,
  });

  const display = useTransform(spring, (latest) =>
    `${prefix}${latest.toFixed(decimals)}${suffix}`
  );

  useEffect(() => {
    if (!hasAnimated) {
      spring.set(value);
      setHasAnimated(true);
    } else {
      spring.set(value);
    }
  }, [value, spring, hasAnimated]);

  return <motion.span className={className}>{display}</motion.span>;
}

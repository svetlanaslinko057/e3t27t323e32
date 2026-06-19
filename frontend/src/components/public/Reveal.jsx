import { useRef } from 'react';
import { motion, useInView, useReducedMotion } from 'framer-motion';

/**
 * Scroll-reveal wrapper. Fades + lifts children into view once.
 * Respects prefers-reduced-motion (fade only, no translate).
 */
export const Reveal = ({ children, delay = 0, y = 22, className = '', as = 'div', once = true, amount = 0.25, ...rest }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once, amount });
  const reduce = useReducedMotion();
  const MotionTag = motion[as] || motion.div;

  return (
    <MotionTag
      ref={ref}
      className={className}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y }}
      animate={inView ? { opacity: 1, y: 0 } : (reduce ? { opacity: 0 } : { opacity: 0, y })}
      transition={{ duration: 0.55, delay, ease: [0.16, 1, 0.3, 1] }}
      data-testid="reveal"
      {...rest}
    >
      {children}
    </MotionTag>
  );
};

export default Reveal;

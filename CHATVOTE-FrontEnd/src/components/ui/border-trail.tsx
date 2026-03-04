"use client";
import { cn } from "@lib/utils";
import { type Transition } from "motion/react";
import * as motion from "motion/react-m";

type BorderTrailProps = {
  className?: string;
  size?: number;
  /** Border radius for the path. Use 9999 for pill-shaped/rounded-full elements */
  contentRadius?: number;
  transition?: Transition;
  delay?: number;
  onAnimationComplete?: () => void;
  style?: React.CSSProperties;
};

const BASE_TRANSITION: Transition = {
  repeat: Number.POSITIVE_INFINITY,
  duration: 5,
  ease: "linear",
};

export function BorderTrail({
  className,
  size = 60,
  contentRadius,
  transition,
  delay,
  onAnimationComplete,
  style,
}: BorderTrailProps) {
  // Use contentRadius if provided, otherwise fall back to size
  const pathRadius = contentRadius ?? size;

  return (
    <div className="pointer-events-none absolute inset-0 rounded-[inherit] border border-transparent mask-[linear-gradient(transparent,transparent),linear-gradient(#000,#000)] mask-intersect [mask-clip:padding-box,border-box]">
      <motion.div
        className={cn("absolute aspect-square bg-zinc-500", className)}
        style={{
          width: size,
          offsetPath: `rect(0 auto auto 0 round ${pathRadius}px)`,
          ...style,
        }}
        animate={{
          offsetDistance: ["0%", "100%"],
        }}
        transition={{
          ...(transition ?? BASE_TRANSITION),
          delay: delay,
        }}
        onAnimationComplete={onAnimationComplete}
      />
    </div>
  );
}

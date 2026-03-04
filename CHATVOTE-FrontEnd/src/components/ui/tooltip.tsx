"use client";

import * as React from "react";
import { createPortal } from "react-dom";

import {
  calculateBestPosition,
  clampCoordinates,
  type PopoverPosition,
  POSITION_CONFIGS,
  type PositionCoordinates,
} from "@lib/shared/position";
import { cn } from "@lib/utils";
import { AnimatePresence, motion } from "motion/react";

type TooltipPosition = PopoverPosition;

type TooltipContextValue = {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLElement | null>;
  position: TooltipPosition;
  delayDuration: number;
};

const TooltipContext = React.createContext<TooltipContextValue | null>(null);

function useTooltipContext(): TooltipContextValue {
  const context = React.useContext(TooltipContext);
  if (context === null) {
    throw new Error("Tooltip components must be used within a Tooltip");
  }
  return context;
}

type TooltipProviderProps = {
  children: React.ReactNode;
  delayDuration?: number;
};

const TooltipProvider = ({ children }: TooltipProviderProps) => {
  return <React.Fragment>{children}</React.Fragment>;
};

type TooltipProps = {
  children: React.ReactNode;
  position?: TooltipPosition;
  delayDuration?: number;
};

const Tooltip = ({
  children,
  position = "bottom-center",
  delayDuration = 150,
}: TooltipProps) => {
  const [isOpen, setIsOpen] = React.useState(false);
  const triggerRef = React.useRef<HTMLElement | null>(null);

  const contextValue = React.useMemo(
    () => ({
      isOpen,
      setIsOpen,
      triggerRef,
      position,
      delayDuration,
    }),
    [isOpen, position, delayDuration],
  );

  return (
    <TooltipContext.Provider value={contextValue}>
      {children}
    </TooltipContext.Provider>
  );
};

type TooltipTriggerProps = {
  children: React.ReactNode;
  asChild?: boolean;
};

const TooltipTrigger = ({ children, asChild = false }: TooltipTriggerProps) => {
  const { setIsOpen, triggerRef, delayDuration } = useTooltipContext();
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  const handleMouseEnter = React.useCallback(() => {
    timeoutRef.current = setTimeout(() => {
      setIsOpen(true);
    }, delayDuration);
  }, [setIsOpen, delayDuration]);

  const handleMouseLeave = React.useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsOpen(false);
  }, [setIsOpen]);

  const handleFocus = React.useCallback(() => {
    setIsOpen(true);
  }, [setIsOpen]);

  const handleBlur = React.useCallback(() => {
    setIsOpen(false);
  }, [setIsOpen]);

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  if (asChild && React.isValidElement(children)) {
    const childElement = children as React.ReactElement<
      React.HTMLAttributes<HTMLElement> & { ref?: React.Ref<HTMLElement> }
    >;
    return React.cloneElement(childElement, {
      ref: triggerRef,
      onMouseEnter: handleMouseEnter,
      onMouseLeave: handleMouseLeave,
      onFocus: handleFocus,
      onBlur: handleBlur,
    });
  }

  return (
    <span
      ref={triggerRef as React.RefObject<HTMLSpanElement>}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
    >
      {children}
    </span>
  );
};

type TooltipContentProps = {
  children: React.ReactNode;
  className?: string;
  sideOffset?: number;
  hidden?: boolean;
};

const TooltipContent = ({
  children,
  className,
  sideOffset = 8,
  hidden = false,
}: TooltipContentProps) => {
  const { isOpen, triggerRef, position } = useTooltipContext();
  const [coords, setCoords] = React.useState<PositionCoordinates>({
    top: 0,
    left: 0,
  });
  const [actualPosition, setActualPosition] =
    React.useState<TooltipPosition>(position);
  const [tooltipSize, setTooltipSize] = React.useState({ width: 0, height: 0 });
  const tooltipRef = React.useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = React.useCallback(() => {
    if (triggerRef.current === null || tooltipRef.current === null) {
      return;
    }

    const triggerRect = triggerRef.current.getBoundingClientRect();
    // Use offsetWidth/offsetHeight to get unscaled dimensions (not affected by transform: scale)
    const tooltipWidth = tooltipRef.current.offsetWidth;
    const tooltipHeight = tooltipRef.current.offsetHeight;
    const padding = 10;

    const { position: bestPosition, coordinates } = calculateBestPosition(
      triggerRect,
      { width: tooltipWidth, height: tooltipHeight },
      position,
      sideOffset,
      padding,
    );

    const clampedCoords = clampCoordinates(
      coordinates,
      { width: tooltipWidth, height: tooltipHeight },
      padding,
    );

    setActualPosition(bestPosition);
    setCoords(clampedCoords);
    setTooltipSize({ width: tooltipWidth, height: tooltipHeight });
  }, [position, sideOffset, triggerRef]);

  React.useEffect(() => {
    if (isOpen === false) {
      return;
    }

    updatePosition();

    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);

    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [isOpen, updatePosition]);

  React.useEffect(() => {
    if (isOpen === false || tooltipRef.current === null) {
      return;
    }

    const resizeObserver = new ResizeObserver(() => {
      updatePosition();
    });

    resizeObserver.observe(tooltipRef.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, [isOpen, updatePosition]);

  if (mounted === false) {
    return null;
  }

  const originConfig = POSITION_CONFIGS[actualPosition];

  return createPortal(
    <AnimatePresence>
      {isOpen === true && hidden === false ? (
        <motion.div
          ref={tooltipRef}
          initial={{
            opacity: 0,
            y: -8,
          }}
          animate={{
            opacity: 1,
            y: 0,
          }}
          exit={{
            opacity: 0,
            y: -8,
          }}
          transition={{
            type: "spring",
            stiffness: 400,
            damping: 32,
          }}
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            transformOrigin: originConfig.origin,
            zIndex: 9999,
            visibility: tooltipSize.width === 0 ? "hidden" : "visible",
          }}
          className={cn(
            "pointer-events-none rounded-md border border-neutral-700 bg-neutral-100 px-3 py-1.5 text-sm text-neutral-950 shadow-md dark:bg-purple-900 dark:text-neutral-100",
            className,
          )}
        >
          {children}
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
};

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
export type { TooltipPosition };

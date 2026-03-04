"use client";

import * as React from "react";
import {
  createContext,
  useCallback,
  useContext,
  useState,
  useSyncExternalStore,
} from "react";
import { createPortal } from "react-dom";

import { useLockScroll } from "@lib/hooks/useLockScroll";
import { cn } from "@lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import {
  AnimatePresence,
  motion,
  type PanInfo,
  useMotionValue,
  useTransform,
} from "motion/react";
import { useTranslations } from "next-intl";

type SheetContextValue = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const SheetContext = createContext<SheetContextValue | null>(null);

function useSheetContext() {
  const context = useContext(SheetContext);
  if (context === null) {
    throw new Error("Sheet components must be used within a Sheet");
  }
  return context;
}

function subscribe() {
  return () => {};
}

function useIsMounted() {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}

type SheetProps = {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
};

const Sheet = ({
  open: controlledOpen,
  onOpenChange,
  children,
}: SheetProps) => {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      if (onOpenChange !== undefined) {
        onOpenChange(newOpen);
      }
      if (isControlled === false) {
        setInternalOpen(newOpen);
      }
    },
    [isControlled, onOpenChange],
  );

  return (
    <SheetContext.Provider value={{ open, onOpenChange: handleOpenChange }}>
      {children}
    </SheetContext.Provider>
  );
};

type SheetTriggerProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
};

const SheetTrigger = React.forwardRef<HTMLButtonElement, SheetTriggerProps>(
  ({ asChild, children, onClick, ...props }, ref) => {
    const { onOpenChange } = useSheetContext();

    const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(event);
      onOpenChange(true);
    };

    if (asChild === true && React.isValidElement(children)) {
      return React.cloneElement(
        children as React.ReactElement<{
          onClick?: (event: React.MouseEvent) => void;
        }>,
        {
          onClick: (event: React.MouseEvent) => {
            (
              children as React.ReactElement<{
                onClick?: (event: React.MouseEvent) => void;
              }>
            ).props.onClick?.(event);
            onOpenChange(true);
          },
        },
      );
    }

    return (
      <button ref={ref} onClick={handleClick} {...props}>
        {children}
      </button>
    );
  },
);
SheetTrigger.displayName = "SheetTrigger";

type SheetCloseProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
};

const SheetClose = React.forwardRef<HTMLButtonElement, SheetCloseProps>(
  ({ asChild, children, onClick, className, ...props }, ref) => {
    const { onOpenChange } = useSheetContext();

    const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(event);
      onOpenChange(false);
    };

    if (asChild === true && React.isValidElement(children)) {
      return React.cloneElement(
        children as React.ReactElement<{
          onClick?: (event: React.MouseEvent) => void;
        }>,
        {
          onClick: (event: React.MouseEvent) => {
            (
              children as React.ReactElement<{
                onClick?: (event: React.MouseEvent) => void;
              }>
            ).props.onClick?.(event);
            onOpenChange(false);
          },
        },
      );
    }

    return (
      <button ref={ref} onClick={handleClick} className={className} {...props}>
        {children}
      </button>
    );
  },
);
SheetClose.displayName = "SheetClose";

type SheetPortalProps = {
  children: React.ReactNode;
};

const SheetPortal = ({ children }: SheetPortalProps) => {
  const isMounted = useIsMounted();

  if (isMounted === false) {
    return null;
  }

  return createPortal(children, document.body);
};
SheetPortal.displayName = "SheetPortal";

type SheetOverlayProps = {
  className?: string;
};

const SheetOverlay = React.forwardRef<HTMLDivElement, SheetOverlayProps>(
  ({ className }, ref) => {
    const { onOpenChange } = useSheetContext();

    return (
      <motion.div
        ref={ref}
        className={cn("fixed inset-0 z-50 bg-black/80", className)}
        onClick={() => {
          onOpenChange(false);
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{
          type: "tween",
          duration: 0.2,
          ease: "easeOut",
        }}
      />
    );
  },
);
SheetOverlay.displayName = "SheetOverlay";

const sheetVariants = cva("bg-background fixed z-50 gap-4 p-6 shadow-lg", {
  variants: {
    side: {
      top: "inset-x-0 top-0 border-b",
      bottom: "inset-x-0 bottom-0 border-t",
      left: "inset-y-0 left-0 h-full w-3/4 border-r sm:max-w-sm",
      right: "inset-y-0 right-0 h-full w-3/4 border-l sm:max-w-sm",
    },
    fullWidth: {
      true: "",
      false: "",
    },
  },
  compoundVariants: [
    {
      side: "left",
      fullWidth: true,
      className: "w-full border-r-0 sm:max-w-none",
    },
    {
      side: "right",
      fullWidth: true,
      className: "w-full border-l-0 sm:max-w-none",
    },
  ],
  defaultVariants: {
    side: "right",
    fullWidth: false,
  },
});

const slideVariants = {
  top: {
    initial: { y: "-100%" },
    animate: { y: 0 },
    exit: { y: "-100%" },
  },
  bottom: {
    initial: { y: "100%" },
    animate: { y: 0 },
    exit: { y: "100%" },
  },
  left: {
    initial: { x: "-100%" },
    animate: { x: 0 },
    exit: { x: "-100%" },
  },
  right: {
    initial: { x: "100%" },
    animate: { x: 0 },
    exit: { x: "100%" },
  },
};

interface SheetContentProps extends VariantProps<typeof sheetVariants> {
  className?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
  closeButtonPosition?: "top-right" | "drag-handle" | "hidden";
}

const DRAG_CLOSE_THRESHOLD = 100;

const SheetContent = React.forwardRef<HTMLDivElement, SheetContentProps>(
  (
    {
      side = "right",
      fullWidth = false,
      className,
      children,
      style,
      closeButtonPosition = "top-right",
    },
    ref,
  ) => {
    const t = useTranslations("common");
    const { open, onOpenChange } = useSheetContext();
    const sideValue = side ?? "right";
    const variants = slideVariants[sideValue];
    const isLeftSide = sideValue === "left";

    const dragX = useMotionValue(0);
    const handleOpacity = useTransform(
      dragX,
      isLeftSide ? [-50, 0, 50] : [-50, 0, 50],
      isLeftSide ? [0.5, 1, 1] : [1, 1, 0.5],
    );

    useLockScroll({ isLocked: open });

    const handleDragEnd = (_: unknown, info: PanInfo) => {
      const threshold = DRAG_CLOSE_THRESHOLD;
      const shouldClose = isLeftSide
        ? info.offset.x < -threshold || info.velocity.x < -500
        : info.offset.x > threshold || info.velocity.x > 500;

      if (shouldClose) {
        onOpenChange(false);
      }
    };

    const renderCloseButton = () => {
      if (closeButtonPosition === "hidden") {
        return null;
      }

      if (closeButtonPosition === "drag-handle") {
        return (
          <motion.div
            className={cn(
              "fixed top-1/2 z-60 flex -translate-y-1/2 cursor-grab touch-none items-center active:cursor-grabbing",
              isLeftSide ? "right-0" : "left-0",
            )}
            style={{ opacity: handleOpacity }}
            drag="x"
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.15}
            onDragEnd={handleDragEnd}
            onDrag={(_, info) => {
              dragX.set(info.offset.x);
            }}
          >
            <div
              className={cn(
                "flex h-20 w-6 items-center justify-center bg-neutral-100 shadow-md dark:bg-purple-900",
                "border-neutral-950 dark:border-neutral-100",
                isLeftSide
                  ? "rounded-l-2xl border-t border-b border-l"
                  : "rounded-r-2xl border-t border-r border-b",
              )}
            >
              <div className="h-10 w-1 rounded-full bg-neutral-400 dark:bg-neutral-600" />
            </div>
          </motion.div>
        );
      }

      return (
        <SheetClose className="ring-offset-background focus:ring-ring absolute top-4 right-4 rounded-sm opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-none disabled:pointer-events-none">
          <X className="size-4" />
          <span className="sr-only">{t("close")}</span>
        </SheetClose>
      );
    };

    return (
      <SheetPortal>
        <AnimatePresence mode="wait">
          {open === true ? (
            <React.Fragment>
              <SheetOverlay />
              <motion.div
                ref={ref}
                className={cn(sheetVariants({ side, fullWidth }), className)}
                style={style}
                initial={variants.initial}
                animate={variants.animate}
                exit={variants.exit}
                transition={{
                  type: "spring",
                  damping: 30,
                  stiffness: 300,
                  mass: 0.8,
                }}
              >
                {children}
                {renderCloseButton()}
              </motion.div>
            </React.Fragment>
          ) : null}
        </AnimatePresence>
      </SheetPortal>
    );
  },
);
SheetContent.displayName = "SheetContent";

const SheetHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col space-y-2 text-center sm:text-left",
      className,
    )}
    {...props}
  />
);
SheetHeader.displayName = "SheetHeader";

const SheetFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className,
    )}
    {...props}
  />
);
SheetFooter.displayName = "SheetFooter";

const SheetTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h2
    ref={ref}
    className={cn("text-foreground text-lg font-semibold", className)}
    {...props}
  />
));
SheetTitle.displayName = "SheetTitle";

const SheetDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-muted-foreground text-sm", className)}
    {...props}
  />
));
SheetDescription.displayName = "SheetDescription";

export {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetOverlay,
  SheetPortal,
  SheetTitle,
  SheetTrigger,
};

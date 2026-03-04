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
import { Check, ChevronRight, Circle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

type DropdownMenuPosition = PopoverPosition;

type DropdownMenuContextValue = {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLElement | null>;
  contentRef: React.RefObject<HTMLDivElement | null>;
  position: DropdownMenuPosition;
  onOpenChange?: (open: boolean) => void;
};

const DropdownMenuContext =
  React.createContext<DropdownMenuContextValue | null>(null);

function useDropdownMenuContext(): DropdownMenuContextValue {
  const context = React.useContext(DropdownMenuContext);
  if (context === null) {
    throw new Error(
      "DropdownMenu components must be used within a DropdownMenu",
    );
  }
  return context;
}

type DropdownMenuProps = {
  children: React.ReactNode;
  position?: DropdownMenuPosition;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
};

const DropdownMenu = ({
  children,
  position = "bottom-left",
  open,
  defaultOpen = false,
  onOpenChange,
}: DropdownMenuProps) => {
  const [internalIsOpen, setInternalIsOpen] = React.useState(defaultOpen);
  const triggerRef = React.useRef<HTMLElement | null>(null);
  const contentRef = React.useRef<HTMLDivElement | null>(null);

  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : internalIsOpen;

  const handleSetIsOpen = React.useCallback(
    (newOpen: boolean) => {
      if (isControlled === false) {
        setInternalIsOpen(newOpen);
      }
      onOpenChange?.(newOpen);
    },
    [isControlled, onOpenChange],
  );

  const contextValue = React.useMemo(
    () => ({
      isOpen,
      setIsOpen: handleSetIsOpen,
      triggerRef,
      contentRef,
      position,
      onOpenChange,
    }),
    [isOpen, handleSetIsOpen, position, onOpenChange],
  );

  return (
    <DropdownMenuContext.Provider value={contextValue}>
      {children}
    </DropdownMenuContext.Provider>
  );
};

type DropdownMenuTriggerProps = {
  children: React.ReactNode;
  asChild?: boolean;
  className?: string;
};

const DropdownMenuTrigger = ({
  children,
  asChild = false,
  className,
}: DropdownMenuTriggerProps) => {
  const { isOpen, setIsOpen, triggerRef } = useDropdownMenuContext();

  const handleClick = React.useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      setIsOpen(!isOpen);
    },
    [isOpen, setIsOpen],
  );

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      if (
        event.key === "Enter" ||
        event.key === " " ||
        event.key === "ArrowDown"
      ) {
        event.preventDefault();
        setIsOpen(true);
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setIsOpen(false);
      }
    },
    [setIsOpen],
  );

  if (asChild === true && React.isValidElement(children)) {
    const childElement = children as React.ReactElement<
      React.HTMLAttributes<HTMLElement> & { ref?: React.Ref<HTMLElement> }
    >;
    return React.cloneElement(childElement, {
      ref: triggerRef,
      onClick: handleClick,
      onKeyDown: handleKeyDown,
      "aria-expanded": isOpen,
      "aria-haspopup": "menu",
    } as React.HTMLAttributes<HTMLElement>);
  }

  return (
    <button
      ref={triggerRef as React.RefObject<HTMLButtonElement>}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      aria-expanded={isOpen}
      aria-haspopup="menu"
      className={cn("inline-flex items-center justify-center", className)}
      type="button"
    >
      {children}
    </button>
  );
};

const DropdownMenuGroup = ({ children }: { children: React.ReactNode }) => {
  return <div role="group">{children}</div>;
};

const DropdownMenuPortal = ({ children }: { children: React.ReactNode }) => {
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (mounted === false) {
    return null;
  }

  return createPortal(children, document.body);
};

type SubMenuContextValue = {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLElement | null>;
};

const SubMenuContext = React.createContext<SubMenuContextValue | null>(null);

function useSubMenuContext(): SubMenuContextValue | null {
  return React.useContext(SubMenuContext);
}

const DropdownMenuSub = ({ children }: { children: React.ReactNode }) => {
  const [isOpen, setIsOpen] = React.useState(false);
  const triggerRef = React.useRef<HTMLElement | null>(null);

  const contextValue = React.useMemo(
    () => ({
      isOpen,
      setIsOpen,
      triggerRef,
    }),
    [isOpen],
  );

  return (
    <SubMenuContext.Provider value={contextValue}>
      {children}
    </SubMenuContext.Provider>
  );
};

const DropdownMenuRadioGroup = ({
  children,
  value,
  onValueChange,
}: {
  children: React.ReactNode;
  value?: string;
  onValueChange?: (value: string) => void;
}) => {
  return (
    <RadioGroupContext.Provider value={{ value, onValueChange }}>
      <div role="radiogroup">{children}</div>
    </RadioGroupContext.Provider>
  );
};

type RadioGroupContextValue = {
  value?: string;
  onValueChange?: (value: string) => void;
};

const RadioGroupContext = React.createContext<RadioGroupContextValue>({});

type DropdownMenuContentProps = {
  children: React.ReactNode;
  className?: string;
  sideOffset?: number;
  align?: "start" | "center" | "end";
};

function getPositionFromAlign(
  align: "start" | "center" | "end" | undefined,
): DropdownMenuPosition {
  if (align === "center") {
    return "bottom-center";
  }
  if (align === "end") {
    return "bottom-right";
  }
  return "bottom-left";
}

const DropdownMenuContent = ({
  children,
  className,
  sideOffset = 4,
  align,
}: DropdownMenuContentProps) => {
  const { isOpen, setIsOpen, triggerRef, contentRef, position } =
    useDropdownMenuContext();
  const effectivePosition =
    align !== undefined ? getPositionFromAlign(align) : position;
  const [coords, setCoords] = React.useState<PositionCoordinates>({
    top: 0,
    left: 0,
  });
  const [actualPosition, setActualPosition] =
    React.useState<DropdownMenuPosition>(effectivePosition);
  const [contentSize, setContentSize] = React.useState({ width: 0, height: 0 });
  const [mounted, setMounted] = React.useState(false);
  const focusedIndexRef = React.useRef<number>(-1);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = React.useCallback(() => {
    if (triggerRef.current === null || contentRef.current === null) {
      return;
    }

    const triggerRect = triggerRef.current.getBoundingClientRect();
    // Use offsetWidth/offsetHeight to get unscaled dimensions (not affected by transform: scale)
    const contentWidth = contentRef.current.offsetWidth;
    const contentHeight = contentRef.current.offsetHeight;
    const padding = 10;

    const { position: bestPosition, coordinates } = calculateBestPosition(
      triggerRect,
      { width: contentWidth, height: contentHeight },
      effectivePosition,
      sideOffset,
      padding,
    );

    const clampedCoords = clampCoordinates(
      coordinates,
      { width: contentWidth, height: contentHeight },
      padding,
    );

    setActualPosition(bestPosition);
    setCoords(clampedCoords);
    setContentSize({ width: contentWidth, height: contentHeight });
  }, [effectivePosition, sideOffset, triggerRef, contentRef]);

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
    if (isOpen === false || contentRef.current === null) {
      return;
    }

    const resizeObserver = new ResizeObserver(() => {
      updatePosition();
    });

    resizeObserver.observe(contentRef.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, [isOpen, contentRef, updatePosition]);

  React.useEffect(() => {
    if (isOpen === false) {
      return;
    }

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;

      if (
        contentRef.current !== null &&
        !contentRef.current.contains(target) &&
        triggerRef.current !== null &&
        !triggerRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen, setIsOpen, contentRef, triggerRef]);

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      const items = contentRef.current?.querySelectorAll(
        '[role="menuitem"]:not([data-disabled])',
      );
      if (items === undefined || items.length === 0) {
        return;
      }

      const itemsArray = Array.from(items) as HTMLElement[];

      if (event.key === "ArrowDown") {
        event.preventDefault();
        focusedIndexRef.current =
          (focusedIndexRef.current + 1) % itemsArray.length;
        itemsArray[focusedIndexRef.current]?.focus();
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        focusedIndexRef.current =
          (focusedIndexRef.current - 1 + itemsArray.length) % itemsArray.length;
        itemsArray[focusedIndexRef.current]?.focus();
      }

      if (event.key === "Home") {
        event.preventDefault();
        focusedIndexRef.current = 0;
        itemsArray[0]?.focus();
      }

      if (event.key === "End") {
        event.preventDefault();
        focusedIndexRef.current = itemsArray.length - 1;
        itemsArray[itemsArray.length - 1]?.focus();
      }

      if (event.key === "Tab") {
        event.preventDefault();
        setIsOpen(false);
      }
    },
    [contentRef, setIsOpen],
  );

  if (mounted === false) {
    return null;
  }

  const originConfig = POSITION_CONFIGS[actualPosition];

  return createPortal(
    <AnimatePresence>
      {isOpen === true ? (
        <motion.div
          ref={contentRef}
          role="menu"
          aria-orientation="vertical"
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
            duration: 0.22,
            ease: [0.16, 1, 0.3, 1],
          }}
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            transformOrigin: originConfig.origin,
            zIndex: 9999,
            visibility: contentSize.width === 0 ? "hidden" : "visible",
          }}
          onKeyDown={handleKeyDown}
          className={cn(
            "min-w-32 overflow-hidden rounded-md border border-neutral-200 bg-white p-1 text-neutral-950 shadow-md dark:border-neutral-700 dark:bg-purple-900 dark:text-neutral-100",
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

type DropdownMenuSubTriggerProps = {
  children: React.ReactNode;
  className?: string;
  inset?: boolean;
  disabled?: boolean;
};

const DropdownMenuSubTrigger = ({
  children,
  className,
  inset = false,
  disabled = false,
}: DropdownMenuSubTriggerProps) => {
  const subContext = useSubMenuContext();

  const handleMouseEnter = React.useCallback(() => {
    if (disabled === true) {
      return;
    }
    subContext?.setIsOpen(true);
  }, [disabled, subContext]);

  const handleMouseLeave = React.useCallback(() => {
    subContext?.setIsOpen(false);
  }, [subContext]);

  return (
    <div
      ref={subContext?.triggerRef as React.RefObject<HTMLDivElement>}
      role="menuitem"
      aria-haspopup="menu"
      aria-expanded={subContext?.isOpen}
      data-disabled={disabled ? "" : undefined}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={cn(
        "flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none",
        "focus:bg-neutral-100 dark:focus:bg-neutral-800",
        "data-[state=open]:bg-neutral-100 dark:data-[state=open]:bg-neutral-800",
        inset && "pl-8",
        disabled && "pointer-events-none opacity-50",
        className,
      )}
    >
      {children}
      <ChevronRight className="ml-auto size-4" />
    </div>
  );
};

type DropdownMenuSubContentProps = {
  children: React.ReactNode;
  className?: string;
  sideOffset?: number;
};

const DropdownMenuSubContent = ({
  children,
  className,
  sideOffset = 2,
}: DropdownMenuSubContentProps) => {
  const subContext = useSubMenuContext();
  const contentRef = React.useRef<HTMLDivElement | null>(null);
  const [coords, setCoords] = React.useState<PositionCoordinates>({
    top: 0,
    left: 0,
  });
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = React.useCallback(() => {
    if (
      subContext === null ||
      subContext.triggerRef.current === null ||
      contentRef.current === null
    ) {
      return;
    }

    const triggerRect = subContext.triggerRef.current.getBoundingClientRect();
    // Use offsetWidth/offsetHeight to get unscaled dimensions (not affected by transform: scale)
    const contentWidth = contentRef.current.offsetWidth;
    const contentHeight = contentRef.current.offsetHeight;
    const padding = 10;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let left = triggerRect.right + sideOffset;

    if (left + contentWidth > viewportWidth - padding) {
      left = triggerRect.left - contentWidth - sideOffset;
    }

    let top = triggerRect.top;

    if (top + contentHeight > viewportHeight - padding) {
      top = viewportHeight - contentHeight - padding;
    }

    if (top < padding) {
      top = padding;
    }

    setCoords({ top, left });
  }, [subContext, sideOffset]);

  React.useEffect(() => {
    if (subContext?.isOpen !== true) {
      return;
    }

    updatePosition();

    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);

    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [subContext?.isOpen, updatePosition]);

  React.useEffect(() => {
    if (subContext?.isOpen !== true || contentRef.current === null) {
      return;
    }

    const resizeObserver = new ResizeObserver(() => {
      updatePosition();
    });

    resizeObserver.observe(contentRef.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, [subContext?.isOpen, updatePosition]);

  if (mounted === false || subContext === null) {
    return null;
  }

  return createPortal(
    <AnimatePresence>
      {subContext.isOpen === true ? (
        <motion.div
          ref={contentRef}
          role="menu"
          initial={{
            opacity: 0,
            scale: 0.9,
          }}
          animate={{
            opacity: 1,
            scale: 1,
          }}
          exit={{
            opacity: 0,
            scale: 0.9,
          }}
          transition={{
            duration: 0.22,
            ease: [0.16, 1, 0.3, 1],
          }}
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            transformOrigin: "left top",
            zIndex: 10000,
          }}
          onMouseEnter={() => subContext.setIsOpen(true)}
          onMouseLeave={() => subContext.setIsOpen(false)}
          className={cn(
            "min-w-32 overflow-hidden rounded-md border border-neutral-200 bg-white p-1 text-neutral-950 shadow-lg dark:border-neutral-700 dark:bg-purple-900 dark:text-neutral-100",
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

type DropdownMenuItemProps = {
  children: React.ReactNode;
  className?: string;
  inset?: boolean;
  disabled?: boolean;
  onSelect?: () => void;
  onClick?: () => void;
};

const DropdownMenuItem = ({
  children,
  className,
  inset = false,
  disabled = false,
  onSelect,
  onClick,
}: DropdownMenuItemProps) => {
  const { setIsOpen } = useDropdownMenuContext();

  const handleClick = React.useCallback(() => {
    if (disabled === true) {
      return;
    }
    onSelect?.();
    onClick?.();
    setIsOpen(false);
  }, [disabled, onSelect, onClick, setIsOpen]);

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      if ((event.key === "Enter" || event.key === " ") && !disabled) {
        event.preventDefault();
        onSelect?.();
        onClick?.();
        setIsOpen(false);
      }
    },
    [disabled, onSelect, onClick, setIsOpen],
  );

  return (
    <div
      role="menuitem"
      tabIndex={disabled ? -1 : 0}
      data-disabled={disabled ? "" : undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        "relative flex items-center gap-2 rounded-sm px-2 py-1.5 text-sm transition-colors outline-none select-none",
        "focus:bg-neutral-100 focus:text-neutral-900 dark:focus:bg-neutral-800 dark:focus:text-neutral-100",
        "hover:bg-neutral-100 dark:hover:bg-neutral-800",
        inset === true ? "pl-8" : undefined,
        disabled === true
          ? "pointer-events-none cursor-default opacity-50"
          : "cursor-pointer",
        "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
        className,
      )}
    >
      {children}
    </div>
  );
};

type DropdownMenuCheckboxItemProps = {
  children: React.ReactNode;
  className?: string;
  checked?: boolean;
  disabled?: boolean;
  onCheckedChange?: (checked: boolean) => void;
};

const DropdownMenuCheckboxItem = ({
  children,
  className,
  checked = false,
  disabled = false,
  onCheckedChange,
}: DropdownMenuCheckboxItemProps) => {
  const handleClick = React.useCallback(() => {
    if (disabled === true) {
      return;
    }
    onCheckedChange?.(!checked);
  }, [disabled, checked, onCheckedChange]);

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      if ((event.key === "Enter" || event.key === " ") && !disabled) {
        event.preventDefault();
        onCheckedChange?.(!checked);
      }
    },
    [disabled, checked, onCheckedChange],
  );

  return (
    <div
      role="menuitemcheckbox"
      aria-checked={checked}
      tabIndex={disabled ? -1 : 0}
      data-disabled={disabled ? "" : undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        "relative flex cursor-default items-center rounded-sm py-1.5 pr-2 pl-8 text-sm transition-colors outline-none select-none",
        "focus:bg-neutral-100 focus:text-neutral-900 dark:focus:bg-neutral-800 dark:focus:text-neutral-100",
        "hover:bg-neutral-100 dark:hover:bg-neutral-800",
        disabled === true ? "pointer-events-none opacity-50" : undefined,
        className,
      )}
    >
      <span className="absolute left-2 flex size-3.5 items-center justify-center">
        {checked === true ? <Check className="size-4" /> : null}
      </span>
      {children}
    </div>
  );
};

type DropdownMenuRadioItemProps = {
  children: React.ReactNode;
  className?: string;
  value: string;
  disabled?: boolean;
};

const DropdownMenuRadioItem = ({
  children,
  className,
  value,
  disabled = false,
}: DropdownMenuRadioItemProps) => {
  const radioContext = React.useContext(RadioGroupContext);
  const isChecked = radioContext.value === value;

  const handleClick = React.useCallback(() => {
    if (disabled === true) {
      return;
    }
    radioContext.onValueChange?.(value);
  }, [disabled, radioContext, value]);

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      if ((event.key === "Enter" || event.key === " ") && disabled === false) {
        event.preventDefault();
        radioContext.onValueChange?.(value);
      }
    },
    [disabled, radioContext, value],
  );

  return (
    <div
      role="menuitemradio"
      aria-checked={isChecked}
      tabIndex={disabled === true ? -1 : 0}
      data-disabled={disabled === true ? "" : undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        "relative flex cursor-default items-center rounded-sm py-1.5 pr-2 pl-8 text-sm transition-colors outline-none select-none",
        "focus:bg-neutral-100 focus:text-neutral-900 dark:focus:bg-neutral-800 dark:focus:text-neutral-100",
        "hover:bg-neutral-100 dark:hover:bg-neutral-800",
        disabled === true ? "pointer-events-none opacity-50" : undefined,
        className,
      )}
    >
      <span className="absolute left-2 flex size-3.5 items-center justify-center">
        {isChecked === true ? <Circle className="size-2 fill-current" /> : null}
      </span>
      {children}
    </div>
  );
};

type DropdownMenuLabelProps = {
  children: React.ReactNode;
  className?: string;
  inset?: boolean;
};

const DropdownMenuLabel = ({
  children,
  className,
  inset = false,
}: DropdownMenuLabelProps) => {
  return (
    <div
      className={cn(
        "px-2 py-1.5 text-sm font-semibold",
        inset === true ? "pl-8" : undefined,
        className,
      )}
    >
      {children}
    </div>
  );
};

type DropdownMenuSeparatorProps = {
  className?: string;
};

const DropdownMenuSeparator = ({ className }: DropdownMenuSeparatorProps) => {
  return (
    <div
      role="separator"
      className={cn(
        "-mx-1 my-1 h-px bg-neutral-200 dark:bg-neutral-700",
        className,
      )}
    />
  );
};

type DropdownMenuShortcutProps = React.HTMLAttributes<HTMLSpanElement>;

const DropdownMenuShortcut = ({
  className,
  ...props
}: DropdownMenuShortcutProps) => {
  return (
    <span
      className={cn("ml-auto text-xs tracking-widest opacity-60", className)}
      {...props}
    />
  );
};

export {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
};
export type { DropdownMenuPosition };

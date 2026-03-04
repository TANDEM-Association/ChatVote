import React, { useEffect } from "react";
import { createPortal } from "react-dom";

import { useLockScroll } from "@lib/hooks/useLockScroll";
import { cn } from "@lib/utils";
import { AnimatePresence, motion } from "motion/react";

type ModalProps = {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
};

let canRender = false;

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  children,
  className,
}) => {
  useLockScroll({ isLocked: isOpen });

  useEffect(() => {
    if (typeof window === "undefined") {
      canRender = false;
    }

    canRender = true;
  }, []);

  if (canRender === false) {
    return null;
  }

  return createPortal(
    <AnimatePresence>
      {isOpen === true ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          onClick={onClose}
          initial={{
            backdropFilter: "blur(0px)",
            background: "transparent",
          }}
          animate={{
            backdropFilter: "blur(4px)",
            background: "rgba(25,22,39,0.8)",
          }}
          exit={{
            backdropFilter: "blur(0px)",
            background: "transparent",
          }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            className={cn(
              "relative max-h-[80dvh] w-fit max-w-257.5 rounded-lg border border-purple-400 bg-purple-900",
              className,
            )}
            onClick={(event) => {
              event.stopPropagation();
            }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{
              duration: 0.2,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            <button
              onClick={onClose}
              className="absolute top-2 right-2 cursor-pointer text-neutral-400 transition-colors hover:text-neutral-100"
            >
              <svg
                className="size-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
            {children}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
};

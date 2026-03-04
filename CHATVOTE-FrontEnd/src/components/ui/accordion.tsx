"use client";

import React from "react";

import { cn } from "@lib/utils";
import { ChevronDown } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

type AccordionContextType = {
  openItems: Set<string>;
  toggleItem: (id: string) => void;
  multiple?: boolean;
};

export const AccordionContext =
  React.createContext<AccordionContextType | null>(null);

type GroupProps = {
  children: React.ReactNode;
  multiple?: boolean;
};

export const AccordionGroup: React.FC<GroupProps> = (props) => {
  const { children, multiple = false } = props;
  const [openItems, setOpenItems] = React.useState<Set<string>>(new Set());

  const toggleItem = (id: string) => {
    setOpenItems((prevState) => {
      const newOpenItems = new Set(prevState);

      if (multiple === true) {
        if (newOpenItems.has(id)) {
          newOpenItems.delete(id);
        } else {
          newOpenItems.add(id);
        }
      } else {
        if (newOpenItems.has(id)) {
          newOpenItems.delete(id);
        } else {
          newOpenItems.clear();
          newOpenItems.add(id);
        }
      }

      return newOpenItems;
    });
  };

  return (
    <AccordionContext.Provider value={{ openItems, toggleItem, multiple }}>
      <div className="flex w-full flex-col items-stretch justify-start">
        {children}
      </div>
    </AccordionContext.Provider>
  );
};

type ItemProps = {
  title: string;
  children: React.ReactNode;
  className?: string;
  trigger?: (props: { isOpen: boolean; toggle: () => void }) => React.ReactNode;
};

export const AccordionItem: React.FC<ItemProps> = (props) => {
  const { title, children, className, trigger } = props;

  const id = React.useId();
  const { isOpen, toggle } = useAccordion(id);

  return (
    <div
      className={cn(
        "border-y border-neutral-100 not-last:border-b-0 first:border-b-0",
        className,
      )}
    >
      {trigger !== undefined ? (
        trigger({ isOpen, toggle })
      ) : (
        <button
          onClick={toggle}
          className="relative flex w-full cursor-pointer items-center justify-between px-4 py-5 text-left"
        >
          <span className="text-sm leading-6 font-medium text-neutral-100">
            {title}
          </span>
          <ChevronDown
            className={cn(
              "size-6 text-neutral-100 transition-all duration-300 ease-in-out",
              isOpen === true && "rotate-180",
            )}
          />
        </button>
      )}
      <AnimatePresence>
        {isOpen === true ? (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            transition={{ duration: 0.4, type: "spring", bounce: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 pt-0 text-sm leading-5 font-normal text-neutral-100">
              {children}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
};

export function useAccordion(id: string) {
  const context = React.useContext(AccordionContext);

  const [isOpen, setIsOpen] = React.useState(false);

  if (context === null) {
    return {
      isOpen,
      toggle: () =>
        setIsOpen((prevState) => {
          return prevState === false;
        }),
    };
  }

  return {
    isOpen: context.openItems.has(id),
    toggle: () => context.toggleItem(id),
  };
}

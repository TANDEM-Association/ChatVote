/* eslint-disable react-hooks/immutability */
import React from "react";

type UseLockScrollOptions = {
  isLocked: boolean;
  element?: React.RefObject<HTMLElement | null>;
};

export function useLockScroll(
  { isLocked = true, element = undefined }: UseLockScrollOptions = {
    isLocked: true,
    element: undefined,
  },
) {
  React.useEffect(() => {
    const targetElement = element?.current ?? document.body;

    if (isLocked === true) {
      document.body.style.overflow = "hidden";
      targetElement.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "auto";
      targetElement.style.overflow = "auto";
    }

    return () => {
      document.body.style.overflow = "auto";
      targetElement.style.overflow = "auto";
    };
  }, [element, isLocked]);
}

"use client";

import { useSyncExternalStore } from "react";

function subscribe() {
  return () => {};
}

/**
 * Hook that returns true after the component has mounted (hydration is complete).
 * Useful for avoiding hydration mismatches with components that use `useId()` internally
 * (like Radix UI components).
 *
 * Usage:
 * ```tsx
 * const isMounted = useIsMounted();
 *
 * if (isMounted === false) {
 *   return <FallbackComponent />;
 * }
 *
 * return <ComponentWithRadixUI />;
 * ```
 */
export function useIsMounted() {
  return useSyncExternalStore(
    subscribe,
    () => true, // Client snapshot - after hydration, return true
    () => false, // Server snapshot - during SSR and initial hydration, return false
  );
}

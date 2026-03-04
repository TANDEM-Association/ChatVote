export type PopoverPosition =
  | "top-left"
  | "top-center"
  | "top-right"
  | "right"
  | "bottom-right"
  | "bottom-center"
  | "bottom-left"
  | "left";

export type PositionCoordinates = {
  top: number;
  left: number;
};

export type PositionConfig = {
  getCoordinates: (
    triggerRect: DOMRect,
    contentRect: { width: number; height: number },
    gap: number,
  ) => PositionCoordinates;
  origin: string;
};

export const POSITION_CONFIGS: Record<PopoverPosition, PositionConfig> = {
  "top-left": {
    getCoordinates: (triggerRect, contentRect, gap) => ({
      top: triggerRect.top - contentRect.height - gap,
      left: triggerRect.left,
    }),
    origin: "bottom left",
  },
  "top-center": {
    getCoordinates: (triggerRect, contentRect, gap) => ({
      top: triggerRect.top - contentRect.height - gap,
      left: triggerRect.left + triggerRect.width / 2 - contentRect.width / 2,
    }),
    origin: "bottom center",
  },
  "top-right": {
    getCoordinates: (triggerRect, contentRect, gap) => ({
      top: triggerRect.top - contentRect.height - gap,
      left: triggerRect.right - contentRect.width,
    }),
    origin: "bottom right",
  },
  right: {
    getCoordinates: (triggerRect, contentRect, gap) => ({
      top: triggerRect.top + triggerRect.height / 2 - contentRect.height / 2,
      left: triggerRect.right + gap,
    }),
    origin: "left center",
  },
  "bottom-right": {
    getCoordinates: (triggerRect, contentRect, gap) => ({
      top: triggerRect.bottom + gap,
      left: triggerRect.right - contentRect.width,
    }),
    origin: "top right",
  },
  "bottom-center": {
    getCoordinates: (triggerRect, contentRect, gap) => ({
      top: triggerRect.bottom + gap,
      left: triggerRect.left + triggerRect.width / 2 - contentRect.width / 2,
    }),
    origin: "top center",
  },
  "bottom-left": {
    getCoordinates: (triggerRect, _, gap) => ({
      top: triggerRect.bottom + gap,
      left: triggerRect.left,
    }),
    origin: "top left",
  },
  left: {
    getCoordinates: (triggerRect, contentRect, gap) => ({
      top: triggerRect.top + triggerRect.height / 2 - contentRect.height / 2,
      left: triggerRect.left - contentRect.width - gap,
    }),
    origin: "right center",
  },
};

export const POSITION_FALLBACK_ORDER: Record<
  PopoverPosition,
  PopoverPosition[]
> = {
  "top-left": [
    "top-center",
    "top-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
    "left",
    "right",
  ],
  "top-center": [
    "top-left",
    "top-right",
    "bottom-center",
    "bottom-left",
    "bottom-right",
    "left",
    "right",
  ],
  "top-right": [
    "top-center",
    "top-left",
    "bottom-right",
    "bottom-center",
    "bottom-left",
    "right",
    "left",
  ],
  right: [
    "left",
    "top-right",
    "bottom-right",
    "top-center",
    "bottom-center",
    "top-left",
    "bottom-left",
  ],
  "bottom-right": [
    "bottom-center",
    "bottom-left",
    "top-right",
    "top-center",
    "top-left",
    "right",
    "left",
  ],
  "bottom-center": [
    "bottom-left",
    "bottom-right",
    "top-center",
    "top-left",
    "top-right",
    "left",
    "right",
  ],
  "bottom-left": [
    "bottom-center",
    "bottom-right",
    "top-left",
    "top-center",
    "top-right",
    "left",
    "right",
  ],
  left: [
    "right",
    "top-left",
    "bottom-left",
    "top-center",
    "bottom-center",
    "top-right",
    "bottom-right",
  ],
};

export function checkPositionFits(
  coords: PositionCoordinates,
  contentRect: { width: number; height: number },
  padding: number,
): boolean {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  const fitsHorizontally =
    coords.left >= padding &&
    coords.left + contentRect.width <= viewportWidth - padding;
  const fitsVertically =
    coords.top >= padding &&
    coords.top + contentRect.height <= viewportHeight - padding;

  return fitsHorizontally && fitsVertically;
}

export function calculateBestPosition(
  triggerRect: DOMRect,
  contentRect: { width: number; height: number },
  preferredPosition: PopoverPosition,
  gap: number,
  padding: number,
): { position: PopoverPosition; coordinates: PositionCoordinates } {
  const preferredConfig = POSITION_CONFIGS[preferredPosition];
  const preferredCoords = preferredConfig.getCoordinates(
    triggerRect,
    contentRect,
    gap,
  );

  if (checkPositionFits(preferredCoords, contentRect, padding)) {
    return { position: preferredPosition, coordinates: preferredCoords };
  }

  const fallbackOrder = POSITION_FALLBACK_ORDER[preferredPosition];

  for (const fallbackPosition of fallbackOrder) {
    const fallbackConfig = POSITION_CONFIGS[fallbackPosition];
    const fallbackCoords = fallbackConfig.getCoordinates(
      triggerRect,
      contentRect,
      gap,
    );

    if (checkPositionFits(fallbackCoords, contentRect, padding)) {
      return { position: fallbackPosition, coordinates: fallbackCoords };
    }
  }

  return { position: preferredPosition, coordinates: preferredCoords };
}

export function clampCoordinates(
  coords: PositionCoordinates,
  contentRect: { width: number; height: number },
  padding: number,
): PositionCoordinates {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  return {
    left: Math.max(
      padding,
      Math.min(coords.left, viewportWidth - contentRect.width - padding),
    ),
    top: Math.max(
      padding,
      Math.min(coords.top, viewportHeight - contentRect.height - padding),
    ),
  };
}

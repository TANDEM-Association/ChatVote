import { type PartyDetails } from "@lib/party-details";
import { type Source } from "@lib/stores/chat-store.types";
import { type ClassValue, clsx } from "clsx";
import { type Timestamp } from "firebase/firestore";
import { twMerge } from "tailwind-merge";

import { GROUP_PARTY_ID } from "./constants";
import { getAppUrl } from "./url";

export const IS_EMBEDDED = process.env.IS_EMBEDDED === "true";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const keyStr =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";

export function triplet(e1: number, e2: number, e3: number) {
  return (
    keyStr.charAt(e1 >> 2) +
    keyStr.charAt(((e1 & 3) << 4) | (e2 >> 4)) +
    keyStr.charAt(((e2 & 15) << 2) | (e3 >> 6)) +
    keyStr.charAt(e3 & 63)
  );
}

function rgbDataURL(r: number, g: number, b: number) {
  return `data:image/gif;base64,R0lGODlhAQABAPAA${
    triplet(0, r, g) + triplet(b, 255, 255)
  }/yH5BAAAAAAALAAAAAABAAEAAAICRAEAOw==`;
}

function hexToRgb(hex: string) {
  const cleanedHex = hex.replace("#", "");

  const r = Number.parseInt(cleanedHex.substring(0, 2), 16);
  const g = Number.parseInt(cleanedHex.substring(2, 4), 16);
  const b = Number.parseInt(cleanedHex.substring(4, 6), 16);

  return { r, g, b };
}

export function hexDataURL(hex: string) {
  const { r, g, b } = hexToRgb(hex);
  return rgbDataURL(r, g, b);
}

export function prettifiedUrlName(url: string) {
  const regex = /https?:\/\/(?:www\.)?(?<domain>[^\/]+\.[a-z]+)/;
  const match = url.match(regex);

  if (match?.groups) {
    return match.groups.domain;
  } else {
    return url;
  }
}

export function prettifiedShortSourceName(source: string): string {
  const shortenings: { [key: string]: string } = {
    Projet: "Proj.",
    Programme: "Prg.",
    Électoral: "Élect.",
  };

  return source
    .split(" ")
    .map((word) => shortenings[word] || word)
    .join(" ");
}

export function generateUuid() {
  return crypto.randomUUID();
}

export function firestoreTimestampToDate(
  timestamp: Timestamp | Date | undefined,
) {
  if (!timestamp) {
    return;
  }

  if (timestamp instanceof Date) {
    return timestamp;
  }

  return timestamp.toDate();
}

export function areSetsEqual(set1: Set<string>, set2: Set<string>): boolean {
  if (set1.size !== set2.size) return false;
  return [...set1].every((item) => set2.has(item));
}

export function prettyDate(
  dateString: string,
  format: "full" | "long" | "medium" | "short" = "long",
): string {
  const date = new Date(dateString);

  const options: Intl.DateTimeFormatOptions = {
    dateStyle: format,
  };

  return new Intl.DateTimeFormat("fr-FR", options).format(date);
}

export function buildPdfUrl(source: Source): URL | null {
  if (!source.url) return null;

  return new URL(
    `/pdf/view?page=${encodeURIComponent(
      source.page ?? 1,
    )}&pdf=${encodeURIComponent(source.url)}`,
    window.location.href,
  );
}

export async function generateOgImageUrl(sessionType: string) {
  if (sessionType === GROUP_PARTY_ID) {
    return;
  }

  const baseUrl = await getAppUrl();

  let party: PartyDetails | undefined;
  try {
    const response = await fetch(`${baseUrl}/api/parties`);
    if (!response.ok) {
      throw new Error("Failed to fetch parties");
    }

    const parties = await response.json();

    party = parties.find((p: PartyDetails) => p.party_id === sessionType);
  } catch (error) {
    console.error(error);
  }

  if (!party) {
    return;
  }

  const url = new URL(baseUrl);
  const imageUrl = new URL("/api/og", url);
  imageUrl.searchParams.set(
    "partyImageUrl",
    `${baseUrl}${buildPartyImageUrl(party.party_id)}`,
  );
  imageUrl.searchParams.set(
    "backgroundColor",
    party.background_color ?? "#fff",
  );

  return imageUrl.toString();
}

export function buildPartyImageUrl(partyId: string) {
  return `/images/${partyId}.webp`;
}

/**
 * Converts literal escape sequences in a string to their actual characters.
 * Handles common escape sequences: \n, \t, \r, \\
 */
export function unescapeString(str: string): string {
  return str
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "\t")
    .replace(/\\r/g, "\r")
    .replace(/\\\\/g, "\\");
}

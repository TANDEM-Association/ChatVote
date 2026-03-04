"use server";

import { cookies } from "next/headers";

import { defaultLocale, type Locale } from "@i18n/config";

import { COOKIE_NAME } from "./constants";

export async function getLocale() {
  const store = await cookies();
  return (store.get(COOKIE_NAME)?.value || defaultLocale) as Locale;
}

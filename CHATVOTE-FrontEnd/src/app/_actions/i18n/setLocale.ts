"use server";

import { cookies } from "next/headers";

import { type Locale } from "@i18n/config";

import { COOKIE_NAME } from "./constants";

export async function setLocale(locale: Locale) {
  const store = await cookies();
  store.set(COOKIE_NAME, locale);
}

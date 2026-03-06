import { cookies } from "next/headers";

import { COOKIE_NAME } from "@actions/i18n/constants";
import { getRequestConfig } from "next-intl/server";

import { defaultLocale, type Locale } from "./config";

export default getRequestConfig(async () => {
  const store = await cookies();
  const locale = (store.get(COOKIE_NAME)?.value || defaultLocale) as Locale;

  return {
    locale,
    messages: (await import(`./messages/${locale}.json`)).default,
  };
});

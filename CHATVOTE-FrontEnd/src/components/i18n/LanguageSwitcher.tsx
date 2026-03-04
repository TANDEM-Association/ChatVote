"use client";

import React, { useTransition } from "react";

import { useRouter } from "next/navigation";

import { setLocale } from "@actions/i18n/setLocale";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@components/ui/select";
import { type Locale, locales } from "@i18n/config";
import { GlobeIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { useAppContext } from "../providers/app-provider";

export const LanguageSwitcher: React.FC = () => {
  const t = useTranslations("language");
  const router = useRouter();
  const { locale } = useAppContext();
  const [isPending, startTransition] = useTransition();

  const handleLocaleChange = (newLocale: string) => {
    startTransition(async () => {
      await setLocale(newLocale as Locale);
      router.refresh();
    });
  };

  return (
    <Select
      value={locale}
      onValueChange={handleLocaleChange}
      disabled={isPending}
    >
      <SelectTrigger className="h-8 w-fit cursor-pointer gap-1 border-none bg-transparent px-2 text-sm focus:ring-0">
        <GlobeIcon className="size-4" />
        <SelectValue placeholder={t("select")} />
      </SelectTrigger>
      <SelectContent className="border-border min-w-16 overflow-hidden rounded-md border bg-neutral-200 shadow-lg data-[side=bottom]:translate-y-px dark:bg-purple-900">
        {locales.map((locale) => {
          return (
            <SelectItem
              key={locale}
              value={locale}
              className="cursor-pointer rounded-md px-3 py-2 transition-all duration-300 ease-in-out hover:bg-neutral-700"
            >
              {t(locale)}
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
};

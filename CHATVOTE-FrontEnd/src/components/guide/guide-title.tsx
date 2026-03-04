"use client";

import { useTranslations } from "next-intl";

export const GuideTitle = () => {
  const t = useTranslations("guide");

  return (
    <h1 className="mt-4 mb-2 text-xl font-bold md:text-2xl">{t("title")}</h1>
  );
};

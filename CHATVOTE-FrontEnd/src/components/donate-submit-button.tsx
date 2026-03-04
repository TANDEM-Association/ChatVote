"use client";

import { useFormStatus } from "react-dom";

import { useTranslations } from "next-intl";

import { Button } from "./ui/button";

type Props = {
  isDisabled: boolean;
};

export const DonateSubmitButton = ({ isDisabled }: Props) => {
  const t = useTranslations("donation");
  const { pending } = useFormStatus();

  return (
    <Button
      className="w-40 rounded-md border border-neutral-950 dark:border-neutral-100"
      disabled={isDisabled}
      isLoading={pending}
      type="submit"
    >
      {t("donateButton")}
    </Button>
  );
};

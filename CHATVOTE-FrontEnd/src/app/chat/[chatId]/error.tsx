"use client";

import { Button } from "@components/ui/button";
import { BugIcon } from "lucide-react";
import { useTranslations } from "next-intl";

export type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

function ErrorView({ error, reset }: ErrorProps) {
  const t = useTranslations("common");

  return (
    <div className="flex size-full flex-col items-center justify-center gap-2 px-4">
      <BugIcon className="text-destructive size-12" />
      <h1 className="text-center text-2xl font-bold">
        {t("oops")}
        <br />
        {t("errorOccurred")}
      </h1>
      <p className="text-muted-foreground text-center text-sm">
        {error.message}
      </p>
      <Button onClick={reset} className="mt-2">
        {t("retry")}
      </Button>
    </div>
  );
}

export default ErrorView;

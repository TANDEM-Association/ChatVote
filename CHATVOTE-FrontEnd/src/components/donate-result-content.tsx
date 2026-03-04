"use client";

import React from "react";

import Link from "next/link";

import { Button } from "@components/ui/button";
import {
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@components/ui/card";
import { CircleCheckIcon, FrownIcon } from "lucide-react";
import { useTranslations } from "next-intl";

type Props = {
  isSuccess: boolean;
};

const DonateResultContent = ({ isSuccess }: Props) => {
  const t = useTranslations("donateResult");

  if (isSuccess === false) {
    return (
      <React.Fragment>
        <CardHeader className="flex flex-col items-center justify-center">
          <FrownIcon className="size-16" />
          <CardTitle className="pt-4 text-center">{t("failed")}</CardTitle>
          <CardDescription className="pt-2 text-center">
            {t("failedDescription")}
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Button className="w-full" asChild>
            <Link href="/donate">{t("backToDonate")}</Link>
          </Button>
        </CardFooter>
      </React.Fragment>
    );
  }

  return (
    <React.Fragment>
      <CardHeader className="flex flex-col items-center justify-center">
        <CircleCheckIcon className="size-16" />
        <CardTitle className="pt-4 text-center">{t("success")}</CardTitle>
        <CardDescription className="pt-2 text-center">
          {t("successDescription")}
        </CardDescription>
      </CardHeader>
      <CardFooter>
        <Button className="w-full" asChild>
          <Link href="/">{t("backToHome")}</Link>
        </Button>
      </CardFooter>
    </React.Fragment>
  );
};

export default DonateResultContent;

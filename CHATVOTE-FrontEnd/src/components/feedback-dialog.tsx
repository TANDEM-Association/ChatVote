"use client";

import React, { useState } from "react";

import Link from "next/link";

import { config } from "@config";
import { MailIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "./ui/button";
import { Modal } from "./ui/modal";

type Props = {
  children: React.ReactNode;
};

const FeedbackDialog = ({ children }: Props) => {
  const t = useTranslations("feedback");
  const [isOpen, setIsOpen] = useState(false);

  return (
    <React.Fragment>
      <div onClick={() => setIsOpen(true)}>{children}</div>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="w-full max-w-md p-6"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold">{t("title")}</h2>
          <p className="text-muted-foreground text-sm">{t("description")}</p>
        </div>

        <div className="flex w-full flex-col gap-2">
          <Button asChild variant="outline">
            <Link href={`mailto:${config.contactEmail}`} target="_top">
              <MailIcon />
              {t("writeEmail")}
            </Link>
          </Button>
        </div>
      </Modal>
    </React.Fragment>
  );
};

export default FeedbackDialog;

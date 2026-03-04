"use client";

import React, { useState } from "react";

import { Modal } from "@components/ui/modal";
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  CpuIcon,
  GitBranch,
} from "lucide-react";
import { useTranslations } from "next-intl";

const AiDisclaimerContent = () => {
  const t = useTranslations("aiDisclaimer");

  return (
    <div className="text-foreground text-sm">
      <p>{t("intro")}</p>

      <ul className="flex list-inside flex-col gap-4 py-4 *:flex *:items-center *:gap-2">
        <li>
          <CpuIcon className="mr-2 size-6 shrink-0" />
          <span className="inline-block">{t("automated")}</span>
        </li>
        <li>
          <AlertCircleIcon className="mr-2 size-6 shrink-0" />
          <span className="inline-block">{t("notOfficial")}</span>
        </li>
        <li>
          <GitBranch className="mr-2 size-6 shrink-0" />
          <span className="inline-block">{t("complexPositions")}</span>
        </li>
        <li>
          <AlertTriangleIcon className="mr-2 size-6 shrink-0" />
          <span className="inline-block">{t("inaccuracies")}</span>
        </li>
      </ul>

      <p>{t("educationalTool")}</p>
    </div>
  );
};

const AiDisclaimer = () => {
  const t = useTranslations("aiDisclaimer");
  const [isOpen, setIsOpen] = useState(false);

  return (
    <React.Fragment>
      <p className="text-muted-foreground my-2 text-center text-xs">
        {t("canMakeErrors")}{" "}
        <button
          className="cursor-pointer font-semibold underline"
          onClick={() => setIsOpen(true)}
        >
          {t("learnMore")}
        </button>
      </p>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="w-full max-w-lg p-6"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </div>
        <AiDisclaimerContent />
      </Modal>
    </React.Fragment>
  );
};

export default AiDisclaimer;

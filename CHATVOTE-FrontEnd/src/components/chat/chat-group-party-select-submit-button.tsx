"use client";

import { useEffect, useMemo } from "react";

import { useRouter } from "next/navigation";

import { useTranslations } from "next-intl";

import { Button } from "../ui/button";

type Props = {
  selectedPartyIds: string[];
  onSubmit: () => void;
  addPartiesToChat?: boolean;
};

const ChatGroupPartySelectSubmitButton = ({
  selectedPartyIds,
  onSubmit,
  addPartiesToChat,
}: Props) => {
  const t = useTranslations("chat.groupSelect");
  const router = useRouter();

  const navigateUrl = useMemo(() => {
    const searchParams = new URLSearchParams();
    selectedPartyIds.forEach((partyId) => {
      searchParams.append("party_id", partyId);
    });

    return `/chat?${searchParams.toString()}`;
  }, [selectedPartyIds]);

  const handleSubmit = () => {
    onSubmit();
    if (!addPartiesToChat) {
      router.push(navigateUrl);
    }
  };

  useEffect(() => {
    if (!addPartiesToChat) {
      router.prefetch(navigateUrl);
    }
  }, [addPartiesToChat, navigateUrl, router]);

  return (
    <Button
      className="mx-auto w-55 rounded-md border border-neutral-950 dark:border-neutral-100"
      onClick={handleSubmit}
    >
      {addPartiesToChat ? t("modifyButton") : t("startButton")}
    </Button>
  );
};

export default ChatGroupPartySelectSubmitButton;

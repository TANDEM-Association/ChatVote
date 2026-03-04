"use client";

import React, { useState } from "react";

import { cn } from "@lib/utils";
import { ThumbsDown } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "../ui/button";
import { Modal } from "../ui/modal";
import { Textarea } from "../ui/textarea";

type Props = {
  isDisliked: boolean;
  onDislikeFeedback: (details: string) => void;
  feedbackDetail?: string;
};

const ChatDislikeFeedbackButton = ({
  isDisliked,
  onDislikeFeedback,
  feedbackDetail,
}: Props) => {
  const t = useTranslations("chat.dislikeFeedback");
  const [isOpen, setIsOpen] = useState(false);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsOpen(false);

    const formData = new FormData(e.target as HTMLFormElement);
    const details = formData.get("details") as string;
    onDislikeFeedback(details);
  };

  return (
    <React.Fragment>
      <Button
        variant="ghost"
        size="icon"
        className="group/dislike size-8 group-data-[has-message-background=true]:hover:bg-zinc-200 group-data-[has-message-background=true]:dark:hover:bg-zinc-800"
        onClick={() => setIsOpen(true)}
      >
        <div className="group-hover/dislike:-translate-y-2 group-hover/dislike:scale-125 group-hover/dislike:transition-transform group-hover/dislike:duration-200 group-hover/dislike:ease-in-out">
          <ThumbsDown className={cn(isDisliked && "fill-foreground/30")} />
        </div>
      </Button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="w-full max-w-md p-6"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold">{t("title")}</h2>
          <p className="text-muted-foreground text-sm">{t("description")}</p>
        </div>
        <form onSubmit={handleSubmit}>
          <Textarea
            placeholder={t("placeholder")}
            className="w-full"
            name="details"
            defaultValue={feedbackDetail}
          />
          <Button className="mt-4 w-full" type="submit">
            {t("submit")}
          </Button>
        </form>
      </Modal>
    </React.Fragment>
  );
};

export default ChatDislikeFeedbackButton;

"use client";

import { useEffect, useState } from "react";

import { useAnonymousAuth } from "@components/anonymous-auth";
import { useChatStore } from "@components/providers/chat-store-provider";
import { Button } from "@components/ui/button";
import { FilloutPopupEmbed } from "@fillout/react";
import { SURVEY_BANNER_MIN_MESSAGE_COUNT } from "@lib/stores/chat-store";
import { track } from "@vercel/analytics/react";
import { MessageCircleHeartIcon, XIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import "@fillout/react/style.css";

const SurveyBanner = () => {
  const t = useTranslations("chat.survey");
  const sessionId = useChatStore((state) => state.chatId);
  const [open, setOpen] = useState(false);
  const { user, updateUser, loading } = useAnonymousAuth();
  const showSurveyBanner = useChatStore(
    (state) =>
      state.messages.length >= SURVEY_BANNER_MIN_MESSAGE_COUNT &&
      !loading &&
      !user?.survey_status?.state,
  );
  const [optimisticShowSurveyBanner, setOptimisticShowSurveyBanner] =
    useState(showSurveyBanner);
  const [prevShowSurveyBanner, setPrevShowSurveyBanner] =
    useState(showSurveyBanner);

  // Adjust state during render (React-recommended pattern for prop/state transitions)
  if (prevShowSurveyBanner !== showSurveyBanner) {
    setPrevShowSurveyBanner(showSurveyBanner);
    if (showSurveyBanner) {
      setOptimisticShowSurveyBanner(true);
    }
  }

  const handleCloseSurvey = () => {
    setOpen(false);
    setOptimisticShowSurveyBanner(false);

    if (!user?.uid) return;
    updateUser({
      survey_status: {
        state: "opened",
        timestamp: new Date(),
      },
    });
  };

  const handleForceCloseSurvey = () => {
    setOptimisticShowSurveyBanner(false);

    track("survey_banner_force_closed");

    if (!user?.uid) return;
    updateUser({
      survey_status: {
        state: "closed",
        timestamp: new Date(),
      },
    });
  };

  useEffect(() => {
    if (showSurveyBanner) return;

    if (
      user?.survey_status?.state === "closed" &&
      user?.survey_status?.timestamp &&
      user?.survey_status?.timestamp instanceof Date
    ) {
      const now = new Date();
      const diff = now.getTime() - user.survey_status.timestamp.getTime();

      if (diff > 1000 * 60 * 60 * 24) {
        updateUser({
          survey_status: null,
        });
      }
    }
  }, [
    showSurveyBanner,
    updateUser,
    user?.survey_status?.state,
    user?.survey_status?.timestamp,
  ]);

  if (!optimisticShowSurveyBanner) {
    return null;
  }

  return (
    <div className="bg-muted flex flex-col gap-2 rounded-lg p-4 group-data-has-message-background:mx-4 group-data-has-message-background:mb-4 group-data-has-message-background:bg-zinc-200 group-data-has-message-background:dark:bg-zinc-800">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold">
          👆🏼 {t("title")}
        </h2>

        <Button
          size="icon"
          variant="ghost"
          className="size-6"
          onClick={handleForceCloseSurvey}
        >
          <XIcon />
        </Button>
      </div>
      <p className="text-muted-foreground text-sm">
        {t("description")}
      </p>
      <Button size="sm" variant="default" onClick={() => setOpen(true)}>
        <MessageCircleHeartIcon />
        {t("startSurvey")}
      </Button>
      {open && (
        <FilloutPopupEmbed
          filloutId="cGozfJUor9us"
          onClose={handleCloseSurvey}
          parameters={{
            session_id: sessionId,
          }}
          inheritParameters
        />
      )}
    </div>
  );
};

export default SurveyBanner;

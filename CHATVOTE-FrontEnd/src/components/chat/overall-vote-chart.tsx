"use client";

import React, { useMemo } from "react";

import { type Vote } from "@lib/socket.types";
import { useTranslations } from "next-intl";

import VoteChart from "./vote-chart";

type Props = {
  vote: Vote;
};

function OverallVoteChart({ vote }: Props) {
  const t = useTranslations("chat.voteChart");

  const [resultStatement, percentageStatement] = useMemo(() => {
    const { yes, no, abstain } = vote.voting_results.overall;

    const totalVotes = yes + no + abstain;

    if (totalVotes === 0) {
      return [t("noValidVotes"), t("noResultDetermined")];
    }

    let outcome: "adopted" | "rejected" | "tie";
    let percentage: number;

    if (yes > no) {
      outcome = "adopted";
      percentage = (yes / totalVotes) * 100;
    } else if (no > yes) {
      outcome = "rejected";
      percentage = (no / totalVotes) * 100;
    } else {
      outcome = "tie";
      percentage = (no / totalVotes) * 100;
    }

    const outcomeLabel =
      outcome === "adopted"
        ? t("adopted")
        : outcome === "rejected"
          ? t("rejected")
          : t("tie");

    const resultStatement = (
      <React.Fragment>
        {t("motion")}{" "}
        <span className="font-bold">
          {outcomeLabel.charAt(0).toUpperCase() + outcomeLabel.slice(1)}.
        </span>
      </React.Fragment>
    );

    let percentageStatement: string;
    if (outcome === "tie") {
      percentageStatement = t("motionTie", {
        percentage: percentage.toFixed(1),
      });
    } else if (outcome === "adopted") {
      percentageStatement = t("motionAdopted", {
        percentage: percentage.toFixed(1),
      });
    } else {
      percentageStatement = t("motionRejected", {
        percentage: percentage.toFixed(1),
      });
    }

    return [resultStatement, percentageStatement];
  }, [vote.voting_results.overall, t]);

  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-4">
      <VoteChart
        voteResults={vote.voting_results.overall}
        memberCount={vote.voting_results.overall.members}
      />

      <div className="flex flex-col items-center justify-center text-center">
        <p>{resultStatement}</p>
        <p className="text-muted-foreground text-xs">{percentageStatement}</p>
      </div>
    </section>
  );
}

export default OverallVoteChart;

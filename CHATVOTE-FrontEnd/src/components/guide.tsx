"use client";

import Link from "next/link";

import { config } from "@config";
import {
  MessageCircleQuestionIcon,
  MessageCircleReplyIcon,
  PlusIcon,
  TextSearchIcon,
  VoteIcon,
  WaypointsIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";

import ChatActionButtonHighlight from "./chat/chat-action-button-highlight";
import { MAX_SELECTABLE_PARTIES } from "./chat/chat-group-party-select-content";
import ProConIcon from "./chat/pro-con-icon";
import { AccordionGroup, AccordionItem } from "./ui/accordion";
import { Button } from "./ui/button";

function buildQuestionLink(question: string) {
  return `/chat?q=${question}`;
}

function Guide() {
  const t = useTranslations("guide");
  const tChat = useTranslations("chat.actions");

  const partySpecificQuestions = t.raw(
    "questions.partyExamples",
  ) as unknown as string[];
  const compareQuestions = t.raw(
    "questions.compareExamples",
  ) as unknown as string[];
  const generalQuestions = t.raw(
    "questions.generalExamples",
  ) as unknown as string[];

  return (
    <article>
      <section>
        <p>
          <span className="font-bold underline">chatvote</span>{" "}
          {t("intro.description")}
        </p>

        <p className="mt-4 text-sm font-semibold">{t("intro.processTitle")}</p>

        <ul className="[&_li]:mt-4 [&_li]:text-sm">
          <li className="relative pl-10">
            <MessageCircleQuestionIcon className="absolute top-0 left-0" />
            {t("intro.step1")}
          </li>
          <li className="relative pl-10">
            <TextSearchIcon className="absolute top-0 left-0" />
            <span className="font-bold underline">chatvote</span>{" "}
            {t("intro.step2")}
          </li>
          <li className="relative pl-10">
            <MessageCircleReplyIcon className="absolute top-0 left-0" />
            {t("intro.step3")}
          </li>
          <li className="relative pl-10">
            <WaypointsIcon className="absolute top-0 left-0" />
            {t("intro.step4")}
          </li>
        </ul>
      </section>

      <section className="mt-6">
        <AccordionGroup>
          <AccordionItem title={t("questions.title")}>
            <div className="font-bold">{t("questions.whatCanIAsk")}</div>
            <div>
              {t("questions.description")}
              <br />
              <br />
              <span className="font-bold">
                {t("questions.partySpecificTitle")}
              </span>
              <ul className="list-outside list-disc py-2 pl-4 [&_li]:pt-1">
                {partySpecificQuestions.map((question) => {
                  return (
                    <li key={question}>
                      <Link
                        className="underline"
                        href={buildQuestionLink(question)}
                      >
                        {question}
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <br />
              <span className="font-bold">{t("questions.compareTitle")}</span>
              <ul className="list-outside list-disc py-2 pl-4 [&_li]:pt-1">
                {compareQuestions.map((question) => {
                  return (
                    <li key={question}>
                      <Link
                        className="underline"
                        href={buildQuestionLink(question)}
                      >
                        {question}
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <br />
              <span className="font-bold">{t("questions.generalTitle")}</span>
              <ul className="list-outside list-disc py-2 pl-4 [&_li]:pt-1">
                {generalQuestions.map((question) => {
                  return (
                    <li key={question}>
                      <Link
                        className="underline"
                        href={buildQuestionLink(question)}
                      >
                        {question}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          </AccordionItem>

          <AccordionItem title={t("numberOfParties.title")}>
            <div className="font-bold">{t("numberOfParties.question")}</div>
            <div>
              {t("numberOfParties.description", {
                max: MAX_SELECTABLE_PARTIES,
              })}
              <br />
              <br />
              {t("numberOfParties.addMore")}{" "}
              <span className="inline-block">
                <PlusIcon className="bg-primary text-primary-foreground size-4 rounded-full p-1" />
              </span>
            </div>
          </AccordionItem>

          <AccordionItem title={t("evaluatePosition.title")}>
            <p>
              {t("evaluatePosition.description")}
              <br />
              {t("evaluatePosition.perplexityInfo")}
            </p>
            <div className="my-2 flex items-center justify-center">
              <div className="relative rounded-md">
                <Button
                  variant="outline"
                  className="h-8 px-2 group-data-has-message-background:bg-zinc-100 group-data-has-message-background:hover:bg-zinc-200 group-data-has-message-background:dark:bg-zinc-900 group-data-has-message-background:dark:hover:bg-zinc-800"
                  tooltip={tChat("evaluatePositionTooltip")}
                  type="button"
                >
                  <ProConIcon />
                  <span className="text-xs">{tChat("evaluatePosition")}</span>
                </Button>
                <ChatActionButtonHighlight showHighlight />
              </div>
            </div>
          </AccordionItem>

          <AccordionItem title={t("votingBehavior.title")}>
            <p>{t("votingBehavior.description")}</p>
            <div className="my-2 flex items-center justify-center">
              <div className="relative rounded-md">
                <Button
                  variant="outline"
                  className="h-8 px-2 group-data-has-message-background:bg-zinc-100 group-data-has-message-background:hover:bg-zinc-200 group-data-has-message-background:dark:bg-zinc-900 group-data-has-message-background:dark:hover:bg-zinc-800"
                  tooltip={tChat("votingBehaviorTooltip")}
                >
                  <VoteIcon />
                  <span className="text-xs">{tChat("votingBehavior")}</span>
                </Button>

                <ChatActionButtonHighlight showHighlight />
              </div>
            </div>
          </AccordionItem>

          <AccordionItem title={t("data.title")}>
            <div className="font-bold">{t("data.question")}</div>
            <div>
              {t("data.description")}{" "}
              <span className="font-bold underline">chatvote</span>{" "}
              {t("data.description")}
              <ol className="list-outside list-decimal py-4 pl-4 [&_li]:pt-1">
                <li>
                  <div className="pl-2">
                    <span className="font-bold">{t("data.programs")}</span>{" "}
                    {t("data.programsDescription")}
                  </div>
                </li>
                <li>
                  <div className="pl-2">
                    <span className="font-bold">
                      {t("data.positionPapers")}
                    </span>{" "}
                    {t("data.positionPapersDescription")}
                  </div>
                </li>
                <li>
                  <div className="pl-2">
                    <span className="font-bold">
                      {t("data.internetSources")}
                    </span>{" "}
                    <span className="font-bold underline">chatvote</span>{" "}
                    {t("data.internetSourcesDescription")}
                  </div>
                </li>
              </ol>
              <br />
              {t("data.sourcesLink")}
            </div>
          </AccordionItem>
          <AccordionItem title={t("guidelines.title")}>
            <div className="font-bold">{t("guidelines.question")}</div>
            <div>
              {t("guidelines.description")}
              <ol className="list-outside list-decimal py-4 pl-4 [&_li]:pt-1">
                <li>
                  <div className="pl-2">
                    <span className="font-bold">
                      {t("guidelines.sourceBased")}
                    </span>{" "}
                    {t("guidelines.sourceBasedDescription")}
                  </div>
                </li>
                <li>
                  <div className="pl-2">
                    <span className="font-bold">
                      {t("guidelines.neutrality")}
                    </span>{" "}
                    {t("guidelines.neutralityDescription")}
                  </div>
                </li>
                <li>
                  <div className="pl-2">
                    <span className="font-bold">
                      {t("guidelines.transparency")}
                    </span>{" "}
                    {t("guidelines.transparencyDescription")}
                  </div>
                </li>
              </ol>
            </div>
          </AccordionItem>
          <AccordionItem title={t("partySelection.title")}>
            <div className="font-bold">{t("partySelection.question")}</div>
            <div>
              {t("partySelection.description")}
              <br />
              <br />
              {t("partySelection.missingParty")}{" "}
              <Link
                href={`mailto:${config.contactEmail}`}
                className="underline"
              >
                contact@chatvote.org
              </Link>
            </div>
          </AccordionItem>
        </AccordionGroup>
      </section>
    </article>
  );
}

export default Guide;

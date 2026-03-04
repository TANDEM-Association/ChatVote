"use client";

import React from "react";

import Image from "next/image";
import Link from "next/link";

import LoginButton from "@components/auth/login-button";
import DonationDialog from "@components/donation-dialog";
import FeedbackDialog from "@components/feedback-dialog";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
} from "@components/ui/sidebar";
import { config } from "@config";
import { type ChatSession } from "@lib/firebase/firebase.types";
import { type Auth } from "@lib/types/auth";
import { HeartHandshakeIcon, MessageCircleIcon, UserIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import ChatSidebarGroupSelect from "./chat-sidebar-group-select";
import SidebarHistory from "./sidebar-history";
import SidebarNewChatButtons from "./sidebar-new-chat-buttons";

const websiteUrl = config.websiteUrl;
const aboutPage = `${websiteUrl}/about`;

type Props = {
  auth: Auth;
  history?: ChatSession[];
};

const ChatSidebarContent = ({ auth, history }: Props) => {
  const t = useTranslations("chat.sidebar");
  const isAuthenticated = auth.session !== null && !auth.session.isAnonymous;

  return (
    <Sidebar variant={"sidebar"}>
      <SidebarContent>
        <div className={"flex w-full items-center justify-between gap-2"}>
          <div className={"flex items-center"}>
            <Link href="https://tndm.fr" className="flex items-center">
              <Image
                src="/images/logos/tandem.svg"
                alt="tandem"
                width={0}
                height={0}
                sizes="100vw"
                className="size-12"
              />
            </Link>
            <Link href="/" className="flex items-center">
              <Image
                src="/images/logos/chatvote.svg"
                alt="chatvote"
                width={0}
                height={0}
                sizes="100vw"
                className="size-12"
              />
            </Link>
          </div>

          <SidebarTrigger />
        </div>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarGroupLabel>{t("newChat")}</SidebarGroupLabel>
            <SidebarNewChatButtons />

            <ChatSidebarGroupSelect />
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>{t("supportChatvote")}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <LoginButton
                  isAuthenticated={isAuthenticated}
                  user={auth.user}
                  noUserChildren={
                    <SidebarMenuButton>
                      <UserIcon className="size-4" />
                      <span>{t("login")}</span>
                    </SidebarMenuButton>
                  }
                  userChildren={
                    <SidebarMenuButton>
                      <UserIcon className="size-4" />
                      <span>{t("account")}</span>
                    </SidebarMenuButton>
                  }
                />
              </SidebarMenuItem>
              <SidebarMenuItem>
                <DonationDialog>
                  <SidebarMenuButton>
                    <HeartHandshakeIcon className="size-4 text-red-400" />
                    <span>{t("donate")}</span>
                  </SidebarMenuButton>
                </DonationDialog>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <FeedbackDialog>
                  <SidebarMenuButton>
                    <MessageCircleIcon className="size-4 text-blue-400" />
                    <span>{t("feedback")}</span>
                  </SidebarMenuButton>
                </FeedbackDialog>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarHistory history={history} />

        <SidebarGroup>
          <SidebarGroupLabel>{t("information")}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <Link href={aboutPage}>{t("about")}</Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <Link href="/guide">{t("howItWorks")}</Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <Link href="/legal-notice">{t("legalNotice")}</Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <Link href="/privacy-policy">{t("privacy")}</Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
};

export default ChatSidebarContent;

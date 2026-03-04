"use client";

import React from "react";

import Image from "next/image";
import Link from "next/link";

import LoginButton from "@components/auth/login-button";
import ChatSidebarGroupSelect from "@components/chat/sidebar/chat-sidebar-group-select";
import DonationDialog from "@components/donation-dialog";
import FeedbackDialog from "@components/feedback-dialog";
import { Button } from "@components/ui/button";
import { SidebarTrigger, useSidebar } from "@components/ui/sidebar";
import { type Auth } from "@lib/types/auth";
import { cn } from "@lib/utils";
import { Heart, MessageSquareWarning, User, UserCheck } from "lucide-react";

type Props = {
  auth: Auth;
};

const ChatSidebarDesktop = ({ auth }: Props) => {
  const { toggleSidebar } = useSidebar();
  const isAuthenticated = auth.session !== null && !auth.session.isAnonymous;

  return (
    <div className="hidden h-screen w-16 flex-none flex-col items-center gap-12 overflow-hidden border-r border-purple-500 bg-purple-900 px-2 py-4 md:flex">
      <div className={"flex flex-col items-center"}>
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
        <SidebarTrigger />
      </div>
      <div className={"flex flex-col items-center gap-4"}>
        <ChatSidebarGroupSelect iconOnly />

        <LoginButton
          isAuthenticated={isAuthenticated}
          noUserChildren={
            <Button
              data-sidebar="login"
              variant="ghost"
              size="icon"
              className={cn("size-10")}
            >
              <User />
            </Button>
          }
          userChildren={
            <Button
              data-sidebar="login"
              variant="ghost"
              size="icon"
              className={cn("size-10")}
            >
              <UserCheck />
            </Button>
          }
        />
        <DonationDialog>
          <Button
            data-sidebar="donation"
            variant="ghost"
            size="icon"
            className={cn("size-10")}
          >
            <Heart />
          </Button>
        </DonationDialog>
        <FeedbackDialog>
          <Button
            data-sidebar="feedback"
            variant="ghost"
            size="icon"
            className={cn("size-10")}
          >
            <MessageSquareWarning />
          </Button>
        </FeedbackDialog>
      </div>
    </div>
  );
};

export default ChatSidebarDesktop;

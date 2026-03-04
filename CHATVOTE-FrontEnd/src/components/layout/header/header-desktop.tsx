"use client";

import React from "react";

import Image from "next/image";
import Link from "next/link";

import LoginButton from "@components/auth/login-button";
import { UserAvatar } from "@components/auth/user-avatar";
import EmbedOpenWebsiteButton from "@components/embed-open-website-button";
import { LanguageSwitcher } from "@components/i18n/LanguageSwitcher";
import { Button } from "@components/ui/button";
import { Separator } from "@components/ui/separator";
import { type User } from "@lib/types/auth";
import { IS_EMBEDDED } from "@lib/utils";
import { useTranslations } from "next-intl";

import { NavbarItem, type NavbarItemDetails } from "./navbar-item";

type HeaderDesktopProps = {
  user: User | null;
  isAuthenticated: boolean;
};

export const HeaderDesktop: React.FC<HeaderDesktopProps> = ({
  user,
  isAuthenticated,
}) => {
  const tNav = useTranslations("navigation");
  const tAuth = useTranslations("auth");

  const tabs: NavbarItemDetails[] = [
    {
      label: tNav("home"),
      href: "/",
    },
    {
      label: tNav("guide"),
      href: "/guide",
    },
  ];

  return (
    <header className="border-border bg-background sticky top-0 z-30 border-b px-4 py-2 md:px-0">
      <div className="relative mx-auto flex max-w-xl items-center justify-start gap-2 md:flex-row">
        <Link href="/" className="shrink-0">
          <Image
            src="/images/logos/chatvote.svg"
            alt="chatvote"
            width={0}
            height={0}
            sizes="100vw"
            className="size-8 rounded-md md:size-12"
          />
        </Link>

        {IS_EMBEDDED ? (
          <div className="absolute inset-0 flex items-center justify-center md:hidden">
            <EmbedOpenWebsiteButton />
          </div>
        ) : null}
        <nav className="flex flex-col items-center justify-between md:w-full md:flex-row">
          <div className="flex w-full items-center">
            {IS_EMBEDDED === false ? (
              <React.Fragment>
                {tabs.map((tab) => {
                  return <NavbarItem key={tab.href} details={tab} />;
                })}
              </React.Fragment>
            ) : (
              <EmbedOpenWebsiteButton />
            )}
          </div>

          <div className="flex w-full items-center justify-end gap-2">
            <LanguageSwitcher />
            <Separator orientation="vertical" className="hidden h-8 md:block" />
            <LoginButton
              isAuthenticated={isAuthenticated}
              user={user}
              noUserChildren={
                <Button variant="default" size="sm">
                  {tAuth("login")}
                </Button>
              }
              userChildren={<UserAvatar user={user} />}
            />
          </div>
        </nav>
      </div>
    </header>
  );
};

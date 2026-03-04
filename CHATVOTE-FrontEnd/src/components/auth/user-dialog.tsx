"use client";

import React, { useState } from "react";

import { Button } from "@components/ui/button";
import { Input } from "@components/ui/input";
import { Label } from "@components/ui/label";
import { Modal } from "@components/ui/modal";
import { type User } from "@lib/types/auth";
import { getAuth, signOut } from "firebase/auth";
import { LogOutIcon } from "lucide-react";
import { useTranslations } from "next-intl";

type UserDialogProps = {
  children: React.ReactNode;
  user: User | null;
};

const UserDialog: React.FC<UserDialogProps> = ({ children, user }) => {
  const t = useTranslations("auth");
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleLogout = async () => {
    setIsLoading(true);
    const auth = getAuth();
    await signOut(auth);
    setIsOpen(false);
    setIsLoading(false);
  };

  return (
    <React.Fragment>
      <div onClick={() => setIsOpen(true)}>{children}</div>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="w-full max-w-md p-6"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold">{t("account.title")}</h2>
          <p className="text-muted-foreground text-sm">
            {t("account.description")}
          </p>
        </div>

        <section className="flex flex-col gap-4">
          {user?.displayName ? (
            <div className="flex flex-col gap-2">
              <Label htmlFor="displayName">{t("account.name")}</Label>
              <Input
                disabled
                id="displayName"
                type="text"
                value={user.displayName}
              />
            </div>
          ) : null}
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">{t("email")}</Label>
            <Input disabled id="email" type="email" value={user?.email ?? ""} />
          </div>
        </section>

        <div className="mt-4">
          <Button
            onClick={handleLogout}
            className="w-full"
            disabled={isLoading}
          >
            <LogOutIcon className="size-4" />
            {t("logout")}
          </Button>
        </div>
      </Modal>
    </React.Fragment>
  );
};

export default UserDialog;

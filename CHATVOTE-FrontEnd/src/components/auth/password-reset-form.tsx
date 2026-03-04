"use client";

import { useState } from "react";

import { Button } from "@components/ui/button";
import { Input } from "@components/ui/input";
import { Label } from "@components/ui/label";
import { getAuth, sendPasswordResetEmail } from "firebase/auth";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

type Props = {
  onChangeView: () => void;
};

const PasswordResetForm = ({ onChangeView }: Props) => {
  const t = useTranslations("auth");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsLoading(true);
    const formData = new FormData(e.target as HTMLFormElement);
    const email = formData.get("email") as string;
    const auth = getAuth();
    await sendPasswordResetEmail(auth, email);
    setIsLoading(false);
    toast.success(t("resetPassword.emailSent"));

    onChangeView();
  };

  return (
    <form className="flex flex-col" onSubmit={handleSubmit}>
      <div className="mb-4">
        <h2 className="text-center text-2xl font-bold md:text-left">
          {t("resetPassword.title")}
        </h2>
        <p className="text-muted-foreground text-center text-sm md:text-left">
          {t("resetPassword.description")}
        </p>
      </div>

      <div className="flex flex-col gap-4">
        <div className="mt-4 grid gap-1">
          <Label htmlFor="email">{t("email")}</Label>
          <Input
            id="email"
            name="email"
            type="email"
            placeholder={t("emailPlaceholder")}
            required
          />
        </div>
        <Button type="submit" className="w-full" disabled={isLoading}>
          {t("resetPassword.sendLink")}
        </Button>
      </div>
      <div className="mt-4 text-center text-sm">
        {t("hasAccount")}{" "}
        <Button
          size="sm"
          type="button"
          variant="link"
          onClick={onChangeView}
          className="p-0 underline underline-offset-4"
        >
          {t("login")}
        </Button>
      </div>
    </form>
  );
};

export default PasswordResetForm;

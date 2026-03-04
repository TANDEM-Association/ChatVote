"use client";

import { useState } from "react";

import Link from "next/link";

import { useAnonymousAuth } from "@components/anonymous-auth";
import GoogleIcon from "@components/icons/google-icon";
import MicrosoftIcon from "@components/icons/microsoft-icon";
import { Button } from "@components/ui/button";
import { Input } from "@components/ui/input";
import { Label } from "@components/ui/label";
import { getUser } from "@lib/firebase/firebase";
import { FirebaseError } from "firebase/app";
import {
  EmailAuthProvider,
  getAuth,
  GoogleAuthProvider,
  linkWithCredential,
  linkWithPopup,
  OAuthProvider,
  signInWithCredential,
  signInWithEmailAndPassword,
} from "firebase/auth";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import PasswordResetForm from "./password-reset-form";
import SuccessAuthForm from "./success-auth-form";

type AuthProvider = "google" | "microsoft" | "email";

type Props = {
  onSuccess: () => void;
};

function LoginForm({ onSuccess }: Props) {
  const t = useTranslations("auth");
  const tNav = useTranslations("navigation");
  const { refreshUser } = useAnonymousAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [isResetPassword, setIsResetPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [allowNewsletter, setAllowNewsletter] = useState(false);

  const handleAuthSuccess = async () => {
    await refreshUser();
    const uid = getAuth().currentUser?.uid;

    if (uid) {
      const user = await getUser(uid);

      if (user?.newsletter_allowed === undefined) {
        setAllowNewsletter(true);
        return;
      }
    }

    onSuccess();
    showSuccessToast();
  };

  const handleAuthError = (error: unknown, provider: AuthProvider) => {
    if (error instanceof FirebaseError) {
      if (error.code === "auth/invalid-credential") {
        return toast.error(t("invalidCredentials"));
      }
      if (error.code === "auth/credential-already-in-use") {
        return handleCredentialAlreadyInUse(error, provider);
      }
      if (error.code === "auth/provider-already-linked") {
        return handleProviderAlreadyLinked();
      }
      if (error.code === "auth/operation-not-allowed") {
        return toast.error(t("methodNotAvailable"));
      }
      if (error.code === "auth/popup-closed-by-user") {
        return; // User closed popup, no need to show error
      }
    }

    console.error(error);
    showErrorReloadToast();
  };

  const handleCredentialAlreadyInUse = async (
    error: FirebaseError,
    provider: AuthProvider,
  ) => {
    const auth = getAuth();

    let credential = null;
    if (provider === "google") {
      credential = GoogleAuthProvider.credentialFromError(error);
    } else if (provider === "microsoft") {
      credential = OAuthProvider.credentialFromError(error);
    } else if (provider === "email") {
      return;
    }

    if (!credential) {
      showErrorReloadToast();
      return;
    }

    try {
      await signInWithCredential(auth, credential);
      await handleAuthSuccess();
    } catch (signInError) {
      handleAuthError(signInError, provider);
    }
  };

  const handleProviderAlreadyLinked = async () => {
    const auth = getAuth();
    if (!auth.currentUser?.isAnonymous && auth.currentUser?.email) {
      await handleAuthSuccess();
      return;
    }
    showErrorReloadToast();
  };

  const handleLogin = async (email: string, password: string) => {
    const auth = getAuth();
    try {
      await signInWithEmailAndPassword(auth, email, password);
      await handleAuthSuccess();
    } catch (error) {
      handleAuthError(error, "email");
    }
  };

  const handleRegister = async (email: string, password: string) => {
    const auth = getAuth();
    const user = auth.currentUser;

    if (!user) {
      showErrorReloadToast();
      return;
    }

    try {
      const credential = EmailAuthProvider.credential(email, password);
      await linkWithCredential(auth.currentUser, credential);
      await handleAuthSuccess();
    } catch (error) {
      handleAuthError(error, "email");
    }
  };

  const handleOAuthLogin = async (
    provider: GoogleAuthProvider | OAuthProvider,
  ) => {
    const auth = getAuth();

    if (!auth.currentUser) {
      showErrorReloadToast();
      return;
    }

    try {
      const result = await linkWithPopup(auth.currentUser, provider);
      const credential =
        provider instanceof GoogleAuthProvider
          ? GoogleAuthProvider.credentialFromResult(result)
          : OAuthProvider.credentialFromResult(result);

      if (!credential) {
        showErrorReloadToast();
        return;
      }

      await linkWithCredential(auth.currentUser, credential);
      await handleAuthSuccess();
    } catch (error) {
      handleAuthError(
        error,
        provider instanceof GoogleAuthProvider ? "google" : "microsoft",
      );
    }
  };

  const handleGoogleLogin = () => handleOAuthLogin(new GoogleAuthProvider());
  const handleMicrosoftLogin = () =>
    handleOAuthLogin(new OAuthProvider("microsoft.com"));

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.target as HTMLFormElement);
    const isRegister = formData.get("isRegister") === "true";
    const email = formData.get("email") as string;
    const password = formData.get("password") as string;

    setIsLoading(true);

    if (isRegister) {
      await handleRegister(email, password);
    } else {
      await handleLogin(email, password);
    }

    setIsLoading(false);
  };

  const showErrorReloadToast = () => {
    toast.error(t("errorReload"));
  };

  const showSuccessToast = () => {
    toast.success(t("loginSuccess"));
  };

  const handleResetPassword = async () => {
    setIsResetPassword(true);
  };

  const handleChangeView = () => {
    setIsResetPassword(!isResetPassword);
  };

  if (isResetPassword) {
    return <PasswordResetForm onChangeView={handleChangeView} />;
  }

  if (allowNewsletter) {
    return <SuccessAuthForm onSuccess={onSuccess} />;
  }

  return (
    <form className="flex flex-col" onSubmit={handleSubmit}>
      <input
        type="hidden"
        name="isRegister"
        value={isRegister ? "true" : "false"}
      />
      <div className="mb-4">
        <h2 className="text-center text-2xl font-bold md:text-left">
          {isRegister ? t("register") : t("login")}
        </h2>
        <p className="text-muted-foreground text-center text-sm md:text-left">
          {isRegister ? t("registerDescription") : t("loginDescription")}
        </p>
      </div>

      <div className="flex flex-col">
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
        <div className="my-4 grid gap-1">
          <div className="flex items-center">
            <Label htmlFor="password">{t("password")}</Label>
            <Button
              variant="link"
              className="ml-auto inline-block h-fit p-0 text-sm underline-offset-4 hover:underline"
              onClick={handleResetPassword}
              size="sm"
              type="button"
            >
              {t("forgotPassword")}
            </Button>
          </div>
          <Input
            id="password"
            type="password"
            name="password"
            required
            minLength={8}
            maxLength={30}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Button type="submit" className="w-full" disabled={isLoading}>
            {isRegister ? t("register") : t("login")}
          </Button>
          <p className="text-muted-foreground text-center text-xs">
            {t("privacyConsent", {
              action: isRegister ? t("register") : t("login"),
            })}{" "}
            <Link href="/privacy-policy" target="_blank" className="underline">
              {tNav("privacyPolicy")}
            </Link>
            .
          </p>

          <div className="after:border-border relative my-4 text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t">
            <span className="bg-background text-muted-foreground relative z-10 px-2">
              {t("orUseProviders")}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Button
              variant="outline"
              className="flex items-center gap-2"
              disabled={isLoading}
              onClick={handleGoogleLogin}
              type="button"
            >
              <div className="flex items-center gap-2">
                <GoogleIcon className="size-3!" />
                <span>Google</span>
              </div>
            </Button>
            <Button
              variant="outline"
              className="flex items-center gap-2"
              disabled={isLoading}
              type="button"
              onClick={handleMicrosoftLogin}
            >
              <div className="flex items-center gap-2">
                <MicrosoftIcon className="size-3!" />
                <span>Microsoft</span>
              </div>
            </Button>
          </div>
        </div>
      </div>
      <div className="mt-4 text-center text-sm">
        {isRegister ? t("hasAccount") : t("noAccount")}{" "}
        <Button
          size="sm"
          type="button"
          variant="link"
          onClick={() => setIsRegister(!isRegister)}
          className="p-0 underline underline-offset-4"
          disabled={isLoading}
        >
          {isRegister ? t("login") : t("register")}
        </Button>
      </div>
    </form>
  );
}

export default LoginForm;

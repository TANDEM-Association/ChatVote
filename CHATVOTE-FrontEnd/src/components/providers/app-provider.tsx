"use client";

import React from "react";

import { type Auth, AuthProvider } from "@components/anonymous-auth";
import AuthServiceWorkerProvider from "@components/providers/auth-service-worker-provider";
import { PartiesProvider } from "@components/providers/parties-provider";
import TenantProvider from "@components/providers/tenant-provider";
import { Toaster } from "@components/ui/sonner";
import { TooltipProvider } from "@components/ui/tooltip";
import { type Locale } from "@i18n/config";
import { type Device } from "@lib/device";
import { type Tenant } from "@lib/firebase/firebase.types";
import { type PartyDetails } from "@lib/party-details";
import { Analytics } from "@vercel/analytics/react";
import { domAnimation, LazyMotion } from "motion/react";

type AppProviderProps = {
  children: React.ReactNode;
  locale: Locale;
  auth: Auth;
  tenant: Tenant | undefined;
  device: Device;
  parties: PartyDetails[];
};

type AppContextValue = {
  device: Device;
  locale: Locale;
};

const AppContext = React.createContext<AppContextValue | null>(null);

export const AppProvider: React.FC<AppProviderProps> = ({
  children,
  locale,
  auth,
  tenant,
  device,
  parties,
}) => {
  return (
    <AppContext.Provider value={{ device, locale }}>
      <AuthServiceWorkerProvider />
      <TooltipProvider>
        <AuthProvider initialAuth={auth}>
          <TenantProvider tenant={tenant}>
            <LazyMotion features={domAnimation}>
              <PartiesProvider parties={parties}>{children}</PartiesProvider>
              <Toaster expand duration={1500} position="top-right" />
              {/* <LoginReminderToast /> */}
              {/* TODO: implement again when problems are fixed <IframeChecker /> */}
              <Analytics />
            </LazyMotion>
          </TenantProvider>
        </AuthProvider>
      </TooltipProvider>
    </AppContext.Provider>
  );
};

export function useAppContext() {
  const context = React.useContext(AppContext);

  if (context === null) {
    throw new Error("useApp must be used within an AppProvider");
  }

  return context;
}

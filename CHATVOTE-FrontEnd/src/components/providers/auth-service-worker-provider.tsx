"use client";

import { useEffect } from "react";

import { firebaseConfigAsUrlParams } from "@lib/firebase/firebase-config";

function AuthServiceWorkerProvider() {
  const registerServiceWorker = async () => {
    if ("serviceWorker" in navigator) {
      const emulatorParam =
        process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true"
          ? "&useEmulators=true"
          : "";
      await navigator.serviceWorker.register(
        `/service-worker.js?${firebaseConfigAsUrlParams}${emulatorParam}`,
        {
          scope: "/",
        },
      );
    }
  };

  useEffect(() => {
    registerServiceWorker();
  }, []);

  return null;
}

export default AuthServiceWorkerProvider;

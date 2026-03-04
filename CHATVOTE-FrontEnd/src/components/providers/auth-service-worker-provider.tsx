"use client";

import { useEffect } from "react";

import { firebaseConfigAsUrlParams } from "@lib/firebase/firebase-config";

function AuthServiceWorkerProvider() {
  const registerServiceWorker = async () => {
    if ("serviceWorker" in navigator) {
      await navigator.serviceWorker.register(
        `/service-worker.js?${firebaseConfigAsUrlParams}`,
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

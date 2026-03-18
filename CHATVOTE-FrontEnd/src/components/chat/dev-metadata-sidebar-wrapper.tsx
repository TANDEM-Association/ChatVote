"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";

const DevMetadataSidebar = dynamic(() => import("./dev-metadata-sidebar"), {
  ssr: false,
});

export default function DevMetadataSidebarWrapper() {
  const searchParams = useSearchParams();
  const isDebug =
    process.env.NODE_ENV === "development" ||
    searchParams.get("debug") === "1";

  if (!isDebug) return null;

  return <DevMetadataSidebar />;
}

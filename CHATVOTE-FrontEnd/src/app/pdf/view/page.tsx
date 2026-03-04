"use client";

import { type NextPage } from "next";
import dynamic from "next/dynamic";

const PDFView = dynamic(() => import("@components/pdf-view"), {
  ssr: false,
});

const PDFViewPage: NextPage = () => {
  return <PDFView />;
};

export default PDFViewPage;

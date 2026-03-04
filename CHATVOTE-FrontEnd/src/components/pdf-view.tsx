"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";

import { useSearchParams } from "next/navigation";

import LoadingSpinner from "@components/loading-spinner";
import { Button } from "@components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@components/ui/tooltip";
import { MinusIcon, PlusIcon, ShieldAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { Document, Page, pdfjs } from "react-pdf";
import { type DocumentCallback } from "react-pdf/dist/esm/shared/types.js";
import AutoSizer from "react-virtualized-auto-sizer";
import { FixedSizeList as List } from "react-window";

import "react-pdf/dist/esm/Page/AnnotationLayer.css";
import "react-pdf/dist/esm/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

function getProxiedPdfUrl(url: string | null): string | null {
  if (url === null) {
    return null;
  }

  if (
    url.includes("firebasestorage.app") ||
    url.includes("storage.googleapis.com")
  ) {
    return `/api/pdf-proxy?url=${encodeURIComponent(url)}`;
  }

  return url;
}

function PDFView() {
  const t = useTranslations("pdf");
  const tCommon = useTranslations("common");
  const searchParams = useSearchParams();
  const rawPdfPath = searchParams.get("pdf");
  const pdfPath = getProxiedPdfUrl(rawPdfPath);
  const page = searchParams.get("page");

  const [numPages, setNumPages] = useState<number>(0);
  const [zoom, setZoom] = useState<number>(1);

  const listRef = useRef<List>(null);
  const outerRef = useRef<HTMLDivElement>(null);
  const scrollRatioRef = useRef<number | null>(null);

  const options = useMemo(
    () => ({
      cMapUrl: "/cmaps/",
      standardFontDataUrl: "/standard_fonts/",
    }),
    [],
  );

  const scrollToPage = (pageNumber: number) => {
    if (listRef.current && pageNumber > 0) {
      listRef.current.scrollToItem(pageNumber - 1, "start");
    }
  };

  const onDocumentLoadSuccess = (pdf: DocumentCallback): void => {
    const { numPages } = pdf;
    setNumPages(numPages);

    if (page) {
      const pageNumber = Number.parseInt(page, 10) || 1;
      setTimeout(() => {
        if (listRef.current) {
          scrollToPage(pageNumber);
        }
      }, 100);
    }
  };

  const handleItemClick = ({ pageNumber }: { pageNumber: number }) => {
    scrollToPage(pageNumber);
  };

  const calculatePageHeight = (
    containerHeight: number,
    containerWidth: number,
  ) => {
    const dinA4Ratio = 1 / Math.sqrt(2);
    const isMobile = containerWidth < 768;

    if (isMobile) {
      const adjustedWidth = containerWidth - 20;
      return adjustedWidth / dinA4Ratio;
    } else {
      return containerHeight;
    }
  };

  const handleZoomIn = () => {
    captureScrollRatio();
    setZoom((z) => z + 0.1);
  };

  const handleZoomOut = () => {
    captureScrollRatio();
    setZoom((z) => Math.max(z - 0.1, 0.1));
  };

  const captureScrollRatio = () => {
    if (!outerRef.current || !numPages) return;
    const scrollElement = outerRef.current;
    const currentScrollTop = scrollElement.scrollTop;

    const containerHeight = outerRef.current.clientHeight;
    const containerWidth = outerRef.current.clientWidth;
    const basePageHeight = calculatePageHeight(containerHeight, containerWidth);
    const oldPageHeight = basePageHeight * zoom;
    const oldTotalHeight = numPages * oldPageHeight;

    const ratio = currentScrollTop / oldTotalHeight;
    scrollRatioRef.current = ratio;
  };

  useLayoutEffect(() => {
    if (scrollRatioRef.current !== null && outerRef.current && numPages) {
      const scrollElement = outerRef.current;
      const containerHeight = scrollElement.clientHeight;
      const containerWidth = scrollElement.clientWidth;
      const basePageHeight = calculatePageHeight(
        containerHeight,
        containerWidth,
      );
      const newPageHeight = basePageHeight * zoom;
      const newTotalHeight = numPages * newPageHeight;

      const newScrollTop = scrollRatioRef.current * newTotalHeight;
      scrollElement.scrollTop = newScrollTop;

      scrollRatioRef.current = null;
    }
  }, [zoom, numPages]);

  return (
    <main className="relative flex h-svh w-full flex-col items-center">
      <div className="bg-muted size-full grow overflow-auto">
        <AutoSizer>
          {({ height, width }) => {
            const basePageHeight = calculatePageHeight(height, width);
            const pageHeight = basePageHeight * zoom;

            return (
              <Document
                file={pdfPath}
                onLoadSuccess={onDocumentLoadSuccess}
                onItemClick={handleItemClick}
                options={options}
                loading={
                  <div className="flex h-svh w-screen flex-col items-center justify-center">
                    <LoadingSpinner />
                    <span className="mt-4">{t("loading")}</span>
                  </div>
                }
                error={
                  <div className="flex h-svh w-screen flex-col items-center justify-center">
                    <ShieldAlert className="size-12 text-red-500" />
                    <span className="mt-4 font-semibold text-red-500">
                      {t("error")}
                    </span>
                  </div>
                }
              >
                {numPages > 0 && (
                  <List
                    height={height}
                    itemCount={numPages}
                    itemSize={pageHeight}
                    width={width}
                    ref={listRef}
                    outerRef={outerRef}
                  >
                    {({ index, style }) => (
                      <div
                        style={{
                          ...style,
                        }}
                        className="flex items-center justify-center py-10"
                        id={`page_${index + 1}`}
                      >
                        <Page
                          pageNumber={index + 1}
                          height={pageHeight}
                          loading={<LoadingSpinner />}
                        />
                      </div>
                    )}
                  </List>
                )}
              </Document>
            );
          }}
        </AutoSizer>
      </div>
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-center p-4">
        <div className="bg-background flex items-center gap-2 space-x-4 rounded-full border p-4 shadow-md transition-shadow duration-200 hover:shadow-lg">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={handleZoomOut}
              >
                <MinusIcon className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>-10%</TooltipContent>
          </Tooltip>

          <div className="flex flex-col items-center text-center">
            <span className="text-sm font-semibold">
              {Math.round(zoom * 100)}%
            </span>
            <span className="text-muted-foreground text-xs">
              {tCommon("zoom")}
            </span>
          </div>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={handleZoomIn}
              >
                <PlusIcon className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>+10%</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </main>
  );
}

export default PDFView;

"use client";

import { useAppContext } from "@components/providers/app-provider";
import { Button } from "@components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@components/ui/dropdown-menu";
import { useTheme } from "@lib/hooks/useTheme";
import { Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";

type Props = {
  align?: "start" | "end" | "center";
};

export function ThemeModeToggle({ align }: Props) {
  const t = useTranslations("theme");
  const tCommon = useTranslations("common");
  const { setTheme } = useTheme();
  const { device } = useAppContext();
  const isDesktop = device === "desktop" || device === "tablet";

  const normalizedAlign = align ?? (isDesktop ? "start" : "center");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-8">
          <Sun className="size-[1.2rem] scale-100 rotate-0 transition-all dark:scale-0 dark:-rotate-90" />
          <Moon className="absolute size-[1.2rem] scale-0 rotate-90 transition-all dark:scale-100 dark:rotate-0" />
          <span className="sr-only">{tCommon("toggleTheme")}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={normalizedAlign}>
        <DropdownMenuItem onClick={() => setTheme("light")}>
          {t("light")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          {t("dark")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          {t("system")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

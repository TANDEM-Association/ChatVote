"use client";

import { useState } from "react";

import { Button } from "@components/ui/button";
import { cn } from "@lib/utils";
import { ListIcon } from "lucide-react";

import { useChatStore } from "../providers/chat-store-provider";
import ElectoralListsDrawer from "./sidebar/sidebar-electoral-lists-mobile";

export default function MobileElectoralListsBar() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const municipalityCode = useChatStore((s) => s.municipalityCode);
  const selectedElectoralLists = useChatStore((s) => s.selectedElectoralLists);

  if (!municipalityCode) return null;

  const count = selectedElectoralLists.length;

  return (
    <>
      <div className="flex items-center justify-center pb-2 md:hidden">
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "h-8 gap-1.5 rounded-full border-dashed text-xs",
            count > 0 && "border-primary/40 bg-primary/5",
          )}
          onClick={() => setDrawerOpen(true)}
        >
          <ListIcon className="size-3.5" />
          <span>
            {count > 0 ? `${count} liste${count > 1 ? "s" : ""} sélectionnée${count > 1 ? "s" : ""}` : "Sélectionner des listes"}
          </span>
        </Button>
      </div>

      <ElectoralListsDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
      />
    </>
  );
}

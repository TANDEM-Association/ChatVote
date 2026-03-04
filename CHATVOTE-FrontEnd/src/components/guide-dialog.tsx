"use client";

import React, { useState } from "react";

import { Modal } from "./ui/modal";
import Guide from "./guide";

type Props = {
  children: React.ReactNode;
};

const GuideDialog = ({ children }: Props) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <React.Fragment>
      <div onClick={() => setIsOpen(true)}>{children}</div>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="flex max-h-[85dvh] w-full max-w-2xl flex-col overflow-hidden p-6"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold">
            Que puis-je faire avec <span className="underline">chatvote</span> ?
          </h2>
          <p className="text-muted-foreground text-sm">
            Trucs et astuces pour utiliser au mieux chatvote.
          </p>
        </div>

        <div className="grow overflow-y-auto">
          <Guide />
        </div>
      </Modal>
    </React.Fragment>
  );
};

export default GuideDialog;

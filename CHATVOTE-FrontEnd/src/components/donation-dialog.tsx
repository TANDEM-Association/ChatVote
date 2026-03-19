"use client";

import React, { useState } from "react";

import { trackDonationDialogOpened } from "@lib/firebase/analytics";

import { Modal } from "./ui/modal";
import DonationForm from "./donation-form";

type Props = {
  children: React.ReactNode;
};

const DonationDialog = ({ children }: Props) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <React.Fragment>
      <div onClick={() => { setIsOpen(true); trackDonationDialogOpened(); }}>{children}</div>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="w-full max-w-lg p-6"
      >
        <DonationForm />
      </Modal>
    </React.Fragment>
  );
};

export default DonationDialog;

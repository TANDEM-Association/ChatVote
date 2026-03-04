"use client";

import React, { useState } from "react";

import { type User } from "@components/anonymous-auth";
import { Modal } from "@components/ui/modal";

import LoginForm from "./login-form";
import UserDialog from "./user-dialog";

type LoginButtonProps = {
  noUserChildren?: React.ReactNode;
  userChildren?: React.ReactNode;
  isAuthenticated: boolean;
  user?: User | null;
};

const LoginButton = ({
  noUserChildren,
  userChildren,
  isAuthenticated,
  user,
}: LoginButtonProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleSuccess = () => {
    setIsOpen(false);
  };

  if (isAuthenticated && !isOpen) {
    if (!userChildren) {
      return null;
    }

    return <UserDialog user={user ?? null}>{userChildren}</UserDialog>;
  }

  return (
    <React.Fragment>
      <div
        onClick={() => {
          setIsOpen(true);
        }}
      >
        {noUserChildren}
      </div>

      <Modal
        isOpen={isOpen}
        onClose={() => {
          setIsOpen(false);
        }}
        className="w-full max-w-md p-6"
      >
        <LoginForm onSuccess={handleSuccess} />
      </Modal>
    </React.Fragment>
  );
};

export default LoginButton;

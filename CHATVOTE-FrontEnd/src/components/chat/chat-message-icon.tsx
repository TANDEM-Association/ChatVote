"use client";

import Image from "next/image";

export const ChatMessageIcon = () => {
  return (
    <div className="ring-border relative flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full">
      <Image
        src="/images/logos/chatvote.svg"
        alt="chatvote"
        sizes="100vw"
        width={0}
        height={0}
        className="size-full object-contain"
      />
    </div>
  );
};

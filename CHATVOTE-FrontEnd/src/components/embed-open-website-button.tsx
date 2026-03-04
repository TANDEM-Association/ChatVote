import Image from "next/image";
import Link from "next/link";

import { getAppUrl } from "@lib/url";

import MessageLoadingBorderTrail from "./chat/message-loading-border-trail";
import { Button } from "./ui/button";

const EmbedOpenWebsiteButton = async () => {
  const appUrl = await getAppUrl();

  return (
    <Button variant="outline" size="sm" asChild className="relative">
      <Link target="_blank" href={appUrl}>
        <MessageLoadingBorderTrail />
        <Image
          src="/images/logos/chatvote.svg"
          alt="chatvote"
          width={0}
          height={0}
          sizes="100vw"
          className="size-4"
        />
        Vers chatvote
      </Link>
    </Button>
  );
};

export default EmbedOpenWebsiteButton;

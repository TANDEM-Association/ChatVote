import { headers } from "next/headers";

import { detectDevice } from "@lib/device";
import { getAuth } from "@lib/firebase/firebase-server";

import { HeaderDesktop } from "./header-desktop";
import { HeaderMobile } from "./header-mobile";

export const Header: React.FC = async () => {
  const requestHeaders = await headers();
  const device = detectDevice(requestHeaders);
  const auth = await getAuth();

  const user = auth.user;
  const isAuthenticated =
    auth.session !== null && auth.session.isAnonymous === false;

  return device === "mobile" ? (
    <HeaderMobile user={user} isAuthenticated={isAuthenticated} />
  ) : (
    <HeaderDesktop user={user} isAuthenticated={isAuthenticated} />
  );
};

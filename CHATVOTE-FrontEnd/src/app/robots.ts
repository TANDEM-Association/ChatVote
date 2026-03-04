import { type MetadataRoute } from "next";

import { getAppUrl } from "@lib/url";

export default async function robots(): Promise<MetadataRoute.Robots> {
  const appUrl = await getAppUrl();

  return {
    rules: {
      userAgent: "*",
      allow: "/",
    },
    sitemap: `${appUrl}/sitemap.xml`,
  };
}

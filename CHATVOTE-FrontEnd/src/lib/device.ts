export type Device = "mobile" | "tablet" | "desktop";

export function detectDevice(headers: Headers): Device {
  const chMobile = headers.get("sec-ch-ua-mobile");
  if (chMobile !== null) {
    return chMobile.includes("?1") ? "mobile" : "desktop";
  }

  const userAgent = (headers.get("user-agent") ?? "").toLowerCase();

  const isTablet =
    /\b(ipad|tablet|xoom|sch-i800|playbook|silk|kindle|tab(?!let)|nexus 7|nexus 10|sm-t|gt-p)\b/.test(
      userAgent,
    );

  const isMobile =
    isTablet === false &&
    /\b(iphone|ipod|android.*mobile|blackberry|bb10|mini|windows phone)\b/.test(
      userAgent,
    );

  if (isTablet === true) {
    return "tablet";
  }

  if (isMobile === true) {
    return "mobile";
  }

  return "desktop";
}

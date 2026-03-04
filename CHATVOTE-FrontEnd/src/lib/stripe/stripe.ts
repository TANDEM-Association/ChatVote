import { getAppUrlSync } from "@lib/url";
import Stripe from "stripe";

import "server-only";

let _stripe: Stripe | null = null;

export function getStripe(): Stripe {
  if (_stripe) return _stripe;

  const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
  if (!stripeSecretKey) {
    throw new Error("STRIPE_SECRET_KEY is not set");
  }

  _stripe = new Stripe(stripeSecretKey, {
    appInfo: {
      name: "chatvote",
      url: getAppUrlSync(),
    },
  });

  return _stripe;
}

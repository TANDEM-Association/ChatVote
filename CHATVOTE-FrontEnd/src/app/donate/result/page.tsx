import { type NextPage } from "next";

import DonateResultContent from "@components/donate-result-content";
import { getStripe } from "@lib/stripe/stripe";

async function validateStripeSession(sessionId: string): Promise<boolean> {
  try {
    const checkoutSession = await getStripe().checkout.sessions.retrieve(sessionId, {
      expand: ["payment_intent"],
    });

    // Vérifier le statut de la session (expired, open, complete)
    if (checkoutSession.status !== "complete") {
      return false;
    }

    // Vérifier que payment_intent existe et est un objet (pas une string)
    const paymentIntent = checkoutSession.payment_intent;

    if (paymentIntent === null || typeof paymentIntent === "string") {
      return false;
    }

    if (paymentIntent.status !== "succeeded") {
      return false;
    }

    return true;
  } catch (error) {
    // Session invalide, n'existe pas, ou erreur Stripe
    console.error("Stripe session retrieval error:", error);
    return false;
  }
}

type DonateResultPageProps = {
  searchParams: Promise<{ session_id: string }>;
};

const DonateResultPage: NextPage<DonateResultPageProps> = async ({
  searchParams,
}: {
  searchParams: Promise<{ session_id: string }>;
}) => {
  const actualSearchParams = await searchParams;

  if (!actualSearchParams.session_id) {
    return <DonateResultContent isSuccess={false} />;
  }

  const isValidPayment = await validateStripeSession(
    actualSearchParams.session_id,
  );

  return <DonateResultContent isSuccess={isValidPayment} />;
};

export default DonateResultPage;

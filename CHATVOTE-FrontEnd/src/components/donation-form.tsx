"use client";

import { useState } from "react";

import { createCheckoutSession } from "@lib/server-actions/stripe-create-session";
import { formatAmountForDisplay } from "@lib/stripe/stripe-helpers";
import { cn } from "@lib/utils";
import NumberFlow from "@number-flow/react";
import { track } from "@vercel/analytics/react";
import { EqualIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "./ui/button";
import {
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Input } from "./ui/input";
import { Slider } from "./ui/slider";
import { DonateSubmitButton } from "./donate-submit-button";

const defaultAmounts = [5, 10, 20, 50, 100, 200, 500];

const DonationForm = () => {
  const t = useTranslations("donation");
  const tCommon = useTranslations("common");
  const [amount, setAmount] = useState(50);
  const [customAmount, setCustomAmount] = useState(false);

  const handleDonate = async (data: FormData) => {
    track("donation_started", {
      amount: amount,
    });

    const result = await createCheckoutSession(data);

    if (result.url) {
      window.location.assign(result.url);
    }
  };

  const handleSetAmount = (amount: number) => {
    setAmount(amount);
    setCustomAmount(false);
  };

  const handleSliderChange = (value: number[]) => {
    setAmount(value[0]);
    if (customAmount) setCustomAmount(false);
  };

  return (
    <form action={handleDonate}>
      <CardHeader className="space-y-3">
        <CardTitle className="text-center text-xl">
          <span>{t("title")}</span>
        </CardTitle>
        <CardDescription className="text-center">
          <p>{t("description")}</p>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-[1fr,auto,1fr] items-center gap-2">
          <div className="flex flex-col items-center justify-center">
            {customAmount ? (
              <Input
                type="number"
                name="amount"
                min="5"
                max="10000"
                step="1"
                className="mb-2 h-16 w-32 [appearance:textfield] text-center text-4xl font-bold [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                value={amount}
                onChange={(e) => {
                  const value = Math.max(0, Math.floor(Number(e.target.value)))
                    .toString()
                    .replace(/^0+/, "");
                  setAmount(Number(value));
                }}
              />
            ) : (
              <h1 className="text-center text-4xl font-bold">
                <NumberFlow value={amount} />{" "}
                <span className="text-muted-foreground text-lg">€</span>
              </h1>
            )}
            <p className="text-muted-foreground text-center text-sm">
              {t("oneTimeDonation")}
            </p>
          </div>
          <EqualIcon className="mx-auto size-10" />
          <div className="mb-8 flex flex-col items-center justify-center">
            <h1 className="text-center text-4xl font-bold">
              <NumberFlow value={amount * 50} />
            </h1>
            <p className="text-muted-foreground text-center text-sm">
              {t("peopleInformed")}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-2">
          {defaultAmounts.map((currAmount) => (
            <Button
              key={currAmount}
              variant="outline"
              type="button"
              className={cn(
                amount === currAmount &&
                  "bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground/90",
              )}
              onClick={() => handleSetAmount(currAmount)}
            >
              {formatAmountForDisplay(currAmount)} €
            </Button>
          ))}
          <Button
            type="button"
            variant="outline"
            className={cn(
              customAmount &&
                "bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground/90",
            )}
            onClick={() => setCustomAmount(true)}
          >
            {tCommon("other")}
          </Button>
        </div>

        <Slider
          className="my-8"
          defaultValue={[50]}
          min={5}
          max={5000}
          step={5}
          value={[amount]}
          onValueChange={handleSliderChange}
        />

        <input type="hidden" name="amount" value={amount} />
      </CardContent>
      <CardFooter className="flex items-center justify-center">
        <DonateSubmitButton isDisabled={amount < 5} />
      </CardFooter>
    </form>
  );
};

export default DonationForm;

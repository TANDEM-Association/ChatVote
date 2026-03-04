import { type NextPage } from "next";

import HowTo from "@components/guide";
import { GuideTitle } from "@components/guide/guide-title";
import { PageLayout } from "@components/layout/page-layout";

const GuidePage: NextPage = () => {
  return (
    <PageLayout>
      <GuideTitle />
      <HowTo />
    </PageLayout>
  );
};

export default GuidePage;

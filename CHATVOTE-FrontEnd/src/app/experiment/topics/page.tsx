import TopicInsights from "@components/experiment/topic-insights";

export const metadata = {
  title: "ChatVote - Topic Insights",
};

export default function TopicInsightsPage() {
  return (
    <main className="bg-background text-foreground h-screen overflow-y-auto">
      <TopicInsights />
    </main>
  );
}

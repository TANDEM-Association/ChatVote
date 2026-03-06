import ExperimentPlayground from "@components/experiment/experiment-playground";

export const metadata = {
  title: "ChatVote - Chunk Metadata Explorer",
};

export default function ExperimentPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <ExperimentPlayground />
    </main>
  );
}

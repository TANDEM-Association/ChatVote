type Props = {
  children: React.ReactNode;
  onClick?: () => void;
};

function InitialSuggestionBubble({ children, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="border-input text-muted-foreground ring-offset-background hover:bg-muted focus-visible:ring-ring cursor-pointer rounded-full border px-3 py-2 text-xs transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      {children}
    </button>
  );
}

export default InitialSuggestionBubble;

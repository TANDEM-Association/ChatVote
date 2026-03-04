import { cn } from "@lib/utils";

type Props = {
  children: React.ReactNode;
  className?: string;
};

const ChatMainContent = ({ children, className }: Props) => {
  return (
    <main
      className={cn(
        "flex min-h-0 w-full flex-1 flex-col overflow-hidden",
        className,
      )}
    >
      {children}
    </main>
  );
};

export default ChatMainContent;

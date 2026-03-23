import AnonymousUserChatStoreUpdater from "@components/auth/anonymous-user-chat-store-updater";
import { ChatStoreProvider } from "@components/providers/chat-store-provider";
import { SidebarProvider } from "@components/ui/sidebar";

type Props = {
  children: React.ReactNode;
};

async function Layout({ children }: Props) {
  return (
    <ChatStoreProvider>
      <AnonymousUserChatStoreUpdater />
      <SidebarProvider defaultOpen={false}>{children}</SidebarProvider>
    </ChatStoreProvider>
  );
}

export default Layout;

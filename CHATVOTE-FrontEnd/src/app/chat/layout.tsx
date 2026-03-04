import AnonymousUserChatStoreUpdater from "@components/auth/anonymous-user-chat-store-updater";
import { ChatStoreProvider } from "@components/providers/chat-store-provider";
import SocketProvider from "@components/providers/socket-provider";
import { SidebarProvider } from "@components/ui/sidebar";

type Props = {
  children: React.ReactNode;
};

async function Layout({ children }: Props) {
  return (
    <ChatStoreProvider>
      <AnonymousUserChatStoreUpdater />
      <SocketProvider>
        <SidebarProvider defaultOpen={false}>{children}</SidebarProvider>
      </SocketProvider>
    </ChatStoreProvider>
  );
}

export default Layout;

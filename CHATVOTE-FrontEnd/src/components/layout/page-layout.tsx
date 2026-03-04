import { Footer } from "./footer";
import { Header } from "./header";

type PageLayoutProps = {
  children: React.ReactNode;
};

export const PageLayout: React.FC<PageLayoutProps> = ({ children }) => {
  return (
    <div className="size-screen flex w-full flex-col items-stretch overflow-hidden">
      <Header />
      <div className="flex flex-1 justify-center overflow-hidden px-4 py-8">
        <main className="w-full max-w-xl">{children}</main>
      </div>
      <Footer />
    </div>
  );
};

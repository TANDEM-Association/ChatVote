"use client";

import React from "react";
import ReactDOM from "react-dom";

import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";

import { LanguageSwitcher } from "@components/i18n/LanguageSwitcher";
import { config } from "@config";
import { useLockScroll } from "@lib/hooks/use-lock-scroll";
import { type User } from "@lib/types/auth";
import {
  motion,
  type SVGMotionProps,
  type Transition,
  useCycle,
  type Variants,
} from "motion/react";
import { useTranslations } from "next-intl";

import { type NavbarItemDetails } from "./navbar-item";

const underlineTransition: Transition = {
  duration: 0.1,
  type: "spring",
  stiffness: 250,
  damping: 30,
};

const menuVariants: Variants = {
  open: {
    y: "0%",
    top: 0,
    transition: {
      duration: 0.8,
      ease: [0.74, 0, 0.19, 1.02],
    },
  },
  closed: {
    y: "-100%",
    top: 0,
    transition: {
      delay: 0.35,
      duration: 0.63,
      ease: [0.74, 0, 0.19, 1.02],
    },
  },
};

const listLinkVariants: Variants = {
  open: {
    transition: {
      delayChildren: 0.8,
      staggerChildren: 0.15,
    },
  },
  closed: {
    transition: {
      staggerChildren: 0.04,
      staggerDirection: -1,
    },
  },
};

const linkVariants: Variants = {
  open: {
    opacity: 1,
    x: 0,
    transition: {
      duration: 0.1,
      type: "spring",
      velocity: -100,
      stiffness: 300,
      damping: 30,
    },
  },
  closed: {
    opacity: 0,
    x: -5,
    transition: {
      duration: 0.01,
      velocity: -100,
      type: "spring",
      stiffness: 500,
      damping: 30,
    },
  },
};

const websiteUrl = config.websiteUrl;
const aboutPage = `${websiteUrl}/about`;

type HeaderMobileProps = {
  user: User | null;
  isAuthenticated: boolean;
};

export const HeaderMobile: React.FC<HeaderMobileProps> = ({
  user,
  isAuthenticated,
}) => {
  const t = useTranslations("navigation");
  const router = useRouter();
  const pathname = usePathname();
  const [isMenuOpen, toggleMenu] = useCycle(false, true);
  const [pendingPath, setPendingPath] = React.useState<string | null>(null);
  const [isMounted, setIsMounted] = React.useState(false);

  useLockScroll({ isLocked: isMenuOpen });

  const ROUTES: NavbarItemDetails[] = [
    {
      label: t("home"),
      href: "/",
    },
    {
      label: t("guide"),
      href: "/guide",
    },
    {
      label: t("supportUs"),
      href: "/donate",
    },
    {
      label: t("about"),
      href: aboutPage,
    },
  ];

  React.useEffect(() => {
    setIsMounted(true);
  }, []);

  const onToggle = () => {
    toggleMenu();
  };

  const isActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const redirectToRoute =
    (path: string) => (event: React.MouseEvent<HTMLAnchorElement>) => {
      event.preventDefault();

      setPendingPath(path);

      toggleMenu();

      router.push(path);
    };

  const menuPortal =
    isMounted === true
      ? ReactDOM.createPortal(
          <motion.div
            variants={menuVariants}
            animate={isMenuOpen === true ? "open" : "closed"}
            initial="closed"
            className="fixed inset-0 z-40 flex h-dvh w-screen flex-col items-start justify-between gap-6 overflow-hidden bg-purple-900"
            onAnimationComplete={(animationDefinition) => {
              if (animationDefinition === "closed" && pendingPath !== null) {
                setPendingPath(null);
              }
            }}
          >
            <motion.ul
              variants={listLinkVariants}
              animate={isMenuOpen === true ? "open" : "closed"}
              className="flex size-full flex-col items-center justify-center gap-3"
            >
              {ROUTES.map((route) => {
                const active = isActive(route.href);
                return (
                  <motion.li
                    key={route.label}
                    variants={linkVariants}
                    className="text-foreground relative text-base font-semibold"
                  >
                    <a onClick={redirectToRoute(route.href)}>{route.label}</a>
                    {active === true ? (
                      <motion.div
                        layoutId="nav-underline"
                        className="absolute -bottom-px left-0 h-px w-full rounded bg-current"
                        transition={underlineTransition}
                        style={{ originY: "0px" }}
                      />
                    ) : null}
                  </motion.li>
                );
              })}
            </motion.ul>
          </motion.div>,
          document.body,
        )
      : null;

  return (
    <React.Fragment>
      <header className="bg-background sticky inset-x-0 top-0 z-50 h-12.5 w-screen">
        <motion.nav
          className="relative mx-auto flex h-full w-85 items-center justify-start py-2"
          initial="closed"
          animate={isMenuOpen === true ? "open" : "closed"}
        >
          <div className="relative z-50 flex w-full flex-row items-center justify-between text-neutral-100">
            <HeaderMobileMenuToggle toggle={onToggle} />
            <a
              onClick={redirectToRoute("/")}
              className="flex cursor-pointer justify-center"
            >
              <Image
                src="/images/logos/chatvote.svg"
                alt="chatvote"
                width={0}
                height={0}
                sizes="100vw"
                className="w-8"
                loading="eager"
              />
            </a>
            <div className="flex items-center justify-end">
              <LanguageSwitcher />
            </div>
          </div>
        </motion.nav>
      </header>
      {menuPortal}
    </React.Fragment>
  );
};

type HeaderMobileMenuToggleProps = {
  toggle: () => void;
};

export const HeaderMobileMenuToggle: React.FC<HeaderMobileMenuToggleProps> = ({
  toggle,
}) => {
  return (
    <button onClick={toggle} className="flex items-center justify-center">
      <svg width="28" height="28" viewBox="0 -2 23 23">
        <Path
          variants={{
            closed: { d: "M 2 2.5 L 20 2.5" },
            open: { d: "M 3 16.5 L 17 2.5" },
          }}
        />
        <Path
          d="M 2 9.423 L 20 9.423"
          variants={{
            closed: { opacity: 1 },
            open: { opacity: 0 },
          }}
          transition={{
            duration: 0.1,
          }}
        />
        <Path
          variants={{
            closed: { d: "M 2 16.346 L 20 16.346" },
            open: { d: "M 3 2.5 L 17 16.346" },
          }}
        />
      </svg>
    </button>
  );
};

const Path: React.FC<SVGMotionProps<SVGPathElement>> = (props) => {
  return (
    <motion.path
      fill="transparent"
      strokeWidth="1.5"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    />
  );
};

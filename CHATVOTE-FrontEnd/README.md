<!--
SPDX-FileCopyrightText: 2025 chatvote

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
-->

# Chatvote

> AI-powered political information chatbot for French elections

Chatvote is an interactive platform that enables citizens to engage with political party programs and positions through AI-powered conversations. Users can ask questions, compare party stances, and receive source-backed answers in a modern, accessible interface.

## Links

- **Application**: [chatvote.org](https://chatvote.org/)
- **About**: [chatvote.org/about](https://chatvote.org/about)
- **Press**: [chatvote.notion.site](https://chatvote.notion.site)

## Features

### AI Chat System

- **Real-time streaming responses** via WebSocket (Socket.io)
- **Multi-party conversations** — Chat with up to 7 parties simultaneously
- **Source-backed answers** — Every response includes references to official party documents
- **Quick replies** — AI-generated follow-up questions for deeper exploration

### Political Analysis Tools

- **Pro/Con Position Evaluation** — AI-powered analysis of party positions with feasibility assessment, short-term and long-term effects (powered by Perplexity.ai)
- **Voting Behavior Analysis** — Parliamentary voting records with detailed breakdown by party
- **Interactive Vote Charts** — Visualize voting patterns with Recharts

### Election Support

- **National & Local Scope** — Support for both national parties and municipal candidates
- **Municipality Search** — Find local candidates by city name or postal code
- **Candidate Profiles** — View candidate information and party affiliations

### User Experience

- **Authentication** — Firebase Auth with Email, Google, and Microsoft providers
- **Chat History** — Persistent sessions synced across devices
- **Session Sharing** — Generate shareable links for chat conversations
- **Internationalization** — Full support for French and English
- **Dark/Light Themes** — System preference detection with manual toggle
- **Responsive Design** — Optimized for desktop, tablet, and mobile
- **PWA Support** — Installable as a progressive web app

### Additional Features

- **PDF Source Viewer** — In-app viewing of party program documents
- **Donation System** — Stripe integration for supporting the project
- **Feedback System** — Message-level like/dislike with detailed feedback
- **Topics Explorer** — Browse questions by political theme
- **Multi-tenant Support** — Custom configurations for embedded deployments

## Tech Stack

### Core

- **[Next.js 16](https://nextjs.org/)** — React framework with App Router and Turbopack
- **[React 19](https://react.dev/)** — UI library
- **[TypeScript](https://www.typescriptlang.org/)** — Type safety

### State Management

- **[Zustand](https://zustand-demo.pmnd.rs/)** — Lightweight state management
- **[Immer](https://immerjs.github.io/immer/)** — Immutable state updates

### Styling

- **[Tailwind CSS v4](https://tailwindcss.com/)** — Utility-first CSS
- **[Radix UI](https://www.radix-ui.com/)** — Accessible component primitives
- **[class-variance-authority](https://cva.style/)** — Component variants
- **[tailwind-merge](https://github.com/dcastil/tailwind-merge)** — Utility class merging

### Backend Services

- **[Firebase](https://firebase.google.com/)** — Authentication & Firestore database
- **[Socket.io](https://socket.io/)** — Real-time WebSocket communication
- **[Stripe](https://stripe.com/)** — Payment processing

### UI/UX

- **[Motion](https://motion.dev/)** — Animations (Framer Motion)
- **[Embla Carousel](https://www.embla-carousel.com/)** — Touch-friendly carousels
- **[Recharts](https://recharts.org/)** — Data visualization
- **[Lucide React](https://lucide.dev/)** — Icon library
- **[Sonner](https://sonner.emilkowal.ski/)** — Toast notifications
- **[Vaul](https://vaul.emilkowal.ski/)** — Drawer component

### Internationalization

- **[next-intl](https://next-intl-docs.vercel.app/)** — i18n for Next.js App Router

### Content

- **[react-markdown](https://github.com/remarkjs/react-markdown)** — Markdown rendering
- **[react-pdf](https://react-pdf.org/)** — PDF document viewing

### Analytics

- **[Vercel Analytics](https://vercel.com/analytics)** — Web analytics
- **[Google Analytics](https://analytics.google.com/)** — Traffic analytics

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── (home)/            # Home page
│   ├── api/               # API routes (embed, og, parties, pdf-proxy, etc.)
│   ├── chat/              # Chat interface with [chatId] dynamic route
│   ├── donate/            # Donation flow
│   ├── guide/             # User guide
│   ├── share/             # Shared chat sessions
│   ├── sources/           # Sources documentation
│   ├── topics/            # Topics explorer
│   └── _actions/          # Server actions (i18n)
├── components/
│   ├── auth/              # Authentication forms and components
│   ├── chat/              # Chat UI components (messages, input, sidebar)
│   ├── election-flow/     # Local/national election selection
│   ├── home/              # Homepage components
│   ├── icons/             # Custom icon components
│   ├── layout/            # Header, footer, page layout
│   ├── providers/         # React context providers
│   ├── share/             # Share session components
│   ├── topics/            # Topics browsing components
│   └── ui/                # Base UI components (shadcn/ui style)
├── config/                # App configuration
├── i18n/                  # Internationalization (messages, config)
└── lib/
    ├── election/          # Election-related Firebase queries
    ├── firebase/          # Firebase configuration and utilities
    ├── hooks/             # Custom React hooks
    ├── server-actions/    # Server-side actions (Stripe)
    ├── shared/            # Shared utilities
    ├── stores/            # Zustand store with actions
    ├── stripe/            # Stripe configuration
    ├── theme/             # Theme management
    └── types/             # TypeScript type definitions
```

## Getting Started

### Prerequisites

- Node.js 18.17 or later
- npm, yarn, pnpm, or bun

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/chatvote-frontend.git
cd chatvote-frontend

# Install dependencies
npm install
```

### Environment Variables

Create a `.env.local` file with the required environment variables:

```env
# Firebase
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=
NEXT_PUBLIC_FIREBASE_PROJECT_ID=
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=
NEXT_PUBLIC_FIREBASE_APP_ID=

# Firebase Admin
FIREBASE_ADMIN_PROJECT_ID=
FIREBASE_ADMIN_CLIENT_EMAIL=
FIREBASE_ADMIN_PRIVATE_KEY=

# Socket.io Backend
NEXT_PUBLIC_SOCKET_URL=

# Stripe
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=
STRIPE_SECRET_KEY=

# App URL
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

### Development

```bash
# Start the development server with Turbopack
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build

```bash
# Create production build
npm run build

# Start production server
npm start
```

### Code Quality

```bash
# Run ESLint
npm run lint

# Fix ESLint issues
npm run lint:fix

# Format code with Prettier
npm run format

# Check formatting
npm run format:check

# Type check
npm run type:check
```

### Bundle Analysis

```bash
# Analyze bundle size
ANALYZE=true npm run build
```

## Deployment

The application is optimized for deployment on [Vercel](https://vercel.com/). Simply connect your repository for automatic deployments.

For other platforms, ensure you:

1. Set all required environment variables
2. Configure Firebase Admin credentials securely
3. Set up WebSocket backend connectivity

## Contributing

We welcome contributions from the community. Please review open issues if you're interested in helping.

### Getting Started

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is **source-available** under the **PolyForm Noncommercial 1.0.0** license.

- Free for **non-commercial** use (see LICENSE for permitted purposes)
- Share the license text and any `Required Notice:` lines when distributing
- Contact us at contact@chatvote.org to:
  - Inform us about your use case
  - Get access to assets required for referencing chatvote in your project
- Do not use the chatvote name or logo without permission

## Acknowledgements

Chatvote enables users to engage with political party positions in a contemporary way, receiving AI-generated answers substantiated with sources from official party programs and documents.

---

Built with care for democratic participation.

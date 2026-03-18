import Image from "next/image";

type Props = {
  compact?: boolean;
};

const partners = [
  { name: "Co-CTO", logo: "/images/logos/sponsors/co-cto.png", href: "https://www.co-cto.fr/" },
  { name: "Zaq.ai", logo: "/images/logos/sponsors/zaq-ai.png", href: "https://zaq.ai" },
  { name: "Tandem", logo: "/images/logos/sponsors/tandem.svg", href: "https://tndm.fr" },
];

export default function SponsorPartners({ compact = false }: Props) {
  if (compact) {
    return (
      <div className="flex items-center justify-center gap-2 py-2 text-xs">
        <span className="text-white/30 whitespace-nowrap tracking-wide uppercase text-[10px]">Partenaires</span>
        <span className="text-white/15">·</span>
        <div className="flex items-center gap-2">
          {partners.map((p, i) => (
            <span key={p.name} className="flex items-center gap-1.5">
              {i > 0 && <span className="text-white/15">·</span>}
              <a
                href={p.href}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-white/50 hover:text-white/80 transition-colors"
              >
                <div className="flex size-4 items-center justify-center overflow-hidden rounded-full bg-white/10">
                  <Image src={p.logo} alt={p.name} width={12} height={12} className="object-contain" />
                </div>
                <span>{p.name}</span>
              </a>
            </span>
          ))}
        </div>
        <span className="text-white/15">|</span>
        <a
          href="https://www.scaleway.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-white/30 hover:text-white/60 transition-colors"
        >
          <span className="whitespace-nowrap">Soutenu par</span>
          <Image src="/images/logos/sponsors/scaleway.svg" alt="Scaleway" width={52} height={11} className="inline-block opacity-50 hover:opacity-80 transition-opacity" />
        </a>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col items-center gap-5 py-2">
      {/* Label */}
      <p className="text-[10px] font-medium tracking-[0.2em] uppercase text-white/25">
        Partenaires &amp; souveraineté numérique
      </p>

      {/* Partner pills */}
      <div className="flex items-center justify-center gap-2">
        {partners.map((partner, i) => (
          <div key={partner.name} className="flex items-center gap-2">
            {i > 0 && <div className="h-px w-6 bg-white/10" />}
            <a
              href={partner.href}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 backdrop-blur-sm transition-all hover:border-white/20 hover:bg-white/10"
            >
              <div className="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/10">
                <Image src={partner.logo} alt={partner.name} width={24} height={24} className="object-contain" />
              </div>
              <span className="whitespace-nowrap text-sm font-medium text-white/70 group-hover:text-white/90 transition-colors">
                {partner.name}
              </span>
            </a>
          </div>
        ))}
      </div>

      {/* Scaleway */}
      <div className="flex items-center gap-2 text-xs text-white/30">
        <span>Souveraineté numérique soutenue par</span>
        <a
          href="https://www.scaleway.com"
          target="_blank"
          rel="noopener noreferrer"
          className="opacity-40 hover:opacity-70 transition-opacity"
        >
          <Image src="/images/logos/sponsors/scaleway.svg" alt="Scaleway" width={160} height={32} className="inline-block" />
        </a>
      </div>
    </div>
  );
}

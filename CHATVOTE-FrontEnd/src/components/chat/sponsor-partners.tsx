import Image from "next/image";

type Props = {
  compact?: boolean;
};

const partners = [
  { name: "Zaq.ai", logo: "/images/logos/sponsors/zaq-ai.png", href: "https://zaq.ai" },
  { name: "Co-CTO", logo: "/images/logos/sponsors/co-cto.svg", href: "https://www.co-cto.fr/" },
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
    <div className="flex w-full flex-col items-center gap-3 py-2 md:gap-5">
      {/* Label */}
      <p className="text-[10px] font-medium tracking-[0.2em] uppercase text-white/25">
        Partenaires &amp; souveraineté numérique
      </p>

      {/* Partner pills */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        {partners.map((partner, i) => (
          <div key={partner.name} className="flex items-center gap-2">
            {i > 0 && <div className="hidden h-px w-6 bg-white/10 md:block" />}
            <a
              href={partner.href}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 backdrop-blur-sm transition-all hover:border-white/20 hover:bg-white/10 md:gap-2 md:px-3 md:py-1.5"
            >
              <div className="flex size-6 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white/10 md:size-8">
                <Image src={partner.logo} alt={partner.name} width={28} height={28} className="object-contain" />
              </div>
              <span className="whitespace-nowrap text-xs font-medium text-white/70 group-hover:text-white/90 transition-colors md:text-sm">
                {partner.name}
              </span>
            </a>
          </div>
        ))}
      </div>

      {/* Scaleway */}
      <div className="flex flex-col items-center gap-1 text-[10px] text-white/30 md:flex-row md:gap-2 md:text-xs">
        <span>Souveraineté numérique soutenue par</span>
        <a
          href="https://www.scaleway.com"
          target="_blank"
          rel="noopener noreferrer"
          className="opacity-40 hover:opacity-70 transition-opacity"
        >
          <Image src="/images/logos/sponsors/scaleway.svg" alt="Scaleway" width={160} height={32} className="inline-block w-24 h-auto md:w-40" />
        </a>
      </div>

      {/* Wahl.chat civil-tech partnership */}
      <div className="flex flex-col items-center gap-1 text-[10px] text-white/30 md:flex-row md:gap-2 md:text-xs">
        <span>En partenariat civil-tech européen avec</span>
        <a
          href="https://wahl.chat"
          target="_blank"
          rel="noopener noreferrer"
          className="text-white opacity-50 hover:opacity-80 transition-opacity"
        >
          <svg aria-label="Wahl.chat" className="h-8 w-auto" fill="none" viewBox="0 0 368 201" xmlns="http://www.w3.org/2000/svg">
            <path d="m62.353.301 13.954 37.462 3.014 9.012h.27l2.472-9.012L93.546.151h22.423l-28.3 92.012H75.101L63.197 58.649l-3.979-11.904h-.422l-4.249 11.754-12.99 33.634H28.84L.539.12h22.544l11.482 37.612 2.472 8.891h.27l3.015-8.89L54.125.27h8.228v.03ZM192.399 92.163h-25.858l-2.863-7.535-37.884-.271-4.37 7.806H98.85L139.055 0h16.003l37.341 92.163Zm-33.634-26.1-12.839-30.5-13.261 30.078 26.1.422ZM220.549.03v35.413h34.598V.03h22.001v92.163h-22.151V56.63h-34.448v35.563h-22.001V.03h22.001ZM312.862.03v72.06h26.492v20.103h-48.493V.181l22.001-.15ZM290.349 199.365H264.49l-2.863-7.535-37.884-.271-4.37 7.806H196.8l40.204-92.163h16.003l37.342 92.163Zm-33.635-26.13-12.838-30.5-13.261 30.078 26.099.422ZM367.081 107.473v18.596h-31.193l-.121 73.296-22.001-.151v-73.296h-30.801v-18.595l84.116.15ZM131.611 107.202v35.412h34.598v-35.412h22.001v92.163h-22.151v-35.563h-34.448v35.563H109.61v-92.163h22.001Z" fill="currentColor"/>
            <path d="m60.334 176.128-23.69-23.689 10.248-10.277 13.441 13.441 31.585-31.584 10.278 10.277-41.862 41.832Z" fill="#ED3833"/>
            <path d="M68.47 177.273c-3.887 2.14-8.136 3.225-12.778 3.225-3.737 0-7.203-.693-10.398-2.109-.904-.392-1.687-.935-2.501-1.387l-17.179 4.159 5.666-17.57c-1.235-3.135-1.868-6.48-1.868-10.006 0-3.647.693-7.113 2.049-10.398a27.57 27.57 0 0 1 5.546-8.559c2.32-2.411 5.093-4.34 8.257-5.757 3.195-1.416 6.66-2.109 10.398-2.109 4.008 0 7.715.783 11.151 2.32a27.681 27.681 0 0 1 5.094 3.014l14.466-14.918a48.706 48.706 0 0 0-11.543-7.324c-5.937-2.682-12.296-4.038-19.138-4.038-6.57 0-12.748 1.235-18.595 3.677-5.847 2.471-10.94 5.846-15.31 10.186-4.37 4.34-7.836 9.373-10.398 15.1-2.562 5.726-3.828 11.904-3.828 18.444 0 6.57 1.266 12.719 3.828 18.475 2.562 5.756 6.028 10.759 10.398 15.039 4.37 4.28 9.493 7.655 15.31 10.126 5.847 2.472 12.025 3.677 18.595 3.677 7.474 0 14.376-1.567 20.705-4.731 6.33-3.135 11.694-7.414 16.064-12.779l-14.497-14.346c-2.44 3.587-5.605 6.45-9.493 8.589ZM367.051 72.09h-19.138v20.103h19.138V72.09Z" fill="currentColor"/>
          </svg>
        </a>
      </div>
    </div>
  );
}

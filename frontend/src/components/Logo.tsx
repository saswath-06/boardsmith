interface BoardsmithLogoProps {
  size?: number;
  className?: string;
}

const BoardsmithLogo = ({ size = 28, className = "" }: BoardsmithLogoProps) => (
  <svg
    className={className}
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    aria-hidden="true"
  >
    {/* substrate */}
    <rect x="2" y="2" width="28" height="28" rx="4"
      fill="var(--bs-substrate)" stroke="var(--bs-copper)" strokeWidth="1.5" />
    {/* outer trace */}
    <path d="M 7 7 L 16 7 L 16 12 M 16 20 L 16 25 L 25 25"
      stroke="var(--bs-copper)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M 7 16 L 11 16 L 11 22"
      stroke="var(--bs-copper)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    {/* center pad */}
    <circle cx="16" cy="16" r="4.2" fill="var(--bs-gold)" stroke="var(--bs-copper)" strokeWidth="1.2"/>
    <circle cx="16" cy="16" r="1.6" fill="var(--bs-bg)"/>
    {/* corner pads */}
    <circle cx="7" cy="7" r="1.6" fill="var(--bs-gold)"/>
    <circle cx="25" cy="25" r="1.6" fill="var(--bs-gold)"/>
    <circle cx="11" cy="22" r="1.4" fill="var(--bs-gold)"/>
  </svg>
);

export default BoardsmithLogo;

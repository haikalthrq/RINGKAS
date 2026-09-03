import type { SVGProps } from "react";

export function RingkasLogo({
  className = "brand-mark-svg",
  size = 32,
  ...props
}: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Logo RINGKAS"
      role="img"
      {...props}
    >
      {/* Left spine of R */}
      <rect x="12" y="10" width="16" height="80" rx="3" fill="var(--orange-500, #f58220)" />
      
      {/* Histogram Bar 1 (Short) */}
      <rect x="33" y="52" width="14" height="38" rx="2.5" fill="var(--orange-500, #f58220)" />
      
      {/* Histogram Bar 2 (Mid-High) */}
      <rect x="52" y="34" width="14" height="56" rx="2.5" fill="var(--orange-500, #f58220)" />
      
      {/* Top loop of R */}
      <path
        d="M28 10H66C78.15 10 88 19.85 88 32C88 44.15 78.15 54 66 54H28V10Z"
        fill="var(--orange-500, #f58220)"
      />
      {/* Inner cutout of R loop */}
      <rect x="28" y="22" width="40" height="20" rx="2" fill="var(--surface, #ffffff)" />
      
      {/* Diagonal R leg */}
      <path
        d="M58 50L78 80H62L48 50H58Z"
        fill="var(--orange-500, #f58220)"
      />
      
      {/* Folded archive folio corner accent */}
      <path
        d="M72 74L88 90H72V74Z"
        fill="var(--blue-900, #083b5c)"
      />
      <path
        d="M88 74L72 74L88 90V74Z"
        fill="var(--blue-700, #005b96)"
        opacity="0.3"
      />
    </svg>
  );
}

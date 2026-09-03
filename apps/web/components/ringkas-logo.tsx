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
      viewBox="0 0 105 105"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Logo RINGKAS"
      role="img"
      {...props}
    >
      {/* 1. Left Spine - Lower Block (Histogram Bar 0) */}
      <rect x="8" y="66" width="16" height="28" fill="var(--orange-500, #F58220)" />

      {/* 2. Middle Histogram Bar (Bar 1 - mid height) */}
      <rect x="29" y="52" width="16" height="42" fill="var(--orange-500, #F58220)" />

      {/* 3. Right Histogram Bar (Bar 2 - tallest bar) */}
      <rect x="50" y="34" width="16" height="60" fill="var(--orange-500, #F58220)" />

      {/* 4. Left Spine Upper Block + Top Roof + R Bowl + Diagonal Leg */}
      <path
        d="
          M 8 11
          H 68
          C 86 11 98 23 98 40
          C 98 55 87 66 74 69
          L 97 92
          L 77 92
          L 66 69
          V 60
          H 8
          V 11
          Z
          M 24 25
          V 60
          H 66
          C 74 60 82 54 82 40
          C 82 28 74 25 66 25
          H 24
          Z
        "
        fill="var(--orange-500, #F58220)"
      />

      {/* 5. Page-turn dog ear: Dark Navy Underneath */}
      <polygon points="77,92 97,76 97,92" fill="var(--blue-950, #062c45)" />

      {/* 6. Page-turn dog ear: Folded Silver Paper Flap */}
      <polygon points="67,92 77,92 97,76" fill="#cbd5e1" />
      <polygon points="67,92 77,92 77,84" fill="#94a3b8" />
    </svg>
  );
}

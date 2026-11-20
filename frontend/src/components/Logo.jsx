import React from 'react';

/**
 * Precision geometric vault & cash flow emblem for PettyCash
 */
export function LogoIcon({ size = 32, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="PettyCash Emblem"
    >
      <defs>
        <linearGradient id="pc-grad-primary" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#34d399" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
        <linearGradient id="pc-grad-dark" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#064e3b" />
          <stop offset="100%" stopColor="#022c22" />
        </linearGradient>
        <linearGradient id="pc-grad-accent" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#6ee7b7" />
        </linearGradient>
      </defs>

      {/* Outer Hexagonal Shield Vault Ring */}
      <path
        d="M24 3L41 12.8V35.2L24 45L7 35.2V12.8L24 3Z"
        fill="url(#pc-grad-dark)"
        stroke="url(#pc-grad-primary)"
        strokeWidth="2"
        strokeLinejoin="round"
      />

      {/* Top Facet Highlight */}
      <path
        d="M24 6L37.5 13.8L24 21.6L10.5 13.8L24 6Z"
        fill="#10b981"
        fillOpacity="0.18"
      />

      {/* Left Shield Wall */}
      <path
        d="M10.5 15.6L24 23.4V39.2L10.5 31.4V15.6Z"
        fill="#047857"
        fillOpacity="0.35"
      />

      {/* Right Shield Wall */}
      <path
        d="M37.5 15.6L24 23.4V39.2L37.5 31.4V15.6Z"
        fill="#059669"
        fillOpacity="0.5"
      />

      {/* Center Vault Hub & Stylized Currency Rupee Glyph */}
      <circle cx="24" cy="24" r="10.5" fill="#022c22" stroke="url(#pc-grad-accent)" strokeWidth="1.8" />

      {/* Inner Currency Character / Precision Geometry */}
      {/* Top Bar */}
      <path d="M19 19.5H29" stroke="#6ee7b7" strokeWidth="1.8" strokeLinecap="round" />
      {/* Mid Bar */}
      <path d="M19 22.5H27" stroke="#6ee7b7" strokeWidth="1.8" strokeLinecap="round" />
      {/* Stem & Loop */}
      <path
        d="M22.5 19.5V24.5C22.5 24.5 25.5 24.5 25.5 22.5C25.5 20.5 22.5 20.5 22.5 20.5"
        stroke="#6ee7b7"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Slash Leg */}
      <path d="M22 24.5L27.5 30" stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" />

      {/* Corner Precision Nodes */}
      <circle cx="24" cy="3" r="1.5" fill="#34d399" />
      <circle cx="41" cy="12.8" r="1.5" fill="#34d399" />
      <circle cx="41" cy="35.2" r="1.5" fill="#34d399" />
      <circle cx="24" cy="45" r="1.5" fill="#34d399" />
      <circle cx="7" cy="35.2" r="1.5" fill="#34d399" />
      <circle cx="7" cy="12.8" r="1.5" fill="#34d399" />
    </svg>
  );
}

export default function Logo({ size = 32, showWordmark = true, className = '' }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div className="shrink-0 drop-shadow-[0_2px_8px_rgba(16,185,129,0.25)] flex items-center justify-center">
        <LogoIcon size={size} />
      </div>
      {showWordmark && (
        <div className="flex items-center gap-2">
          <span className="text-base font-bold tracking-tight text-slate-50">
            Petty<span className="text-emerald-400">Cash</span>
          </span>
          <span className="text-[10px] font-semibold tracking-wider uppercase px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
            v2.0
          </span>
        </div>
      )}
    </div>
  );
}

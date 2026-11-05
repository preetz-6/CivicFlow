/**
 * Original, generic municipal crest of CivicFlow Municipal Corporation.
 * Deliberately NOT the State Emblem of India or the Karnataka emblem (their use is
 * restricted by law). Motif: a civic hall above lake waves, ringed by the name.
 * Keep in sync with public/crest.svg (favicon).
 */
export function Crest({ size = 76, label }: { size?: number; label: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      role="img"
      aria-label={label}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <path id="cf-crest-top" d="M 20 60 A 40 40 0 0 1 100 60" />
        <path id="cf-crest-bottom" d="M 14 60 A 46 46 0 0 0 106 60" />
      </defs>
      <circle cx="60" cy="60" r="58" fill="#ffffff" stroke="#1b3a6b" strokeWidth="3" />
      <circle cx="60" cy="60" r="35" fill="none" stroke="#e87722" strokeWidth="2" />
      <text fill="#1b3a6b" fontFamily="Arial, sans-serif" fontSize="10" fontWeight="700" letterSpacing="1.5">
        <textPath href="#cf-crest-top" startOffset="50%" textAnchor="middle">
          CIVICFLOW
        </textPath>
      </text>
      <text fill="#1b3a6b" fontFamily="Arial, sans-serif" fontSize="7.2" fontWeight="700" letterSpacing="0.6">
        <textPath href="#cf-crest-bottom" startOffset="50%" textAnchor="middle">
          MUNICIPAL CORPORATION
        </textPath>
      </text>
      <circle cx="17" cy="60" r="2.2" fill="#e87722" />
      <circle cx="103" cy="60" r="2.2" fill="#e87722" />
      {/* civic hall */}
      <g fill="#1b3a6b">
        <polygon points="40,50 60,38 80,50" />
        <rect x="40" y="50" width="40" height="3.5" />
        <rect x="43" y="55" width="5" height="16" />
        <rect x="52" y="55" width="5" height="16" />
        <rect x="63" y="55" width="5" height="16" />
        <rect x="72" y="55" width="5" height="16" />
        <rect x="38" y="71" width="44" height="3.5" />
        <rect x="35" y="75.5" width="50" height="3" />
      </g>
      {/* lake waves */}
      <g fill="none" stroke="#e87722" strokeWidth="2" strokeLinecap="round">
        <path d="M 40 84 q 5 -3 10 0 t 10 0 t 10 0 t 10 0" />
        <path d="M 45 89 q 5 -3 10 0 t 10 0 t 10 0" />
      </g>
    </svg>
  );
}

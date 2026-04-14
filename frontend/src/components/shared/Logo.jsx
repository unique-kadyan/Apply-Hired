// Kalibr brand mark — a stylised "K" whose upper stroke extends as an upward
// arrow, suggesting a calibrated, measured career trajectory.
// Variants:
//   variant="mark"      — square logo only (favicon, avatar slot)
//   variant="wordmark"  — text-only "Kalibr" in brand gradient
//   variant="full"      — mark + wordmark side by side (default)

const GRADIENT_ID = 'kalibrGrad';

function Mark({ size = 32 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Kalibr logo"
      role="img"
    >
      <defs>
        <linearGradient id={GRADIENT_ID} x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="55%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#7c3aed" />
        </linearGradient>
      </defs>
      {/* Vertical stroke of the K — left bar */}
      <path d="M22 14 H34 V86 H22 Z" fill={`url(#${GRADIENT_ID})`} />
      {/* Upper diagonal — extends as upward arrow */}
      <path
        d="M34 50 L66 18 L82 18 L50 50 Z"
        fill={`url(#${GRADIENT_ID})`}
      />
      {/* Lower diagonal — slightly faded for depth */}
      <path
        d="M34 50 L50 50 L82 86 L66 86 Z"
        fill={`url(#${GRADIENT_ID})`}
        opacity="0.78"
      />
      {/* Calibration accent dot — top-right of the arrow */}
      <circle cx="84" cy="14" r="4.5" fill="#60a5fa" />
    </svg>
  );
}

function Wordmark({ height = 24, color }) {
  return (
    <span
      style={{
        fontSize: height,
        fontWeight: 800,
        letterSpacing: '-0.02em',
        lineHeight: 1,
        background: color
          ? 'none'
          : 'linear-gradient(135deg, #2563eb 0%, #3b82f6 55%, #7c3aed 100%)',
        WebkitBackgroundClip: color ? undefined : 'text',
        backgroundClip: color ? undefined : 'text',
        WebkitTextFillColor: color ? undefined : 'transparent',
        color: color || undefined,
        fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
        userSelect: 'none',
      }}
    >
      Kalibr
    </span>
  );
}

export default function Logo({ size = 28, variant = 'full', color }) {
  if (variant === 'mark') return <Mark size={size} />;
  if (variant === 'wordmark') return <Wordmark height={size} color={color} />;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: Math.round(size * 0.28),
      }}
    >
      <Mark size={size} />
      <Wordmark height={Math.round(size * 0.86)} color={color} />
    </span>
  );
}

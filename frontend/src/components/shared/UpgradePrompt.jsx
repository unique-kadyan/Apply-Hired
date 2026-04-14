// Reusable upgrade-to-Pro prompts.
//   <ProBadge tier={tier} />            small pill — shows current tier
//   <UpgradeBanner reason="..." />      inline banner inside a panel
//   <BlurOverlay text="..." />          full-overlay blur card for locked content

export function ProBadge({ tier }) {
  if (tier === 'admin') {
    return <span style={pillStyle('#fbbf24', '#78350f', '#fbbf24')}>★ Admin</span>;
  }
  if (tier === 'pro') {
    return <span style={pillStyle('#a855f7', '#1e1b4b', '#a855f7')}>⚡ Pro</span>;
  }
  return <span style={pillStyle('#94a3b8', '#1f2937', '#475569')}>Free</span>;
}

function pillStyle(color, bg, border) {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    fontSize: '0.7rem',
    fontWeight: 700,
    padding: '0.15rem 0.55rem',
    borderRadius: 999,
    color,
    background: bg,
    border: `1px solid ${border}`,
    letterSpacing: '0.02em',
  };
}

export function UpgradeBanner({ title, body, onUpgrade }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(124,58,237,0.12), rgba(37,99,235,0.12))',
      border: '1px solid rgba(124,58,237,0.35)',
      borderRadius: 10,
      padding: '0.85rem 1.1rem',
      display: 'flex',
      alignItems: 'center',
      gap: '0.85rem',
      flexWrap: 'wrap',
    }}>
      <div style={{ fontSize: '1.4rem' }}>⚡</div>
      <div style={{ flex: 1, minWidth: 200 }}>
        {title && <div style={{ fontWeight: 700, color: '#e2e8f0', marginBottom: 2 }}>{title}</div>}
        {body && <div style={{ fontSize: '0.82rem', color: '#cbd5e1' }}>{body}</div>}
      </div>
      {onUpgrade && (
        <button onClick={onUpgrade} style={{
          background: 'linear-gradient(135deg, #7c3aed, #2563eb)',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          padding: '0.5rem 1rem',
          fontWeight: 700,
          cursor: 'pointer',
          fontSize: '0.85rem',
          whiteSpace: 'nowrap',
        }}>Upgrade to Pro</button>
      )}
    </div>
  );
}

export function BlurOverlay({ text, ctaText = 'Upgrade to Pro', onCta }) {
  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(15,23,42,0.6)',
      backdropFilter: 'blur(6px)',
      WebkitBackdropFilter: 'blur(6px)',
      borderRadius: 'inherit',
      gap: '0.6rem',
      padding: '1rem',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: '1.6rem' }}>🔒</div>
      <div style={{ color: '#e2e8f0', fontSize: '0.9rem', maxWidth: 320 }}>{text}</div>
      {onCta && (
        <button onClick={onCta} style={{
          background: 'linear-gradient(135deg, #7c3aed, #2563eb)',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          padding: '0.45rem 1.1rem',
          fontWeight: 700,
          cursor: 'pointer',
          fontSize: '0.82rem',
        }}>{ctaText}</button>
      )}
    </div>
  );
}

export default { ProBadge, UpgradeBanner, BlurOverlay };

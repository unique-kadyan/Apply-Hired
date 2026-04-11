'use client';

export function Badge({ score }) {
  const pct = Math.round(score * 100);
  const cls = pct >= 70 ? { background: '#065f46', color: '#6ee7b7' } : pct >= 40 ? { background: '#78350f', color: '#fcd34d' } : { background: '#7f1d1d', color: '#fca5a5' };
  return <span style={{ ...cls, padding: '0.2rem 0.6rem', borderRadius: 20, fontWeight: 700, fontSize: '0.82rem', display: 'inline-block', minWidth: 44, textAlign: 'center' }}>{pct}%</span>;
}

export function StatusBadge({ status }) {
  const colors = { new: { bg: '#164e63', fg: '#67e8f9' }, previous: { bg: '#334155', fg: '#94a3b8' }, saved: { bg: '#1e3a5f', fg: '#93c5fd' }, applied: { bg: '#065f46', fg: '#6ee7b7' }, interview: { bg: '#581c87', fg: '#d8b4fe' }, rejected: { bg: '#7f1d1d', fg: '#fca5a5' }, offer: { bg: '#14532d', fg: '#86efac' } };
  const c = colors[status] || colors.new;
  return <span style={{ background: c.bg, color: c.fg, padding: '0.2rem 0.6rem', borderRadius: 20, fontWeight: 600, fontSize: '0.78rem', textTransform: 'capitalize' }}>{status}</span>;
}

export function SkillChip({ label, selected, onClick }) {
  return (
    <button onClick={onClick} style={{ background: selected ? '#1e3a5f' : 'var(--bg2)', border: `1px solid ${selected ? '#3b82f6' : '#475569'}`, color: selected ? '#93c5fd' : 'var(--muted)', padding: '0.35rem 0.8rem', borderRadius: 20, fontSize: '0.85rem', fontWeight: selected ? 600 : 500, cursor: 'pointer', transition: 'all 0.15s', margin: '0.15rem' }}>
      {label}
    </button>
  );
}

'use client';

export default function ResumeScoreCard({ score }) {
  if (!score || !score.sections) return null;
  const total = score.total_score || 0;
  const color = total >= 80 ? '#6ee7b7' : total >= 60 ? '#fcd34d' : total >= 40 ? '#fdba74' : '#fca5a5';
  const label = total >= 80 ? 'Excellent' : total >= 60 ? 'Good' : total >= 40 ? 'Needs Work' : 'Weak';

  const sectionLabels = {
    contact_info: 'Contact Info', summary: 'Summary', skills: 'Skills',
    experience: 'Experience', education: 'Education', formatting: 'Formatting', ats_keywords: 'ATS Keywords',
  };

  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: '1.5rem', marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <div style={{
          width: 80, height: 80, borderRadius: '50%',
          background: `conic-gradient(${color} ${total * 3.6}deg, var(--bg3) 0deg)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%', background: 'var(--bg2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column',
          }}>
            <span style={{ fontSize: '1.3rem', fontWeight: 800, color, lineHeight: 1 }}>{total}</span>
            <span style={{ fontSize: '0.6rem', color: 'var(--muted)' }}>/100</span>
          </div>
        </div>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Resume Score</h2>
          <p style={{ color, fontWeight: 600, margin: '0.2rem 0 0' }}>{label}</p>
        </div>
      </div>
      <div style={{ display: 'grid', gap: '0.5rem', marginBottom: '0.5rem' }}>
        {Object.entries(score.sections).map(([key, sec]) => {
          const pct = Math.round((sec.score / sec.max) * 100);
          const barColor = pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--yellow)' : 'var(--red)';
          return (
            <div key={key}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: '0.2rem' }}>
                <span style={{ color: 'var(--text2)' }}>{sectionLabels[key] || key}</span>
                <span style={{ color: 'var(--muted)' }}>{sec.score}/{sec.max}</span>
              </div>
              <div style={{ background: 'var(--bg3)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                <div style={{ background: barColor, height: '100%', borderRadius: 6, width: `${pct}%`, transition: 'width 0.5s' }}></div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

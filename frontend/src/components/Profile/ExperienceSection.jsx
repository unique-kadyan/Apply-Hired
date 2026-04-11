'use client';
import { useState } from 'react';
import styles from '@/lib/styles';

export default function ExperienceSection({ experience }) {
  const [activeIdx, setActiveIdx] = useState(null);
  const COLORS = ['#2563eb', '#059669', '#7c3aed', '#d97706', '#0891b2', '#dc2626', '#be185d', '#0d9488'];

  function parsePeriod(period) {
    if (!period) return null;
    const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
    const parts = period.replace(/\u2013/g, '-').split(/\s*-\s*/);
    function parseDate(s) {
      s = (s || '').trim().toLowerCase();
      if (s === 'present' || s === 'current' || s === 'now') return new Date();
      const m = s.match(/([a-z]+)\s+(\d{4})/);
      if (m && MONTHS[m[1].slice(0, 3)] !== undefined) return new Date(+m[2], MONTHS[m[1].slice(0, 3)], 1);
      const y = s.match(/\d{4}/);
      return y ? new Date(+y[0], 0, 1) : null;
    }
    const start = parseDate(parts[0]);
    const end = parseDate(parts[1] || 'present');
    return (start && end) ? { start, end } : null;
  }

  function fmtDuration(start, end) {
    const months = Math.round((end - start) / (1000 * 60 * 60 * 24 * 30.4));
    if (months < 1) return '< 1 mo';
    const y = Math.floor(months / 12), m = months % 12;
    return [y > 0 ? `${y} yr${y > 1 ? 's' : ''}` : '', m > 0 ? `${m} mo` : ''].filter(Boolean).join(' ');
  }

  const items = experience.map((exp, i) => {
    const parsed = parsePeriod(exp.period);
    return { ...exp, parsed, color: COLORS[i % COLORS.length] };
  }).filter(e => e.parsed);

  if (items.length === 0) {
    return (
      <div style={styles.card}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Work Experience</h2>
        {experience.map((exp, i) => (
          <div key={i} style={{ marginBottom: '1.25rem', paddingBottom: '1.25rem', borderBottom: i < experience.length - 1 ? '1px solid var(--border)' : 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.25rem' }}>
              <h3 style={{ color: 'var(--text)', fontSize: '1rem' }}>{exp.title}</h3>
              <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>{exp.period}</span>
            </div>
            <p style={{ color: '#60a5fa', marginBottom: '0.4rem', fontSize: '0.92rem' }}>{exp.company}</p>
            <ul style={{ paddingLeft: '1.4rem', lineHeight: 1.8, color: '#cbd5e1', fontSize: '0.88rem' }}>
              {(exp.highlights || []).map((h, j) => <li key={j}>{h}</li>)}
            </ul>
          </div>
        ))}
      </div>
    );
  }

  const minDate = new Date(Math.min(...items.map(e => e.parsed.start)));
  const maxDate = new Date(Math.max(...items.map(e => e.parsed.end)));
  minDate.setMonth(minDate.getMonth() - 3);
  maxDate.setMonth(maxDate.getMonth() + 3);
  const totalMs = maxDate - minDate;
  const pct = d => ((d - minDate) / totalMs) * 100;

  const ticks = [];
  const startYear = minDate.getFullYear();
  const endYear = maxDate.getFullYear() + 1;
  for (let y = startYear; y <= endYear; y++) {
    const p = pct(new Date(y, 0, 1));
    if (p >= 0 && p <= 100) ticks.push({ year: y, p });
  }

  return (
    <div style={styles.card}>
      <h2 style={{ fontSize: '1.1rem', marginBottom: '1.5rem' }}>Work Experience</h2>

      <div style={{ position: 'relative', marginBottom: '2rem', overflowX: 'auto' }}>
        <div style={{ minWidth: 480, position: 'relative' }}>
          <div style={{ position: 'relative', height: `${items.length * 52 + 8}px`, marginBottom: '0.5rem' }}>
            {items.map((exp, i) => {
              const left = pct(exp.parsed.start);
              const right = pct(exp.parsed.end);
              const width = Math.max(right - left, 0.8);
              const dur = fmtDuration(exp.parsed.start, exp.parsed.end);
              const isEnd = exp.parsed.end >= new Date() - 86400000;
              const isActive = activeIdx === i;
              return (
                <div key={i}
                  onMouseEnter={() => setActiveIdx(i)}
                  onMouseLeave={() => setActiveIdx(null)}
                  onClick={() => setActiveIdx(isActive ? null : i)}
                  style={{
                    position: 'absolute',
                    top: `${i * 52 + 4}px`,
                    left: `${left}%`,
                    width: `${width}%`,
                    height: 40,
                    borderRadius: 8,
                    background: isActive ? exp.color : `${exp.color}44`,
                    border: `2px solid ${exp.color}`,
                    cursor: 'pointer',
                    transition: 'background 0.2s, box-shadow 0.2s',
                    boxShadow: isActive ? `0 0 0 3px ${exp.color}55` : 'none',
                    display: 'flex', alignItems: 'center',
                    padding: '0 0.6rem',
                    overflow: 'hidden',
                    boxSizing: 'border-box',
                  }}>
                  <div style={{ overflow: 'hidden', flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.7rem', color: isActive ? '#fff' : exp.color, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {exp.company}
                    </div>
                    <div style={{ fontSize: '0.65rem', color: isActive ? 'rgba(255,255,255,0.85)' : '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {exp.title}
                    </div>
                  </div>
                  <span style={{ fontSize: '0.62rem', background: isActive ? 'rgba(0,0,0,0.25)' : `${exp.color}33`, color: isActive ? '#fff' : exp.color, borderRadius: 4, padding: '0.1rem 0.35rem', marginLeft: 4, flexShrink: 0, fontWeight: 700, whiteSpace: 'nowrap' }}>
                    {dur}{isEnd ? ' 🟢' : ''}
                  </span>
                </div>
              );
            })}
          </div>

          <div style={{ position: 'relative', height: 24, borderTop: '1px solid var(--border)' }}>
            {ticks.map(t => (
              <div key={t.year} style={{ position: 'absolute', left: `${t.p}%`, top: 0, transform: 'translateX(-50%)' }}>
                <div style={{ width: 1, height: 6, background: 'var(--border)', margin: '0 auto' }} />
                <span style={{ fontSize: '0.68rem', color: 'var(--muted)', whiteSpace: 'nowrap' }}>{t.year}</span>
              </div>
            ))}
          </div>

          {(() => {
            const tp = pct(new Date());
            if (tp < 0 || tp > 100) return null;
            return (
              <div style={{ position: 'absolute', top: 0, left: `${tp}%`, width: 1, height: `${items.length * 52 + 8}px`, background: 'rgba(37,99,235,0.5)', borderLeft: '1px dashed #2563eb', pointerEvents: 'none' }}>
                <span style={{ position: 'absolute', top: -18, left: 3, fontSize: '0.6rem', color: '#2563eb', fontWeight: 700, whiteSpace: 'nowrap' }}>Today</span>
              </div>
            );
          })()}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
        {items.map((exp, i) => {
          const dur = fmtDuration(exp.parsed.start, exp.parsed.end);
          const isEnd = exp.parsed.end >= new Date() - 86400000;
          return (
            <div key={i}
              onMouseEnter={() => setActiveIdx(i)}
              onMouseLeave={() => setActiveIdx(null)}
              style={{
                background: activeIdx === i ? `${exp.color}14` : 'rgba(255,255,255,0.02)',
                border: `1px solid ${activeIdx === i ? exp.color : 'var(--border)'}`,
                borderLeft: `4px solid ${exp.color}`,
                borderRadius: 10, padding: '0.85rem 1rem',
                transition: 'border-color 0.2s, background 0.2s',
                cursor: 'default',
              }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem', marginBottom: '0.3rem' }}>
                <div style={{ minWidth: 0 }}>
                  <p style={{ fontWeight: 700, color: 'var(--text)', fontSize: '0.92rem', marginBottom: '0.1rem' }}>{exp.title}</p>
                  <p style={{ color: exp.color, fontSize: '0.82rem', fontWeight: 600 }}>{exp.company}</p>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <span style={{ display: 'inline-block', background: `${exp.color}22`, color: exp.color, border: `1px solid ${exp.color}55`, borderRadius: 6, padding: '0.15rem 0.5rem', fontSize: '0.7rem', fontWeight: 700 }}>
                    {dur}
                  </span>
                  {isEnd && <span style={{ display: 'block', fontSize: '0.62rem', color: '#6ee7b7', marginTop: 2 }}>● Current</span>}
                </div>
              </div>
              <p style={{ color: 'var(--muted)', fontSize: '0.75rem', marginBottom: '0.5rem' }}>{exp.period}</p>
              {(exp.highlights || []).length > 0 && (
                <ul style={{ paddingLeft: '1.1rem', margin: 0, color: '#94a3b8', fontSize: '0.8rem', lineHeight: 1.75 }}>
                  {exp.highlights.slice(0, 3).map((h, j) => <li key={j}>{h}</li>)}
                  {exp.highlights.length > 3 && <li style={{ color: '#475569' }}>+{exp.highlights.length - 3} more…</li>}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

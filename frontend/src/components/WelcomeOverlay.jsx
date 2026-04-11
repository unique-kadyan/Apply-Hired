'use client';
import { useState, useEffect, useMemo } from 'react';

export default function WelcomeOverlay({ name, isSignup, onDone }) {
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setFading(true), 3200);
    const t2 = setTimeout(() => onDone(), 3800);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  const confetti = useMemo(() => {
    const colors = ['#6366f1','#34d399','#fbbf24','#f472b6','#60a5fa','#a78bfa','#fb923c','#4ade80','#f87171','#38bdf8'];
    const shapes = ['square','rect','circle'];
    return Array.from({ length: 80 }, (_, i) => ({
      id: i,
      color: colors[i % colors.length],
      shape: shapes[i % shapes.length],
      left: Math.random() * 100,
      size: 6 + Math.random() * 10,
      delay: Math.random() * 1.2,
      duration: 2.0 + Math.random() * 1.5,
      rotate: Math.random() * 360,
      drift: (Math.random() - 0.5) * 120,
    }));
  }, []);

  const headline = isSignup
    ? `Welcome, ${name}! 🎉`
    : `Welcome back, ${name}! 🎊`;

  const slogans = isSignup
    ? [
        "Your next big break starts here.",
        "Let's chart your path to the top.",
        "Great careers don't happen by chance — they're built.",
        "We'll help you charm every opportunity that comes your way.",
      ]
    : [
        "Your dream role is one application away.",
        "Ready to crack your next opportunity?",
        "Every great hire was once a great applicant.",
        "The right job is out there — let's find it together.",
      ];
  const slogan = slogans[Math.floor(Date.now() / 1000) % slogans.length];

  return (
    <div onClick={onDone} style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(6,8,20,0.88)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden', cursor: 'pointer',
      opacity: fading ? 0 : 1, transition: 'opacity 0.6s ease',
    }}>
      {confetti.map(p => (
        <div key={p.id} style={{
          position: 'absolute',
          left: `${p.left}%`,
          top: '-20px',
          width: p.shape === 'rect' ? p.size * 2.2 : p.size,
          height: p.shape === 'circle' ? p.size : p.size,
          borderRadius: p.shape === 'circle' ? '50%' : p.shape === 'square' ? 2 : 1,
          background: p.color,
          opacity: 0.9,
          animation: `confettiFall ${p.duration}s ${p.delay}s ease-in forwards`,
          '--drift': `${p.drift}px`,
          '--rot': `${p.rotate}deg`,
        }} />
      ))}

      <div onClick={e => e.stopPropagation()} style={{
        background: 'linear-gradient(135deg, rgba(30,32,60,0.98) 0%, rgba(15,17,35,0.98) 100%)',
        border: '1px solid rgba(99,102,241,0.4)',
        borderRadius: 20,
        padding: '2.5rem 3rem',
        textAlign: 'center',
        maxWidth: 440,
        width: '90%',
        boxShadow: '0 0 60px rgba(99,102,241,0.25), 0 20px 60px rgba(0,0,0,0.6)',
        animation: 'popIn 0.5s cubic-bezier(0.34,1.56,0.64,1) both',
        position: 'relative',
      }}>
        <div style={{
          position: 'absolute', inset: -2, borderRadius: 22, zIndex: -1,
          background: 'linear-gradient(135deg,#6366f1,#34d399,#fbbf24,#f472b6)',
          opacity: 0.35, filter: 'blur(8px)',
        }} />

        <div style={{ fontSize: '3rem', marginBottom: '0.75rem', lineHeight: 1 }}>
          {isSignup ? '🚀' : '✨'}
        </div>
        <h2 style={{
          fontSize: '1.6rem', fontWeight: 800, margin: '0 0 0.6rem',
          background: 'linear-gradient(135deg,#a5b4fc,#34d399)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          lineHeight: 1.2,
        }}>{headline}</h2>

        {isSignup && (
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem', margin: '0 0 0.75rem', lineHeight: 1.5 }}>
            Help us aid to charm your professional journey.
          </p>
        )}

        <p style={{
          color: '#94a3b8', fontSize: '1rem', margin: '0 0 1.5rem',
          fontStyle: 'italic', lineHeight: 1.5,
        }}>"{slogan}"</p>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', justifyContent: 'center' }}>
          {[...Array(5)].map((_, i) => (
            <div key={i} style={{
              width: i === 2 ? 24 : i === 1 || i === 3 ? 16 : 8,
              height: 4, borderRadius: 2,
              background: i === 2 ? '#6366f1' : 'rgba(99,102,241,0.3)',
              animation: `pulse 1.5s ${i * 0.15}s ease-in-out infinite`,
            }} />
          ))}
        </div>

        <p style={{ color: 'rgba(100,116,139,0.7)', fontSize: '0.72rem', marginTop: '1.2rem' }}>
          Click anywhere to continue
        </p>
      </div>

      <style>{`
        @keyframes confettiFall {
          0%   { transform: translateY(0) translateX(0) rotate(0deg); opacity: 1; }
          100% { transform: translateY(110vh) translateX(var(--drift)) rotate(calc(var(--rot) * 4)); opacity: 0; }
        }
        @keyframes popIn {
          from { opacity: 0; transform: scale(0.7); }
          to   { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}

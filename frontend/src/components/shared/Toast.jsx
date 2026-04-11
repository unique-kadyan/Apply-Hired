'use client';
import { useEffect } from 'react';

export default function Toast({ message, type, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 4000); return () => clearTimeout(t); }, []);
  const bg = type === 'success' ? '#065f46' : type === 'error' ? '#7f1d1d' : '#78350f';
  const fg = type === 'success' ? '#6ee7b7' : type === 'error' ? '#fca5a5' : '#fcd34d';
  return (
    <div style={{ position: 'fixed', bottom: 20, right: 20, background: 'var(--bg2)', border: `1px solid ${fg}33`, borderRadius: 12, padding: '1rem 1.5rem', zIndex: 200, boxShadow: '0 8px 30px rgba(0,0,0,0.5)', maxWidth: 400, animation: 'fadeIn 0.3s', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
      <span style={{ color: fg, fontSize: '1.2rem' }}>{type === 'success' ? '✓' : type === 'error' ? '✗' : '⚠'}</span>
      <span style={{ color: fg, fontWeight: 500 }}>{message}</span>
      <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', marginLeft: 'auto', fontSize: '1rem' }}>&times;</button>
    </div>
  );
}

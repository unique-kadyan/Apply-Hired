const styles = {
  navbar: { background: 'var(--bg2)', borderBottom: '1px solid var(--border)', padding: '0 1.5rem', display: 'flex', alignItems: 'center', gap: '1rem', position: 'sticky', top: 0, zIndex: 100, height: 52, backdropFilter: 'blur(12px)' },
  logo: { fontSize: '1.15rem', fontWeight: 700, color: '#60a5fa', letterSpacing: '-0.02em', whiteSpace: 'nowrap' },
  navLink: { color: 'var(--muted)', fontWeight: 500, padding: '0.4rem 0.75rem', borderRadius: 8, transition: 'all 0.15s', cursor: 'pointer', fontSize: '0.88rem', border: 'none', background: 'none', whiteSpace: 'nowrap' },
  navActive: { color: '#fff', background: 'rgba(37,99,235,0.15)' },
  container: { maxWidth: 1400, margin: '0 auto', padding: 'clamp(0.75rem, 2vw, 1.5rem) clamp(0.75rem, 3vw, 2rem)', animation: 'fadeIn 0.3s ease' },
  card: { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: '1.5rem', marginBottom: '1rem', transition: 'border-color 0.2s' },
  btn: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', padding: '0.55rem 1.1rem', border: 'none', borderRadius: 8, fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s', textDecoration: 'none', whiteSpace: 'nowrap' },
  btnPrimary: { background: 'var(--accent)', color: '#fff' },
  btnSuccess: { background: 'var(--green)', color: '#fff' },
  btnSecondary: { background: '#475569', color: '#fff' },
  btnDanger: { background: 'var(--red)', color: '#fff' },
  btnSm: { padding: '0.35rem 0.7rem', fontSize: '0.8rem' },
  input: { background: 'var(--bg)', border: '1px solid #475569', color: 'var(--text2)', padding: '0.6rem 1rem', borderRadius: 8, fontSize: '0.9rem', width: '100%', outline: 'none', transition: 'border-color 0.2s' },
  select: { background: 'var(--bg)', border: '1px solid #475569', color: 'var(--text2)', padding: '0.5rem 1rem', borderRadius: 8, fontSize: '0.9rem', outline: 'none' },
};
export default styles;

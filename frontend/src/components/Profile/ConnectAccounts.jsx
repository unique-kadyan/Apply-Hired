'use client';
import { useState, useEffect } from 'react';
import api from '@/lib/api';
import sse from '@/lib/sse';
import styles from '@/lib/styles';

function fmtDate(d) {
  if (!d) return '';
  const dt = new Date(d);
  const now = new Date();
  const diff = Math.round((now - dt) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff < 7) return `${diff}d ago`;
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function ConnectAccounts({ profile, setProfile, showToast }) {
  const [editing, setEditing] = useState(null);
  const [githubInput, setGithubInput] = useState(profile.github_username || '');
  const [linkedinInput, setLinkedinInput] = useState(profile.linkedin || '');
  const [portfolioInput, setPortfolioInput] = useState(profile.website || '');
  const [loading, setLoading] = useState('');
  const [githubRateLimit, setGithubRateLimit] = useState(false);
  const [githubTokenInput, setGithubTokenInput] = useState(profile.github_token ? '••••••••' : '');
  const [editingToken, setEditingToken] = useState(false);
  const [showAllProjects, setShowAllProjects] = useState(false);

  const [gmailStatus, setGmailStatus] = useState(null);
  const [gmailSyncing, setGmailSyncing] = useState(false);
  const [gmailResult, setGmailResult] = useState(null);

  useEffect(() => {
    api.get('/api/gmail/status').then(r => setGmailStatus(r)).catch(() => setGmailStatus({ connected: false }));
  }, []);

  // Live: when a Gmail sync finishes (manual or scheduled), refresh status & result.
  useEffect(() => {
    const off = sse.subscribe('gmail_synced', (data) => {
      setGmailResult(data);
      api.get('/api/gmail/status').then(r => setGmailStatus(r)).catch(() => {});
    });
    return off;
  }, []);

  useEffect(() => {
    const onMessage = (e) => {
      if (e.data?.type === 'gmail_connected') {
        api.get('/api/gmail/status').then(r => setGmailStatus(r));
        showToast('Gmail connected! Click "Sync Now" to scan for interview & offer emails.', 'success');
      } else if (e.data?.type === 'gmail_error') {
        showToast(`Gmail connection failed: ${e.data.detail || 'unknown error'}`, 'error');
      }
    };
    window.addEventListener('message', onMessage);
    if (new URLSearchParams(window.location.search).get('gmail_connected')) {
      window.history.replaceState({}, '', '/');
      api.get('/api/gmail/status').then(r => setGmailStatus(r));
      showToast('Gmail connected! Click "Sync Now" to scan for interview & offer emails.', 'success');
    }
    return () => window.removeEventListener('message', onMessage);
  }, []);

  const connectGmail = () => {
    const w = 600, h = 700;
    const left = Math.max(0, (screen.width - w) / 2);
    const top = Math.max(0, (screen.height - h) / 2);
    window.open('/api/gmail/auth', 'gmail_oauth', `width=${w},height=${h},top=${top},left=${left},menubar=no,toolbar=no,location=no,status=no`);
  };

  const gmailSync = async () => {
    setGmailSyncing(true);
    setGmailResult(null);
    try {
      const res = await api.post('/api/gmail/sync', {});
      setGmailResult(res);
      api.get('/api/gmail/status').then(r => setGmailStatus(r));
      const total = (res.interview || 0) + (res.offer || 0);
      if (total > 0) showToast(`Gmail sync: ${res.interview} interview${res.interview !== 1 ? 's' : ''}, ${res.offer} offer${res.offer !== 1 ? 's' : ''} detected!`, 'success');
      else showToast(`Gmail sync complete — ${res.scanned} emails scanned, no new updates.`, 'success');
    } catch { showToast('Gmail sync failed', 'error'); }
    setGmailSyncing(false);
  };

  const gmailDisconnect = async () => {
    await api.post('/api/gmail/disconnect', {});
    setGmailStatus({ connected: false });
    setGmailResult(null);
    showToast('Gmail disconnected', 'success');
  };

  const GITHUB_TOKEN_URL = 'https://github.com/settings/personal-access-tokens/new';

  const connectGithub = async (tokenOverride) => {
    const val = githubInput.trim();
    if (!val) { showToast('Enter a GitHub username or URL', 'error'); return; }
    setLoading('github');
    try {
      const body = { username: val };
      const token = tokenOverride || (editingToken ? githubTokenInput.trim() : '');
      if (token && !token.startsWith('•')) body.token = token;
      const res = await api.post('/api/profile/connect/github', body);
      if (res.error) {
        if (res.rate_limit) { setGithubRateLimit(true); setEditingToken(true); return; }
        showToast(res.error, 'error');
      } else {
        setProfile(res.profile);
        setGithubRateLimit(false);
        setEditingToken(false);
        if (res.profile?.github_token) setGithubTokenInput('••••••••');
        const s = res.stats || {};
        showToast(`✓ GitHub connected — ${s.public_repos || 0} repos, ${s.languages_added || 0} languages, ${s.projects_added || 0} projects imported`, 'success');
        setEditing(null);
      }
    } catch (err) { showToast('Could not reach server. Please try again.', 'error'); }
    setLoading('');
  };

  const connectLinkedin = async () => {
    if (!linkedinInput.trim()) return;
    setLoading('linkedin');
    try {
      const res = await api.post('/api/profile/connect/linkedin', { url: linkedinInput });
      if (res.error) showToast(res.error, 'error');
      else { setProfile(res.profile); showToast('LinkedIn connected!', 'success'); setEditing(null); }
    } catch (err) { showToast('Failed to connect LinkedIn', 'error'); }
    setLoading('');
  };

  const connectPortfolio = async () => {
    if (!portfolioInput.trim()) return;
    setLoading('portfolio');
    try {
      const res = await api.post('/api/profile/connect/portfolio', { url: portfolioInput });
      if (res.error) showToast(res.error, 'error');
      else { setProfile(res.profile); showToast('Portfolio connected!', 'success'); setEditing(null); }
    } catch (err) { showToast('Failed to connect portfolio', 'error'); }
    setLoading('');
  };

  const accounts = [
    { key: 'github', label: 'GitHub', value: profile.github, display: profile.github_username || profile.github, input: githubInput, setInput: setGithubInput, connect: connectGithub, placeholder: 'username or URL' },
    { key: 'linkedin', label: 'LinkedIn', value: profile.linkedin, display: profile.linkedin, input: linkedinInput, setInput: setLinkedinInput, connect: connectLinkedin, placeholder: 'https://linkedin.com/in/yourname' },
    { key: 'portfolio', label: 'Portfolio', value: profile.website, display: profile.website, input: portfolioInput, setInput: setPortfolioInput, connect: connectPortfolio, placeholder: 'https://yoursite.com' },
  ];

  const connectedStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid var(--border)' };
  const editRowStyle = { display: 'flex', gap: '0.5rem', alignItems: 'center', padding: '0.6rem 0', borderBottom: '1px solid var(--border)' };

  const LANG_COLORS = {
    JavaScript: { bg: 'rgba(234,179,8,0.15)', color: '#fbbf24', border: 'rgba(234,179,8,0.3)' },
    TypeScript: { bg: 'rgba(59,130,246,0.15)', color: '#60a5fa', border: 'rgba(59,130,246,0.3)' },
    Python: { bg: 'rgba(34,197,94,0.15)', color: '#4ade80', border: 'rgba(34,197,94,0.3)' },
    Java: { bg: 'rgba(239,68,68,0.15)', color: '#f87171', border: 'rgba(239,68,68,0.3)' },
    Go: { bg: 'rgba(6,182,212,0.15)', color: '#22d3ee', border: 'rgba(6,182,212,0.3)' },
    Rust: { bg: 'rgba(249,115,22,0.15)', color: '#fb923c', border: 'rgba(249,115,22,0.3)' },
    HTML: { bg: 'rgba(249,115,22,0.12)', color: '#fdba74', border: 'rgba(249,115,22,0.25)' },
    CSS: { bg: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: 'rgba(139,92,246,0.3)' },
    Kotlin: { bg: 'rgba(168,85,247,0.15)', color: '#c084fc', border: 'rgba(168,85,247,0.3)' },
    Swift: { bg: 'rgba(251,146,60,0.15)', color: '#fb923c', border: 'rgba(251,146,60,0.3)' },
    Ruby: { bg: 'rgba(239,68,68,0.12)', color: '#fca5a5', border: 'rgba(239,68,68,0.25)' },
    Shell: { bg: 'rgba(15,118,110,0.15)', color: '#2dd4bf', border: 'rgba(15,118,110,0.3)' },
    _default: { bg: 'rgba(100,116,139,0.15)', color: 'var(--muted)', border: 'rgba(100,116,139,0.25)' },
  };
  const tagStyle = (lang) => {
    const c = LANG_COLORS[lang] || LANG_COLORS._default;
    return { background: c.bg, color: c.color, border: `1px solid ${c.border}`, padding: '0.1rem 0.45rem', borderRadius: 20, fontSize: '0.68rem', fontWeight: 600, whiteSpace: 'nowrap' };
  };
  const topicStyle = { background: 'rgba(99,102,241,0.12)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.25)', padding: '0.1rem 0.4rem', borderRadius: 20, fontSize: '0.66rem', fontWeight: 500, whiteSpace: 'nowrap' };

  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: '1.5rem', marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h2 style={{ fontSize: '1.1rem', margin: 0 }}>Connected Accounts</h2>
        {profile.profile_updated_at && (
          <span style={{ color: '#475569', fontSize: '0.72rem' }}>
            Updated {new Date(profile.profile_updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      {accounts.map(acc => (
        <div key={acc.key}>
          {editing === acc.key ? (
            <div style={{ ...editRowStyle, flexWrap: 'wrap', gap: '0.5rem' }}>
              <span style={{ color: 'var(--muted)', fontSize: '0.85rem', minWidth: 65, fontWeight: 600 }}>{acc.label}</span>
              <input
                style={{ ...styles.input, flex: 1, minWidth: 180, marginBottom: 0 }}
                value={acc.input}
                onChange={e => acc.setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') acc.connect(); if (e.key === 'Escape') setEditing(null); }}
                placeholder={acc.placeholder}
                autoFocus
              />
              <button onClick={() => acc.connect()} disabled={loading === acc.key || !acc.input.trim()}
                style={{ ...styles.btn, ...styles.btnSm, ...styles.btnPrimary, minWidth: 80, opacity: !acc.input.trim() ? 0.5 : 1 }}>
                {loading === acc.key ? '⏳ Importing…' : 'Connect'}
              </button>
              <button onClick={() => setEditing(null)} style={{ ...styles.btn, ...styles.btnSm, ...styles.btnSecondary }}>Cancel</button>
            </div>
          ) : acc.value ? (
            <div style={connectedStyle}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ color: 'var(--green2)', fontSize: '0.82rem' }}>&#10003;</span>
                <span style={{ color: 'var(--muted)', fontSize: '0.85rem', minWidth: 55 }}>{acc.label}</span>
                <a href={acc.display && acc.display.startsWith('http') ? acc.display : '#'} target="_blank" rel="noopener"
                  style={{ fontSize: '0.85rem', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block' }}>
                  {acc.display}
                </a>
              </div>
              <button onClick={() => { setEditing(acc.key); acc.setInput(acc.display || ''); }} title="Edit"
                style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#818cf8', cursor: 'pointer', borderRadius: 8, width: 30, height: 30, display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.18s', flexShrink: 0 }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(99,102,241,0.22)'; e.currentTarget.style.borderColor = '#818cf8'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(99,102,241,0.1)'; e.currentTarget.style.borderColor = 'rgba(99,102,241,0.25)'; }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
              </button>
            </div>
          ) : (
            <div style={connectedStyle}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ color: '#475569', fontSize: '0.82rem' }}>&#9675;</span>
                <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>{acc.label}</span>
                <span style={{ color: '#475569', fontSize: '0.82rem' }}>Not connected</span>
              </div>
              <button onClick={() => setEditing(acc.key)} style={{ ...styles.btn, ...styles.btnSm, ...styles.btnPrimary, fontSize: '0.78rem' }}>Connect</button>
            </div>
          )}
        </div>
      ))}

      {(githubRateLimit || editingToken) && (
        <div style={{ marginTop: '0.75rem', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 10, padding: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
            <div>
              <p style={{ fontWeight: 700, fontSize: '0.88rem', color: '#fcd34d', marginBottom: '0.2rem' }}>
                {githubRateLimit ? '⚠ GitHub API Rate Limit Reached' : '🔑 GitHub Personal Access Token'}
              </p>
              <p style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>
                {githubRateLimit
                  ? 'Unauthenticated requests are limited to 60/hour. Provide a GitHub token to get 5,000/hour.'
                  : 'A stored token lets us import your full GitHub profile without hitting rate limits.'}
              </p>
            </div>
            <button onClick={() => { setGithubRateLimit(false); setEditingToken(false); }}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '1.2rem', padding: '0 0.2rem', lineHeight: 1 }}>×</button>
          </div>
          <ol style={{ color: 'var(--muted)', fontSize: '0.8rem', paddingLeft: '1.1rem', lineHeight: 1.9, marginBottom: '0.75rem' }}>
            <li>Click the button below to open GitHub → Settings → Personal Access Tokens</li>
            <li>Click <strong style={{ color: '#e2e8f0' }}>Generate new token</strong> (Fine-grained or Classic)</li>
            <li>Give it a name (e.g. <em>Kalibr</em>), set expiration, select scope: <strong style={{ color: '#e2e8f0' }}>read:user</strong> (or leave default for fine-grained)</li>
            <li>Copy the generated token and paste it below</li>
          </ol>
          <a href={GITHUB_TOKEN_URL} target="_blank" rel="noopener noreferrer"
            style={{ ...styles.btn, ...styles.btnSm, background: '#24292f', color: '#fff', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem', textDecoration: 'none', border: '1px solid #444' }}>
            🐙 Open GitHub → Create Token ↗
          </a>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <input
              type="password"
              style={{ ...styles.input, flex: 1, minWidth: 200, marginBottom: 0, fontFamily: 'monospace', fontSize: '0.82rem' }}
              value={editingToken && !githubTokenInput.startsWith('•') ? githubTokenInput : (githubTokenInput.startsWith('•') ? '' : githubTokenInput)}
              onChange={e => setGithubTokenInput(e.target.value)}
              placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              autoFocus={githubRateLimit}
            />
            <button
              disabled={loading === 'github' || !githubTokenInput.trim() || githubTokenInput.startsWith('•')}
              onClick={async () => {
                const token = githubTokenInput.trim();
                if (!token || token.startsWith('•')) return;
                setLoading('github');
                try {
                  const val = githubInput.trim() || (profile.github_username || profile.github || '');
                  const res = await api.post('/api/profile/connect/github', { username: val, token });
                  if (res.error) { showToast(res.error, 'error'); }
                  else {
                    setProfile(res.profile);
                    setGithubRateLimit(false);
                    setEditingToken(false);
                    setGithubTokenInput('••••••••');
                    setEditing(null);
                    const s = res.stats || {};
                    showToast(`✓ GitHub connected — ${s.public_repos || 0} repos, ${s.languages_added || 0} languages imported`, 'success');
                  }
                } catch { showToast('Connection failed', 'error'); }
                setLoading('');
              }}
              style={{ ...styles.btn, ...styles.btnSm, ...styles.btnSuccess, opacity: (!githubTokenInput.trim() || githubTokenInput.startsWith('•')) ? 0.45 : 1 }}>
              {loading === 'github' ? '⏳ Connecting…' : '✓ Save & Connect'}
            </button>
          </div>
          {profile.github_token && <p style={{ color: '#6ee7b7', fontSize: '0.75rem', marginTop: '0.4rem' }}>✓ Token already saved — clear the input and click Save to update it.</p>}
        </div>
      )}

      {!githubRateLimit && !editingToken && (
        <div style={{ textAlign: 'right', marginTop: '0.2rem', marginBottom: '0.2rem' }}>
          <button onClick={() => setEditingToken(true)}
            style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: '0.72rem', textDecoration: 'underline' }}>
            {profile.github_token ? '🔑 Update GitHub Token' : '🔑 Set GitHub Token (optional, avoids rate limits)'}
          </button>
        </div>
      )}

      {profile.projects && profile.projects.length > 0 && (() => {
        const visible = showAllProjects ? profile.projects : profile.projects.slice(0, 5);
        const hasMore = profile.projects.length > 5;
        return (
          <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
              <h3 style={{ fontSize: '0.85rem', color: 'var(--muted)', margin: 0 }}>
                GitHub Projects
                <span style={{ marginLeft: '0.5rem', background: 'rgba(99,102,241,0.15)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.3)', borderRadius: 20, padding: '0.05rem 0.5rem', fontSize: '0.7rem', fontWeight: 700 }}>
                  {profile.projects.length}
                </span>
              </h3>
              {hasMore && (
                <button onClick={() => setShowAllProjects(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.3)', color: '#818cf8', borderRadius: 20, padding: '0.2rem 0.75rem', fontSize: '0.72rem', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'rgba(99,102,241,0.22)'; e.currentTarget.style.borderColor = '#818cf8'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'rgba(99,102,241,0.1)'; e.currentTarget.style.borderColor = 'rgba(99,102,241,0.3)'; }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                    style={{ transition: 'transform 0.25s', transform: showAllProjects ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                  {showAllProjects ? 'View Less' : `View More (${profile.projects.length - 5} more)`}
                </button>
              )}
            </div>
            {visible.map((p, i) => {
              const allLangs = (p.languages && p.languages.length > 0) ? p.languages : (p.language ? [p.language] : []);
              return (
                <div key={i} style={{ marginBottom: '0.65rem', padding: '0.55rem 0.7rem', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 8, transition: 'border-color 0.2s', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(99,102,241,0.4)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <a href={p.url} target="_blank" rel="noopener" style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--accent)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.3rem', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.name}
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.5, flexShrink: 0 }}><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>
                    </a>
                    {p.description && <p style={{ color: 'var(--muted)', fontSize: '0.79rem', margin: '0.25rem 0 0', lineHeight: 1.4 }}>{p.description}</p>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', justifyContent: 'center', gap: '0.25rem', flexShrink: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      {allLangs.map((lang, li) => <span key={li} style={tagStyle(lang)}>{lang}</span>)}
                      {(p.topics || []).slice(0, 2).map((t, ti) => <span key={ti} style={topicStyle}>{t}</span>)}
                      {p.stars > 0 && (
                        <span style={{ color: '#fbbf24', fontSize: '0.68rem', display: 'flex', alignItems: 'center', gap: '0.2rem', marginLeft: '0.1rem' }}>
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>
                          {p.stars}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })()}

      <div style={{ marginTop: '1.25rem', paddingTop: '1.25rem', borderTop: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <div>
            <h3 style={{ fontSize: '0.95rem', margin: 0 }}>
              <span style={{ marginRight: '0.4rem' }}>📧</span> Gmail — Auto-detect Interviews &amp; Offers
            </h3>
            <p style={{ color: 'var(--muted)', fontSize: '0.78rem', margin: '0.2rem 0 0' }}>
              Connects with <strong>read-only</strong> access. Scans for interview invitations and offer letters and automatically updates your job statuses.
            </p>
          </div>
          {gmailStatus?.connected && (
            <span style={{ background: 'rgba(5,150,105,0.15)', color: '#6ee7b7', border: '1px solid rgba(5,150,105,0.3)', padding: '0.2rem 0.65rem', borderRadius: 20, fontSize: '0.75rem', fontWeight: 600, flexShrink: 0 }}>✓ Connected</span>
          )}
        </div>

        {gmailStatus === null ? (
          <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>Checking…</p>
        ) : gmailStatus.connected ? (
          <div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center', marginBottom: '0.6rem' }}>
              <button onClick={gmailSync} disabled={gmailSyncing} style={{ ...styles.btn, ...styles.btnSuccess, fontSize: '0.85rem', padding: '0.45rem 1.1rem' }}>
                {gmailSyncing ? '⏳ Scanning Gmail…' : '🔄 Sync Now'}
              </button>
              <button onClick={gmailDisconnect} style={{ ...styles.btn, background: 'rgba(220,38,38,0.1)', color: '#f87171', border: '1px solid rgba(220,38,38,0.3)', fontSize: '0.82rem', padding: '0.45rem 0.9rem' }}>
                Disconnect
              </button>
              {gmailStatus.last_sync && (
                <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Last sync: {fmtDate(gmailStatus.last_sync)}</span>
              )}
            </div>
            {gmailResult && (
              <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: '0.75rem 1rem', fontSize: '0.83rem' }}>
                <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap', marginBottom: gmailResult.updates?.length ? '0.6rem' : 0 }}>
                  <span>📬 <strong>{gmailResult.scanned}</strong> emails scanned</span>
                  <span style={{ color: '#d8b4fe' }}>📅 <strong>{gmailResult.interview}</strong> interview{gmailResult.interview !== 1 ? 's' : ''} found</span>
                  <span style={{ color: '#fde68a' }}>💰 <strong>{gmailResult.offer}</strong> offer{gmailResult.offer !== 1 ? 's' : ''} found</span>
                </div>
                {gmailResult.updates?.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '0.4rem' }}>
                    {gmailResult.updates.map((u, i) => {
                      const isOffer = u.status === 'offer';
                      const accent = isOffer
                        ? { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)', tag: 'rgba(245,158,11,0.2)', tagText: '#fde68a' }
                        : { bg: 'rgba(124,58,237,0.1)', border: 'rgba(124,58,237,0.3)', tag: 'rgba(124,58,237,0.2)', tagText: '#d8b4fe' };
                      const ext = u.extracted || {};
                      return (
                        <div key={i} style={{ background: accent.bg, border: `1px solid ${accent.border}`, borderRadius: 8, padding: '0.6rem 0.85rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: Object.keys(ext).length ? '0.4rem' : 0 }}>
                            <span style={{ background: accent.tag, color: accent.tagText, padding: '0.1rem 0.45rem', borderRadius: 6, fontWeight: 700, fontSize: '0.72rem', textTransform: 'capitalize', flexShrink: 0 }}>{u.status}</span>
                            <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{u.company}</span>
                            <span style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>— {u.job_title}</span>
                          </div>
                          {Object.keys(ext).length > 0 && (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem 1rem', fontSize: '0.78rem', color: 'var(--text2)' }}>
                              {ext.date && <span>📅 <strong>Date:</strong> {ext.date}{ext.time ? ` at ${ext.time}` : ''}{ext.timezone ? ` ${ext.timezone}` : ''}</span>}
                              {ext.round && <span>🎯 <strong>Round:</strong> {ext.round}</span>}
                              {ext.platform && <span>💻 <strong>Platform:</strong> {ext.platform}</span>}
                              {ext.interviewer && <span>👤 <strong>Interviewer:</strong> {ext.interviewer}</span>}
                              {ext.meeting_link && <a href={ext.meeting_link} target="_blank" rel="noopener" style={{ color: accent.tagText }}>🔗 Join Meeting</a>}
                              {ext.salary && <span>💰 <strong>Salary:</strong> {ext.salary}{ext.currency ? ` ${ext.currency}` : ''}</span>}
                              {ext.joining_date && <span>🗓 <strong>Joining:</strong> {ext.joining_date}</span>}
                              {ext.deadline && <span>⏰ <strong>Deadline:</strong> {ext.deadline}</span>}
                              {ext.location && <span>📍 <strong>Location:</strong> {ext.location}</span>}
                              {ext.benefits && <span>🎁 <strong>Benefits:</strong> {ext.benefits}</span>}
                            </div>
                          )}
                          <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '0.3rem', marginBottom: 0 }}>📧 {u.email_subject}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div>
            <button onClick={connectGmail}
              style={{ ...styles.btn, background: 'linear-gradient(135deg,#4285f4,#34a853)', color: '#fff', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.88rem', padding: '0.5rem 1.2rem', border: 'none', cursor: 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M20 4H4C2.9 4 2 4.9 2 6v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 2-8 5-8-5h16zm0 12H4V8l8 5 8-5v10z" /></svg>
              Connect Gmail
            </button>
            <p style={{ color: 'var(--muted)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
              You'll be asked to grant <strong>read-only</strong> Gmail access. Kalibr never reads personal emails — only scans for subject lines containing "interview", "offer", or "congratulations".
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

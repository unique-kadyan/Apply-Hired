'use client';
import { useState, useEffect } from 'react';
import api from '@/lib/api';
import styles from '@/lib/styles';
import { Badge, StatusBadge } from '@/components/shared/Badge';
import { fmtDate } from '@/components/Jobs/Jobs';

export default function JobDetail({ jobId, navigate, showToast }) {
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState('');
  const [interview, setInterview] = useState({ round: '', date: '', time: '', timezone: 'IST', interviewer: '', meeting_link: '', platform: '', notes: '' });
  const [offer, setOffer] = useState({ salary: '', currency: 'INR', joining_date: '', deadline: '', benefits: '', location: '', offer_text: '', notes: '' });
  const [savingInterview, setSavingInterview] = useState(false);
  const [savingOffer, setSavingOffer] = useState(false);
  const [autoApplying, setAutoApplying] = useState(false);

  useEffect(() => {
    api.get(`/api/jobs/${jobId}`).then(j => {
      setJob(j);
      setStatus(j.status);
      if (j.interview_details) setInterview(prev => ({ ...prev, ...j.interview_details }));
      if (j.offer_details) setOffer(prev => ({ ...prev, ...j.offer_details }));
    });
  }, [jobId]);

  if (!job) return <div style={styles.container}><p style={{ color: 'var(--muted)' }}>Loading...</p></div>;

  const updateStatus = async () => {
    await api.post(`/api/jobs/${job.id}/status`, { status });
    showToast(`Status updated to "${status}"`, 'success');
    setJob(j => ({ ...j, status }));
  };

  const saveInterview = async () => {
    setSavingInterview(true);
    try {
      const res = await api.post(`/api/jobs/${job.id}/interview`, interview);
      setJob(j => ({ ...j, status: 'interview', interview_details: res.interview_details }));
      setStatus('interview');
      showToast('Interview details saved!', 'success');
    } catch { showToast('Failed to save interview details', 'error'); }
    setSavingInterview(false);
  };

  const saveOffer = async () => {
    setSavingOffer(true);
    try {
      const res = await api.post(`/api/jobs/${job.id}/offer`, offer);
      setJob(j => ({ ...j, status: 'offer', offer_details: res.offer_details }));
      setStatus('offer');
      showToast('Offer details saved!', 'success');
    } catch { showToast('Failed to save offer details', 'error'); }
    setSavingOffer(false);
  };

  const iField = (label, key, type = 'text', placeholder = '') => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', flex: '1 1 180px' }}>
      <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
      <input type={type} value={interview[key]} placeholder={placeholder}
        onChange={e => setInterview(p => ({ ...p, [key]: e.target.value }))}
        style={{ ...styles.input, fontSize: '0.9rem', padding: '0.45rem 0.7rem' }} />
    </div>
  );

  const oField = (label, key, type = 'text', placeholder = '') => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', flex: '1 1 180px' }}>
      <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
      <input type={type} value={offer[key]} placeholder={placeholder}
        onChange={e => setOffer(p => ({ ...p, [key]: e.target.value }))}
        style={{ ...styles.input, fontSize: '0.9rem', padding: '0.45rem 0.7rem' }} />
    </div>
  );

  const genCoverLetter = async () => {
    showToast('Generating cover letter...', 'warning');
    const res = await api.post(`/api/jobs/${job.id}/cover-letter`);
    setJob(j => ({ ...j, cover_letter: res.cover_letter }));
    showToast('Cover letter generated!', 'success');
  };

  const copyLetter = () => {
    navigator.clipboard.writeText(job.cover_letter);
    showToast('Copied to clipboard!', 'success');
  };

  const autoApplySingle = async () => {
    if (!confirm(`Auto-apply to "${job.title}" at ${job.company}?\n\nThis will generate a cover letter, copy it to clipboard, and open the job page.`)) return;
    setAutoApplying(true);
    showToast('Generating cover letter...', 'warning');
    try {
      const res = await api.post('/api/auto-apply', { job_ids: [job.id] });
      const detail = res.details?.[0];
      if (detail?.cover_letter) {
        try { await navigator.clipboard.writeText(detail.cover_letter); } catch (e) {}
      }
      if (detail?.url) window.open(detail.url, '_blank');
      showToast('Job page opened! Cover letter copied to clipboard.', 'success');
      setJob(j => ({ ...j, status: 'applied' }));
      setStatus('applied');
    } catch (err) { showToast('Auto-apply failed', 'error'); }
    setAutoApplying(false);
  };

  return (
    <div style={styles.container}>
      <button onClick={() => navigate('jobs')} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '0.9rem', marginBottom: '1rem' }}>&larr; Back to Jobs</button>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.4rem', marginBottom: '0.3rem' }}>{job.title}</h1>
          <p style={{ color: '#60a5fa', fontSize: '1.05rem' }}>{job.company}</p>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem', marginTop: '0.2rem' }}>{[job.location, fmtDate(job.date_posted)].filter(Boolean).join(' · ')}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <Badge score={job.score} />
          <StatusBadge status={job.status} />
        </div>
      </div>

      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <button style={{ ...styles.btn, background: 'linear-gradient(135deg, #059669, #2563eb)', color: '#fff', padding: '0.6rem 1.5rem', fontSize: '0.95rem' }} onClick={autoApplySingle} disabled={autoApplying || job.status === 'applied'}>
          {autoApplying ? 'Applying...' : job.status === 'applied' ? 'Applied' : 'Auto-Apply'}
        </button>
        <a href={job.url} target="_blank" rel="noopener" style={{ ...styles.btn, ...styles.btnPrimary }}>Open Job Posting &rarr;</a>
        <button style={{ ...styles.btn, ...styles.btnSuccess }} onClick={genCoverLetter}>{job.cover_letter ? 'Regenerate' : 'Generate'} Cover Letter</button>
        {job.salary && <span style={{ ...styles.btn, ...styles.btnSecondary, cursor: 'default' }}>Salary: {job.salary}</span>}
      </div>

      <div style={styles.card}>
        <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Update Status</h2>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <select style={styles.select} value={status} onChange={e => setStatus(e.target.value)}>
            {['new', 'previous', 'saved', 'applied', 'interview', 'rejected', 'offer'].map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
          <button style={{ ...styles.btn, ...styles.btnPrimary, ...styles.btnSm }} onClick={updateStatus}>Update</button>
        </div>
        <p style={{ fontSize: '0.8rem', color: 'var(--muted)', marginTop: '0.6rem' }}>
          Set to <strong>Interview</strong> or <strong>Offer</strong> to unlock detailed tracking below.
        </p>
      </div>

      {(status === 'interview' || job.status === 'interview' || job.interview_details) && (
        <div style={{ ...styles.card, borderLeft: '3px solid #7c3aed' }}>
          <h2 style={{ fontSize: '1rem', marginBottom: '1rem', color: '#d8b4fe' }}>Interview Details</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
            {iField('Round', 'round', 'text', 'e.g. Technical Round 1')}
            {iField('Date', 'date', 'date')}
            {iField('Time', 'time', 'time')}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', flex: '1 1 120px' }}>
              <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Timezone</label>
              <select value={interview.timezone} onChange={e => setInterview(p => ({ ...p, timezone: e.target.value }))} style={{ ...styles.select, fontSize: '0.9rem', padding: '0.45rem 0.7rem' }}>
                {['IST', 'UTC', 'UTC+5:30', 'EST', 'PST', 'CST', 'MST', 'GMT', 'CET', 'AEST'].map(tz => <option key={tz}>{tz}</option>)}
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
            {iField('Interviewer / Team', 'interviewer', 'text', 'e.g. Priya Sharma (Engineering)')}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', flex: '1 1 140px' }}>
              <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Platform</label>
              <select value={interview.platform} onChange={e => setInterview(p => ({ ...p, platform: e.target.value }))} style={{ ...styles.select, fontSize: '0.9rem', padding: '0.45rem 0.7rem' }}>
                {['', 'Google Meet', 'Zoom', 'Microsoft Teams', 'Webex', 'Phone Call', 'In Person', 'Other'].map(pl => <option key={pl} value={pl}>{pl || '— Select platform —'}</option>)}
              </select>
            </div>
            {iField('Meeting Link', 'meeting_link', 'url', 'https://meet.google.com/...')}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Notes</label>
            <textarea rows={2} value={interview.notes} placeholder="Preparation notes, topics to review..."
              onChange={e => setInterview(p => ({ ...p, notes: e.target.value }))}
              style={{ ...styles.input, resize: 'vertical', fontSize: '0.9rem', padding: '0.5rem 0.7rem', fontFamily: 'inherit' }} />
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <button style={{ ...styles.btn, background: '#7c3aed', color: '#fff', padding: '0.5rem 1.4rem' }} onClick={saveInterview} disabled={savingInterview}>
              {savingInterview ? 'Saving...' : 'Save Interview Details'}
            </button>
            {interview.meeting_link && <a href={interview.meeting_link} target="_blank" rel="noopener" style={{ ...styles.btn, ...styles.btnSm, background: '#1e3a5f', color: '#93c5fd' }}>Join Meeting &rarr;</a>}
          </div>
          {job.interview_details?.saved_at && <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginTop: '0.5rem' }}>Last saved: {fmtDate(job.interview_details.saved_at)}</p>}
        </div>
      )}

      {(status === 'offer' || job.status === 'offer' || job.offer_details) && (
        <div style={{ ...styles.card, borderLeft: '3px solid #f59e0b' }}>
          <h2 style={{ fontSize: '1rem', marginBottom: '1rem', color: '#fde68a' }}>Offer Details</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
            {oField('Salary / CTC', 'salary', 'text', 'e.g. ₹25 LPA or $120,000')}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', flex: '1 1 100px' }}>
              <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Currency</label>
              <select value={offer.currency} onChange={e => setOffer(p => ({ ...p, currency: e.target.value }))} style={{ ...styles.select, fontSize: '0.9rem', padding: '0.45rem 0.7rem' }}>
                {['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD'].map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            {oField('Joining Date', 'joining_date', 'date')}
            {oField('Acceptance Deadline', 'deadline', 'date')}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
            {oField('Benefits', 'benefits', 'text', 'Health, ESOPs, bonus, WFH...')}
            {oField('Work Location', 'location', 'text', 'e.g. Remote / Bengaluru')}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', marginBottom: '0.75rem' }}>
            <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Offer Letter Text <span style={{ textTransform: 'none', color: '#64748b' }}>(paste key details)</span></label>
            <textarea rows={4} value={offer.offer_text} placeholder="Paste relevant sections from your offer letter here..."
              onChange={e => setOffer(p => ({ ...p, offer_text: e.target.value }))}
              style={{ ...styles.input, resize: 'vertical', fontSize: '0.9rem', padding: '0.5rem 0.7rem', fontFamily: 'inherit' }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Notes</label>
            <textarea rows={2} value={offer.notes} placeholder="Negotiation notes, questions, decisions..."
              onChange={e => setOffer(p => ({ ...p, notes: e.target.value }))}
              style={{ ...styles.input, resize: 'vertical', fontSize: '0.9rem', padding: '0.5rem 0.7rem', fontFamily: 'inherit' }} />
          </div>
          <button style={{ ...styles.btn, background: '#b45309', color: '#fff', padding: '0.5rem 1.4rem' }} onClick={saveOffer} disabled={savingOffer}>
            {savingOffer ? 'Saving...' : 'Save Offer Details'}
          </button>
          {job.offer_details?.saved_at && <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginTop: '0.5rem' }}>Last saved: {fmtDate(job.offer_details.saved_at)}</p>}
        </div>
      )}

      {job.score_details && (
        <div style={styles.card}>
          <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Match Analysis</h2>
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
            <div><span style={{ color: 'var(--muted)' }}>Local: </span><strong>{Math.round((job.score_details.local_score || 0) * 100)}%</strong></div>
            {job.score_details.ai_score != null && <div><span style={{ color: 'var(--muted)' }}>AI: </span><strong>{Math.round(job.score_details.ai_score * 100)}%</strong></div>}
          </div>
          {job.score_details.ai_reasons && job.score_details.ai_reasons.length > 0 && (
            <ul style={{ paddingLeft: '1.5rem', lineHeight: 1.8, color: 'var(--text2)' }}>
              {job.score_details.ai_reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
        </div>
      )}

      {job.tags && job.tags.length > 0 && (
        <div style={styles.card}>
          <h2 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Tags</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {job.tags.map((t, i) => <span key={i} style={{ background: '#1e3a5f', color: '#93c5fd', padding: '0.25rem 0.7rem', borderRadius: 20, fontSize: '0.82rem' }}>{t}</span>)}
          </div>
        </div>
      )}

      {job.description && (
        <div style={styles.card}>
          <h2 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Description</h2>
          <div style={{ lineHeight: 1.8, color: '#cbd5e1', fontSize: '0.92rem' }}>{job.description.substring(0, 2000)}</div>
        </div>
      )}

      {job.cover_letter && (
        <div style={styles.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h2 style={{ fontSize: '1rem', margin: 0 }}>Cover Letter</h2>
            <button style={{ ...styles.btn, ...styles.btnSm, ...styles.btnSecondary }} onClick={copyLetter}>Copy</button>
          </div>
          <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: '1.5rem', whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: '0.93rem' }}>{job.cover_letter}</div>
        </div>
      )}
    </div>
  );
}

'use client';
import { useState, useEffect } from 'react';
import api from '@/lib/api';
import styles from '@/lib/styles';

export default function ResumeOptimizer({ profile, setProfile, showToast }) {
  const [loading, setLoading] = useState(false);
  const [optimized, setOptimized] = useState(profile.optimized_resume || null);
  const [hasPaid, setHasPaid] = useState(false);
  const [targetRole, setTargetRole] = useState(profile.title || '');
  const [targetCompany, setTargetCompany] = useState('');
  const [jobDesc, setJobDesc] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [priceLabel, setPriceLabel] = useState('');

  useEffect(() => {
    api.get('/api/payment/has-paid').then(r => setHasPaid(r.paid));
    api.get('/api/payment/config').then(r => setPriceLabel(r.display_amount || ''));
    if (profile.optimized_resume) setOptimized(profile.optimized_resume);
  }, [profile]);

  const startPayment = async () => {
    try {
      const config = await api.get('/api/payment/config');
      if (!config.configured) { showToast('Payment gateway not configured', 'error'); return; }
      const order = await api.post('/api/payment/create-order', {});
      if (order.error) { showToast(order.error, 'error'); return; }
      const options = {
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: 'JobBot',
        description: 'ATS Resume Optimization',
        order_id: order.order_id,
        handler: async (response) => {
          const verify = await api.post('/api/payment/verify', {
            order_id: response.razorpay_order_id,
            payment_id: response.razorpay_payment_id,
            signature: response.razorpay_signature,
          });
          if (verify.paid) {
            setHasPaid(true);
            showToast('Payment successful! Now customize and optimize.', 'success');
            setShowForm(true);
          } else {
            showToast('Payment verification failed', 'error');
          }
        },
        prefill: { name: profile.name, email: profile.email, contact: profile.phone },
        theme: { color: '#2563eb' },
      };
      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      showToast('Payment failed. Please try again.', 'error');
    }
  };

  const runOptimization = async () => {
    setLoading(true);
    showToast('Optimizing your resume with AI... This may take 15-20 seconds.', 'warning');
    try {
      const res = await api.post('/api/payment/optimize-resume', {
        target_role: targetRole, target_company: targetCompany, job_description: jobDesc,
      });
      if (res.error) { showToast(res.error, 'error'); }
      else {
        setOptimized(res.optimized);
        if (res.profile) setProfile(res.profile);
        showToast('Resume optimized!', 'success');
        setShowForm(false);
      }
    } catch (err) { showToast('Optimization failed', 'error'); }
    setLoading(false);
  };

  if (optimized && !showForm) {
    return (
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: '1.5rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h2 style={{ fontSize: '1.1rem', margin: 0, color: 'var(--green2)' }}>ATS-Optimized Resume</h2>
          {profile.optimized_for && (
            <span style={{ color: 'var(--muted)', fontSize: '0.78rem' }}>
              Tailored for: {profile.optimized_for.role}{profile.optimized_for.company ? ` at ${profile.optimized_for.company}` : ''}
            </span>
          )}
        </div>
        <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '0.4rem' }}>Professional Summary</h3>
          <p style={{ color: '#cbd5e1', lineHeight: 1.7, margin: 0 }}>{optimized.summary}</p>
        </div>
        {(optimized.experience || []).map((exp, i) => (
          <div key={i} style={{ marginBottom: '1rem', paddingBottom: '1rem', borderBottom: i < optimized.experience.length - 1 ? '1px solid var(--border)' : 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <strong style={{ color: 'var(--text)' }}>{exp.title}</strong>
              <span style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{exp.period}</span>
            </div>
            <p style={{ color: '#60a5fa', fontSize: '0.88rem', marginBottom: '0.3rem' }}>{exp.company}</p>
            <ul style={{ paddingLeft: '1.25rem', margin: 0, lineHeight: 1.8, color: '#cbd5e1', fontSize: '0.88rem' }}>
              {(exp.highlights || []).map((h, j) => <li key={j}>{h}</li>)}
            </ul>
          </div>
        ))}
        {optimized.ats_keywords && optimized.ats_keywords.length > 0 && (
          <div style={{ marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '0.4rem' }}>ATS Keywords Used</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
              {optimized.ats_keywords.map((kw, i) => (
                <span key={i} style={{ background: '#065f46', color: '#6ee7b7', padding: '0.2rem 0.6rem', borderRadius: 20, fontSize: '0.78rem' }}>{kw}</span>
              ))}
            </div>
          </div>
        )}
        {optimized.optimization_notes && optimized.optimization_notes.length > 0 && (
          <div style={{ background: 'rgba(37,99,235,0.08)', border: '1px solid rgba(37,99,235,0.2)', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '0.85rem', color: 'var(--accent2)', margin: '0 0 0.4rem' }}>What We Improved</h3>
            <ul style={{ paddingLeft: '1.25rem', margin: 0, lineHeight: 1.7, color: '#cbd5e1', fontSize: '0.85rem' }}>
              {optimized.optimization_notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          </div>
        )}
        <button onClick={() => { setShowForm(true); setOptimized(null); setHasPaid(false); }}
          style={{ ...styles.btn, ...styles.btnSecondary, fontSize: '0.85rem' }}>
          Re-optimize for a Different Role
        </button>
      </div>
    );
  }

  if (hasPaid && (showForm || !optimized)) {
    return (
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: '1.5rem', marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.3rem' }}>Optimize Your Resume</h2>
        <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>Tailor your resume for a specific role. Our AI will rewrite it for maximum ATS compatibility.</p>
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.3rem', fontSize: '0.85rem' }}>Target Role</label>
          <input style={styles.input} value={targetRole} onChange={e => setTargetRole(e.target.value)} placeholder="e.g. Senior Backend Engineer" />
        </div>
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.3rem', fontSize: '0.85rem' }}>Target Company (optional)</label>
          <input style={styles.input} value={targetCompany} onChange={e => setTargetCompany(e.target.value)} placeholder="e.g. Google, Razorpay" />
        </div>
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.3rem', fontSize: '0.85rem' }}>Paste Job Description (optional — improves keyword matching)</label>
          <textarea style={{ ...styles.input, minHeight: 120, resize: 'vertical' }} value={jobDesc} onChange={e => setJobDesc(e.target.value)}
            placeholder="Paste the full job description here for best results..." />
        </div>
        <button onClick={runOptimization} disabled={loading || !targetRole}
          style={{ ...styles.btn, ...styles.btnPrimary, padding: '0.7rem 2rem', fontSize: '0.95rem', opacity: !targetRole ? 0.5 : 1 }}>
          {loading ? 'Optimizing...' : 'Optimize Resume'}
        </button>
      </div>
    );
  }

  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(37,99,235,0.1), rgba(124,58,237,0.1))',
      border: '1px solid rgba(37,99,235,0.3)', borderRadius: 14, padding: '1.5rem', marginBottom: '1rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 250 }}>
          <h2 style={{ fontSize: '1.1rem', margin: '0 0 0.3rem', color: 'var(--text)' }}>Fix &amp; Optimize Your Resume</h2>
          <p style={{ color: 'var(--muted)', fontSize: '0.88rem', lineHeight: 1.6, marginBottom: '1rem' }}>
            Get an AI-rewritten, ATS-optimized resume tailored for your target role. Includes:
          </p>
          <ul style={{ paddingLeft: '1.25rem', margin: '0 0 1.25rem', lineHeight: 1.9, color: '#cbd5e1', fontSize: '0.88rem' }}>
            <li>ATS-friendly formatting and keywords</li>
            <li>Quantified achievements with strong action verbs</li>
            <li>Tailored to specific role and job description</li>
            <li>Professional summary rewrite</li>
            <li>Keyword optimization for recruiter search</li>
          </ul>
          <button onClick={startPayment}
            style={{
              ...styles.btn, background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
              color: '#fff', padding: '0.75rem 2rem', fontSize: '1rem', fontWeight: 700,
              boxShadow: '0 4px 15px rgba(37,99,235,0.3)',
            }}>
            {priceLabel ? `Optimize for ${priceLabel}` : 'Optimize Resume'}
          </button>
          <p style={{ color: '#64748b', fontSize: '0.75rem', marginTop: '0.5rem' }}>Per-optimization payment. Secure checkout via Razorpay.</p>
        </div>
      </div>
    </div>
  );
}

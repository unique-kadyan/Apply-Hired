'use client';
import { useState, useRef } from 'react';
import api from '@/lib/api';
import styles from '@/lib/styles';
import ResumeScoreCard from '@/components/Profile/ResumeScoreCard';
import ResumeOptimizer from '@/components/Profile/ResumeOptimizer';

export default function ResumePage({ profile, setProfile, showToast }) {
  const fileRef = useRef(null);
  const [scoring, setScoring] = useState(false);
  const [scoreResult, setScoreResult] = useState(null);

  const scoreResume = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setScoring(true);
    setScoreResult(null);
    const fd = new FormData();
    fd.append('resume', file);
    try {
      const res = await api.upload('/api/profile/score-resume', fd);
      if (res.error) { showToast(res.error, 'error'); }
      else { setScoreResult(res); showToast('Resume scored!', 'success'); }
    } catch { showToast('Scoring failed', 'error'); }
    setScoring(false);
    e.target.value = '';
  };

  const displayScore = scoreResult || profile.resume_score;

  return (
    <div style={styles.container}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.4rem', margin: '0 0 0.25rem' }}>Resume</h1>
        <p style={{ color: 'var(--muted)', fontSize: '0.88rem', margin: 0 }}>
          Check your resume score for free, then optimize it with AI for any target role.
        </p>
      </div>

      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: '1.5rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: displayScore ? '1.25rem' : 0 }}>
          <div>
            <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.25rem' }}>Resume Score Check</h2>
            <p style={{ color: 'var(--muted)', fontSize: '0.85rem', margin: 0 }}>
              Free — upload your resume to get an ATS compatibility score.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ background: '#065f46', color: '#6ee7b7', padding: '0.2rem 0.75rem', borderRadius: 20, fontSize: '0.75rem', fontWeight: 600 }}>FREE</span>
            <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" style={{ display: 'none' }} onChange={scoreResume} />
            <button onClick={() => fileRef.current?.click()} disabled={scoring}
              style={{ ...styles.btn, ...styles.btnSecondary, fontSize: '0.85rem', opacity: scoring ? 0.6 : 1 }}>
              {scoring ? 'Scoring...' : displayScore ? 'Re-check Score' : 'Check Score'}
            </button>
          </div>
        </div>
        {displayScore && <ResumeScoreCard score={displayScore} />}
        {!displayScore && (
          <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginTop: '0.75rem' }}>
            Upload a PDF, DOCX, or TXT resume to see your ATS score breakdown.
          </p>
        )}
      </div>

      <div style={{ marginBottom: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <h2 style={{ fontSize: '1.05rem', margin: 0 }}>AI Resume Optimization</h2>
          <span style={{ background: 'rgba(37,99,235,0.15)', color: '#93c5fd', padding: '0.2rem 0.75rem', borderRadius: 20, fontSize: '0.75rem', fontWeight: 600 }}>PAID</span>
        </div>
        <ResumeOptimizer profile={profile} setProfile={setProfile} showToast={showToast} />
      </div>
    </div>
  );
}

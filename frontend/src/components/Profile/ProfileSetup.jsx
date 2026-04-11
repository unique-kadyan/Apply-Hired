'use client';
import { useState, useRef } from 'react';
import api from '@/lib/api';
import styles from '@/lib/styles';
import ResumeScoreCard from './ResumeScoreCard';
import ResumeOptimizer from './ResumeOptimizer';

export default function ProfileSetup({ profile, setProfile, showToast, onComplete }) {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [step, setStep] = useState(1);

  const uploadResume = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append('resume', file);
    try {
      const res = await api.upload('/api/profile/upload-resume', fd);
      if (res.error) { showToast(res.error, 'error'); }
      else {
        setProfile(res.profile);
        showToast('Resume parsed successfully!', 'success');
        setStep(2);
      }
    } catch (err) { showToast('Upload failed', 'error'); }
    setUploading(false);
  };

  const cardStyle = { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 16, padding: '2rem' };

  if (step === 2) {
    return (
      <div style={{ maxWidth: 700, margin: '0 auto', padding: '2rem', animation: 'fadeIn 0.3s ease' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '0.3rem' }}>Review Your Profile</h1>
          <p style={{ color: 'var(--muted)' }}>We parsed your resume. Review below and continue.</p>
        </div>

        <div style={cardStyle}>
          <h2 style={{ margin: '0 0 0.2rem' }}>{profile.name}</h2>
          <p style={{ color: '#60a5fa', marginBottom: '0.3rem' }}>{profile.title}</p>
          <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginBottom: '1rem' }}>
            {profile.location} | {profile.years_of_experience} yrs | {profile.email}
          </p>
          <p style={{ color: '#cbd5e1', lineHeight: 1.7, marginBottom: '1.5rem' }}>{profile.summary}</p>

          {profile.skills && Object.keys(profile.skills).length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '0.5rem' }}>Skills</h3>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                {Object.values(profile.skills).flat().map((s, i) => (
                  <span key={i} style={{ background: '#1e3a5f', color: '#93c5fd', padding: '0.25rem 0.7rem', borderRadius: 20, fontSize: '0.82rem' }}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {(profile.experience || []).length > 0 && (
            <div>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '0.5rem' }}>Experience ({profile.experience.length} roles)</h3>
              {profile.experience.map((exp, i) => (
                <div key={i} style={{ marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: i < profile.experience.length - 1 ? '1px solid var(--border)' : 'none' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                    <strong style={{ color: 'var(--text)' }}>{exp.title}</strong>
                    <span style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{exp.period}</span>
                  </div>
                  <p style={{ color: '#60a5fa', fontSize: '0.88rem' }}>{exp.company}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {profile.resume_score && <ResumeScoreCard score={profile.resume_score} />}

        {profile.resume_score && profile.resume_score.total_score < 100 && (
          <ResumeOptimizer profile={profile} setProfile={setProfile} showToast={showToast} />
        )}

        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem', justifyContent: 'center' }}>
          <button onClick={() => setStep(1)} style={{ ...styles.btn, ...styles.btnSecondary }}>Re-upload Resume</button>
          <button onClick={onComplete} style={{ ...styles.btn, ...styles.btnPrimary, padding: '0.7rem 2rem', fontSize: '1rem' }}>
            Continue to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 520, margin: '0 auto', padding: '2rem', animation: 'fadeIn 0.3s ease' }}>
      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>&#128196;</div>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.3rem' }}>Set Up Your Profile</h1>
        <p style={{ color: 'var(--muted)', lineHeight: 1.6 }}>
          Upload your resume to get started. We&apos;ll parse your skills,<br />experience, and education automatically.
        </p>
      </div>

      <div style={{ ...cardStyle, textAlign: 'center' }}>
        <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" onChange={uploadResume} style={{ display: 'none' }} />
        <div style={{
          border: '2px dashed #475569', borderRadius: 14, padding: '3rem 2rem',
          cursor: 'pointer', transition: 'all 0.2s', marginBottom: '1rem',
        }} onClick={() => !uploading && fileRef.current.click()}>
          {uploading ? (
            <div>
              <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: 'var(--accent2)' }}>Parsing...</div>
              <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>Analyzing your resume with AI</p>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>&#128195;</div>
              <p style={{ color: 'var(--text2)', fontWeight: 600, fontSize: '1rem', marginBottom: '0.3rem' }}>
                Click to upload your resume
              </p>
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>PDF, DOCX, or TXT</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

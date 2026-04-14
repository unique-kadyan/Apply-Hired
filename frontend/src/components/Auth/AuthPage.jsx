'use client';
import { useState, useEffect } from 'react';
import api from '@/lib/api';
import styles from '@/lib/styles';
import Logo from '@/components/shared/Logo';

export default function AuthPage({ onAuth, showToast }) {
  const [mode, setMode] = useState('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [showGoogleBanner, setShowGoogleBanner] = useState(false);
  const [resetToken, setResetToken] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('reset_token');
    if (token) {
      setResetToken(token);
      setMode('reset');
      window.history.replaceState({}, '', '/');
    }
  }, []);

  const googleLogin = () => { window.location.href = '/api/auth/google'; };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    if (!email) { showToast('Enter your email address', 'error'); return; }
    setLoading(true);
    try {
      const res = await api.post('/api/auth/forgot-password', { email });
      showToast(res.message || 'Reset link sent to your email', 'success');
      setMode('login');
    } catch (err) { showToast('Something went wrong', 'error'); }
    setLoading(false);
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (!password || password.length < 6) { showToast('Password must be at least 6 characters', 'error'); return; }
    setLoading(true);
    try {
      const res = await api.post('/api/auth/reset-password', { token: resetToken, password });
      if (res.error) { showToast(res.error, 'error'); }
      else { showToast(res.message || 'Password reset! You can now sign in.', 'success'); setMode('login'); setResetToken(''); }
    } catch (err) { showToast('Something went wrong', 'error'); }
    setLoading(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setShowGoogleBanner(false);
    try {
      if (otpSent) {
        const res = await api.post('/api/auth/verify-otp', { email, otp });
        if (res.error) showToast(res.error, 'error');
        else if (res.user) onAuth(res.user, true);
      } else if (mode === 'signup') {
        const res = await api.post('/api/auth/signup', { name, email, password });
        if (res.error) {
          showToast(res.error, 'error');
          if (res.use_google) setShowGoogleBanner(true);
        }
        else if (res.needs_otp) { setOtpSent(true); showToast('Verification code sent to your email!', 'success'); }
        else if (res.user) onAuth(res.user, true);
      } else {
        const res = await api.post('/api/auth/login', { email, password });
        if (res.error) showToast(res.error, 'error');
        else if (res.user) onAuth(res.user, false);
      }
    } catch (err) { showToast('Something went wrong. Please try again.', 'error'); }
    setLoading(false);
  };

  const labelStyle = { display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.3rem', fontSize: '0.85rem' };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 16, padding: '2.5rem', width: '100%', maxWidth: 420, animation: 'fadeIn 0.4s ease' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.5rem' }}>
            <Logo size={48} />
          </div>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
            {mode === 'reset' ? 'Set your new password' : mode === 'forgot' ? 'Enter your email to receive a reset link' : otpSent ? `Enter the code sent to ${email}` : mode === 'login' ? 'Welcome back! Sign in to continue.' : 'Create your account to get started.'}
          </p>
        </div>

        {mode === 'reset' ? (
          <form onSubmit={handleResetPassword}>
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={labelStyle}>New Password</label>
              <input style={styles.input} type="password" value={password} onChange={e => setPassword(e.target.value)}
                     placeholder="Min 6 characters" required minLength={6} autoFocus />
            </div>
            <button type="submit" disabled={loading} style={{
              ...styles.btn, ...styles.btnPrimary, width: '100%', padding: '0.7rem', fontSize: '0.95rem', justifyContent: 'center',
            }}>
              {loading ? 'Resetting...' : 'Reset Password'}
            </button>
            <button type="button" onClick={() => { setMode('login'); setResetToken(''); }}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '0.85rem', marginTop: '1rem', width: '100%', textAlign: 'center' }}>
              Back to Sign In
            </button>
          </form>

        ) : mode === 'forgot' ? (
          <form onSubmit={handleForgotPassword}>
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={labelStyle}>Email</label>
              <input style={styles.input} type="email" value={email} onChange={e => setEmail(e.target.value)}
                     placeholder="you@example.com" required autoFocus />
            </div>
            <button type="submit" disabled={loading} style={{
              ...styles.btn, ...styles.btnPrimary, width: '100%', padding: '0.7rem', fontSize: '0.95rem', justifyContent: 'center',
            }}>
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>
            <button type="button" onClick={() => setMode('login')}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '0.85rem', marginTop: '1rem', width: '100%', textAlign: 'center' }}>
              Back to Sign In
            </button>
          </form>

        ) : otpSent ? (
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={labelStyle}>Verification Code</label>
              <input style={{ ...styles.input, textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.3em', fontWeight: 700 }}
                     value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                     placeholder="000000" required maxLength={6} autoFocus />
            </div>
            <button type="submit" disabled={loading || otp.length !== 6} style={{
              ...styles.btn, ...styles.btnPrimary, width: '100%', padding: '0.7rem', fontSize: '0.95rem',
              justifyContent: 'center', opacity: otp.length !== 6 ? 0.5 : 1,
            }}>
              {loading ? 'Verifying...' : 'Verify & Create Account'}
            </button>
            <button type="button" onClick={() => { setOtpSent(false); setOtp(''); }}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '0.85rem', marginTop: '0.75rem', width: '100%', textAlign: 'center' }}>
              Back
            </button>
          </form>
        ) : (
          <>
            <button onClick={googleLogin} style={{
              width: '100%', padding: '0.85rem', borderRadius: 10, border: '1px solid #475569',
              background: '#fff', color: '#1f2937', fontSize: '1rem', fontWeight: 600,
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: '0.7rem', transition: 'all 0.15s', marginBottom: '1.5rem',
            }}>
              <svg width="20" height="20" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59A14.5 14.5 0 019.5 24c0-1.59.28-3.13.76-4.59l-7.98-6.19A23.9 23.9 0 000 24c0 3.77.9 7.35 2.56 10.52l7.97-5.93z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 5.93C6.51 42.62 14.62 48 24 48z"/></svg>
              Continue with Google
            </button>

            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }}></div>
              <span style={{ color: '#64748b', fontSize: '0.8rem' }}>or</span>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }}></div>
            </div>

            <form onSubmit={handleSubmit}>
              {mode === 'signup' && (
                <div style={{ marginBottom: '1rem' }}>
                  <label style={labelStyle}>Full Name</label>
                  <input style={styles.input} value={name} onChange={e => setName(e.target.value)} placeholder="Your name" required />
                </div>
              )}
              <div style={{ marginBottom: '1rem' }}>
                <label style={labelStyle}>Email</label>
                <input style={styles.input} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
              </div>
              <div style={{ marginBottom: '1.5rem' }}>
                <label style={labelStyle}>Password</label>
                <input style={styles.input} type="password" value={password} onChange={e => setPassword(e.target.value)}
                       placeholder={mode === 'signup' ? 'Min 6 characters' : 'Your password'} required minLength={mode === 'signup' ? 6 : 1} />
                {mode === 'login' && (
                  <button type="button" onClick={() => setMode('forgot')}
                    style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', fontSize: '0.82rem', float: 'right', marginTop: '0.3rem' }}>
                    Forgot password?
                  </button>
                )}
              </div>
              <button type="submit" disabled={loading} style={{
                ...styles.btn, ...styles.btnPrimary, width: '100%', padding: '0.7rem', fontSize: '0.95rem', justifyContent: 'center',
              }}>
                {loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Account'}
              </button>
            </form>

            {showGoogleBanner && (
              <div style={{ background: 'rgba(37,99,235,0.1)', border: '1px solid rgba(37,99,235,0.3)', borderRadius: 10, padding: '1rem', marginTop: '1rem', textAlign: 'center' }}>
                <p style={{ color: 'var(--text2)', fontSize: '0.88rem', margin: '0 0 0.75rem', lineHeight: 1.5 }}>
                  Email verification is temporarily unavailable. Sign in with Google instead:
                </p>
                <button onClick={googleLogin} style={{
                  width: '100%', padding: '0.7rem', borderRadius: 8, border: '1px solid #475569',
                  background: '#fff', color: '#1f2937', fontSize: '0.9rem', fontWeight: 600,
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.6rem',
                }}>
                  <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59A14.5 14.5 0 019.5 24c0-1.59.28-3.13.76-4.59l-7.98-6.19A23.9 23.9 0 000 24c0 3.77.9 7.35 2.56 10.52l7.97-5.93z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 5.93C6.51 42.62 14.62 48 24 48z"/></svg>
                  Continue with Google
                </button>
              </div>
            )}

            <p style={{ textAlign: 'center', marginTop: '1.25rem', color: 'var(--muted)', fontSize: '0.88rem' }}>
              {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
              <button onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
                style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', fontWeight: 600, fontSize: '0.88rem' }}>
                {mode === 'login' ? 'Sign Up' : 'Sign In'}
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  );
}

'use client';
import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import styles from '@/lib/styles';
import Toast from '@/components/shared/Toast';
import AuthPage from '@/components/Auth/AuthPage';
import WelcomeOverlay from '@/components/WelcomeOverlay';
import Dashboard from '@/components/Dashboard/Dashboard';
import Jobs from '@/components/Jobs/Jobs';
import JobDetail from '@/components/Jobs/JobDetail';
import Search from '@/components/Search/Search';
import Profile from '@/components/Profile/Profile';
import ProfileSetup from '@/components/Profile/ProfileSetup';

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [page, setPage] = useState('dashboard');
  const [pageArg, setPageArg] = useState(null);
  const [profile, setProfile] = useState({});
  const [toast, setToast] = useState(null);

  const _loadCachedDash = () => {
    try { const c = sessionStorage.getItem('_dashData'); return c ? JSON.parse(c) : null; } catch { return null; }
  };
  const _saveCachedDash = (data) => {
    try { sessionStorage.setItem('_dashData', JSON.stringify(data)); } catch {}
  };
  const [dashData, setDashData] = useState(_loadCachedDash);

  const fetchDashData = useCallback(() => {
    Promise.all([
      api.get('/api/stats'),
      api.get('/api/jobs?tab=not_applied&per_page=5&sort_by=score&sort_dir=desc'),
      api.get('/api/jobs?tab=applied&per_page=5&sort_by=updated_at&sort_dir=desc'),
    ]).then(([stats, notApplied, applied]) => {
      if (!stats || stats.error) return;
      const apJobs = (applied && applied.jobs) || [];
      const data = {
        stats,
        recentNew: (notApplied && notApplied.jobs) || [],
        recentApplied: apJobs.filter(j => j.status === 'applied'),
        recentInterview: apJobs.filter(j => j.status === 'interview' || j.status === 'offer'),
      };
      setDashData(data);
      _saveCachedDash(data);
    }).catch(() => {});
  }, []);

  const [visited, setVisited] = useState({ dashboard: true });

  useEffect(() => {
    api.get('/api/auth/me').then(res => {
      if (res.user) {
        setUser(res.user);
        api.get('/api/profile').then(setProfile);
        fetchDashData();
      }
      setAuthChecked(true);
    }).catch(() => setAuthChecked(true));

    const params = new URLSearchParams(window.location.search);
    if (params.get('auth_success')) {
      window.history.replaceState({}, '', '/');
      api.get('/api/auth/me').then(res => {
        if (res.user) {
          setUser(res.user);
          api.get('/api/profile').then(setProfile);
          fetchDashData();
        }
        setAuthChecked(true);
      });
    }
    if (params.get('auth_error')) {
      setToast({ message: 'Google sign-in failed. Please try again.', type: 'error' });
      window.history.replaceState({}, '', '/');
    }
  }, []);

  const navigate = (p, arg = null) => {
    setVisited(prev => ({ ...prev, [p]: true }));
    setPage(p); setPageArg(arg);
    window.scrollTo(0, 0);
  };

  const showToast = (message, type = 'success') => setToast({ message, type });

  const [welcome, setWelcome] = useState(null);

  const handleAuth = (userData, isSignup = false) => {
    setUser(userData);
    api.get('/api/profile').then(setProfile);
    fetchDashData();
    setWelcome({ name: userData.name?.split(' ')[0] || userData.name, isSignup });
  };

  const handleLogout = async () => {
    await api.post('/api/auth/logout', {});
    try { sessionStorage.removeItem('_dashData'); } catch {}
    setUser(null);
    setProfile({});
    setDashData(null);
    setVisited({ dashboard: true });
    setPage('dashboard');
    showToast('Logged out', 'success');
  };

  const [setupDone, setSetupDone] = useState(false);
  const isProfileComplete = (p) => {
    if (setupDone) return true;
    if (!p) return false;
    if (p.resume_score) return true;
    if (p.experience && p.experience.length > 0) return true;
    if (p.skills && Object.keys(p.skills).length > 0) return true;
    return false;
  };

  if (!authChecked) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: 'var(--muted)', fontSize: '1.1rem' }}>Loading...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div>
        <AuthPage onAuth={handleAuth} showToast={showToast} />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    );
  }

  if (welcome) {
    return (
      <>
        <WelcomeOverlay name={welcome.name} isSignup={welcome.isSignup} onDone={() => setWelcome(null)} />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </>
    );
  }

  if (!isProfileComplete(profile)) {
    return (
      <div>
        <div style={styles.navbar}>
          <div style={{ ...styles.logo, cursor: 'pointer' }} onClick={() => navigate('dashboard')}>JobBot</div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>{user.name}</span>
            <button onClick={handleLogout} style={{ ...styles.navLink, color: '#f87171', fontSize: '0.82rem' }}>Logout</button>
          </div>
        </div>
        <ProfileSetup profile={profile} setProfile={setProfile} showToast={showToast} onComplete={() => setSetupDone(true)} />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    );
  }

  return (
    <div>
      <div style={styles.navbar}>
        <div style={{ ...styles.logo, cursor: 'pointer' }} onClick={() => navigate('dashboard')}>JobBot</div>
        <nav style={{ display: 'flex', gap: '0.25rem', flex: 1 }}>
          {[['dashboard', 'Dashboard'], ['jobs', 'Jobs'], ['search', 'Search'], ['profile', 'Profile']].map(([key, label]) => (
            <button key={key} onClick={() => navigate(key)}
              style={{ ...styles.navLink, ...(page === key || (page === 'job' && key === 'jobs') ? styles.navActive : {}) }}>
              {label}
            </button>
          ))}
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginLeft: 'auto' }}>
          <div onClick={() => navigate('profile')} title="My Profile" style={{ cursor: 'pointer', width: 32, height: 32, borderRadius: '50%', flexShrink: 0, overflow: 'hidden', border: '2px solid var(--bg3)', transition: 'border-color 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent2)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--bg3)'}>
            {profile.avatar
              ? <img src={profile.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
              : <div style={{ width: '100%', height: '100%', background: 'linear-gradient(135deg,#2563eb,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, color: '#fff' }}>
                  {(user.name || 'U')[0].toUpperCase()}
                </div>
            }
          </div>
          <span className="hide-sm" style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{user.name}</span>
          <button onClick={handleLogout} style={{ ...styles.navLink, color: '#f87171', fontSize: '0.8rem', padding: '0.35rem 0.6rem' }}>Logout</button>
        </div>
      </div>

      <div style={{ display: page === 'dashboard' ? '' : 'none' }}>
        <Dashboard navigate={navigate} dashData={dashData} onRefresh={fetchDashData} />
      </div>

      {visited.jobs && (
        <div style={{ display: page === 'jobs' ? '' : 'none' }}>
          <Jobs navigate={navigate} showToast={showToast} isVisible={page === 'jobs'} />
        </div>
      )}

      {page === 'job' && <JobDetail jobId={pageArg} navigate={navigate} showToast={showToast} />}

      {visited.search && (
        <div style={{ display: page === 'search' ? '' : 'none' }}>
          <Search profile={profile} showToast={showToast} navigate={navigate} />
        </div>
      )}

      {visited.profile && (
        <div style={{ display: page === 'profile' ? '' : 'none' }}>
          <Profile profile={profile} setProfile={setProfile} showToast={showToast} />
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}

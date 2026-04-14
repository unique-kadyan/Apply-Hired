'use client';
import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import sse from '@/lib/sse';
import styles from '@/lib/styles';
import { refreshTier, useTier } from '@/lib/tier';
import Toast from '@/components/shared/Toast';
import Logo from '@/components/shared/Logo';
import UpgradeModal from '@/components/shared/UpgradeModal';
import AuthPage from '@/components/Auth/AuthPage';
import WelcomeOverlay from '@/components/WelcomeOverlay';
import Dashboard from '@/components/Dashboard/Dashboard';
import Jobs from '@/components/Jobs/Jobs';
import JobDetail from '@/components/Jobs/JobDetail';
import Search from '@/components/Search/Search';
import Profile from '@/components/Profile/Profile';
import ProfileSetup from '@/components/Profile/ProfileSetup';
import ResumePage from '@/components/Resume/ResumePage';
import CircularProgress from '@mui/material/CircularProgress';
import DashboardIcon from '@mui/icons-material/Dashboard';
import WorkIcon from '@mui/icons-material/Work';
import SearchIcon from '@mui/icons-material/Search';
import ArticleIcon from '@mui/icons-material/Article';
import PersonIcon from '@mui/icons-material/Person';
import LogoutIcon from '@mui/icons-material/Logout';

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [page, setPage] = useState('dashboard');
  const [pageArg, setPageArg] = useState(null);
  const [profile, setProfile] = useState({});
  const [toast, setToast] = useState(null);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeMode, setUpgradeMode] = useState('default'); // 'default' | 'welcome' | 'exhausted'
  const [quotaInfo, setQuotaInfo] = useState(null);
  const tierData = useTier();

  // Global upgrade trigger: any nested component can call window.kalibrUpgrade()
  // to open the modal without prop-drilling through every layer.
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    window.kalibrUpgrade = (mode = 'default', info = null) => {
      setUpgradeMode(mode);
      setQuotaInfo(info);
      setUpgradeOpen(true);
    };
    return () => { delete window.kalibrUpgrade; };
  }, []);

  // Welcome banner — auto-opens once per browser session for logged-in free
  // users so they always see the plan comparison + "Continue with Free" / "Upgrade"
  // choice. Pro/admin users are skipped. Session-keyed so it doesn't re-popup
  // on every navigation, but does re-popup on next login.
  useEffect(() => {
    if (!user || !tierData?.tier || upgradeOpen) return;
    if (tierData.tier !== 'free') return;
    try {
      const key = `_welcomeShown_${user.id || user.email}`;
      if (sessionStorage.getItem(key)) return;
      sessionStorage.setItem(key, '1');
    } catch { /* sessionStorage unavailable */ }
    setUpgradeMode('welcome');
    setQuotaInfo(null);
    setUpgradeOpen(true);
  }, [user, tierData?.tier]);

  // Quota-exhausted listener — any 402 response from the API auto-opens the
  // exhausted modal so the user can't miss the limit.
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handler = (e) => {
      const d = e.detail || {};
      const used = d.used != null ? d.used : (d.free_visible_unlocked || 0);
      const limit = d.limit != null ? d.limit : (d.free_visible_limit || 5);
      let feature = d.feature;
      if (!feature) {
        const msg = (d.error || '').toLowerCase();
        if (msg.includes('cover letter')) feature = 'Cover letters';
        else if (msg.includes('application')) feature = 'Applications';
        else if (msg.includes('view')) feature = 'Job views';
        else if (msg.includes('chrome')) feature = 'Chrome extension';
        else if (msg.includes('auto-search')) feature = 'Auto-search';
        else feature = 'Free plan limit';
      }
      setQuotaInfo({ feature, used, limit, message: d.message || d.error });
      setUpgradeMode('exhausted');
      setUpgradeOpen(true);
    };
    window.addEventListener('quota:exhausted', handler);
    return () => window.removeEventListener('quota:exhausted', handler);
  }, []);

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

  // Live dashboard updates: refetch whenever the server pushes a jobs_changed event.
  useEffect(() => {
    if (!user) return undefined;
    const off = sse.subscribe('jobs_changed', () => fetchDashData());
    return off;
  }, [user, fetchDashData]);

  useEffect(() => {
    const onSessionExpired = () => {
      setUser(null);
      setProfile({});
      setDashData(null);
      setVisited({ dashboard: true });
      setPage('dashboard');
      setToast({ message: 'Your session has expired. Please sign in again.', type: 'warning' });
      try { sessionStorage.removeItem('_dashData'); } catch {}
    };
    window.addEventListener('session:expired', onSessionExpired);
    return () => window.removeEventListener('session:expired', onSessionExpired);
  }, []);

  useEffect(() => {
    api.get('/api/auth/me').then(res => {
      if (res.user) {
        setUser(res.user);
        api.get('/api/profile').then(setProfile);
        fetchDashData();
        refreshTier();
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
    try {
      sessionStorage.removeItem('_dashData');
      // Clear welcome-shown flags so the comparison modal re-appears on next login
      Object.keys(sessionStorage)
        .filter((k) => k.startsWith('_welcomeShown_'))
        .forEach((k) => sessionStorage.removeItem(k));
    } catch { /* sessionStorage unavailable */ }
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
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem' }}>
        <CircularProgress size={36} sx={{ color: '#60a5fa' }} />
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>Loading…</p>
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
          <div style={{ cursor: 'pointer' }} onClick={() => navigate('dashboard')}>
            <Logo size={28} />
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>{user.name}</span>
            <button onClick={handleLogout} style={{ ...styles.navLink, color: '#f87171', fontSize: '0.82rem', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
              <LogoutIcon style={{ fontSize: 15 }} />Logout
            </button>
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
        <div style={{ cursor: 'pointer' }} onClick={() => navigate('dashboard')}>
          <Logo size={28} />
        </div>
        <nav style={{ display: 'flex', gap: '0.25rem', flex: 1 }}>
          {[
            ['dashboard', 'Dashboard', <DashboardIcon style={{ fontSize: 16 }} />],
            ['jobs',      'Jobs',      <WorkIcon style={{ fontSize: 16 }} />],
            ['search',    'Search',    <SearchIcon style={{ fontSize: 16 }} />],
            ['resume',    'Resume',    <ArticleIcon style={{ fontSize: 16 }} />],
            ['profile',   'Profile',   <PersonIcon style={{ fontSize: 16 }} />],
          ].map(([key, label, icon]) => (
            <button key={key} onClick={() => navigate(key)}
              style={{ ...styles.navLink, ...(page === key || (page === 'job' && key === 'jobs') ? styles.navActive : {}), display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
              {icon}<span className="hide-sm">{label}</span>
            </button>
          ))}
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginLeft: 'auto' }}>
          <button onClick={() => setUpgradeOpen(true)} title="Upgrade to Pro" style={{
            background: 'linear-gradient(135deg,#7c3aed,#2563eb)', color: '#fff', border: 'none',
            borderRadius: 8, padding: '0.4rem 0.85rem', fontWeight: 700, fontSize: '0.78rem',
            cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>⚡ <span className="hide-sm">Upgrade</span></button>
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
          <button onClick={handleLogout} style={{ ...styles.navLink, color: '#f87171', fontSize: '0.8rem', padding: '0.35rem 0.6rem', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
            <LogoutIcon style={{ fontSize: 15 }} /><span className="hide-sm">Logout</span>
          </button>
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

      {visited.resume && (
        <div style={{ display: page === 'resume' ? '' : 'none' }}>
          <ResumePage profile={profile} setProfile={setProfile} showToast={showToast} />
        </div>
      )}

      {visited.profile && (
        <div style={{ display: page === 'profile' ? '' : 'none' }}>
          <Profile profile={profile} setProfile={setProfile} showToast={showToast} />
        </div>
      )}

      <UpgradeModal
        open={upgradeOpen}
        onClose={() => { setUpgradeOpen(false); setUpgradeMode('default'); setQuotaInfo(null); }}
        showToast={showToast}
        mode={upgradeMode}
        quotaInfo={quotaInfo}
      />
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}

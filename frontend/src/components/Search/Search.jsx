'use client';
import { useState, useEffect, useRef } from 'react';
import api from '@/lib/api';
import styles from '@/lib/styles';
import { SkillChip } from '@/components/shared/Badge';
import Switch from '@mui/material/Switch';
import LinearProgress from '@mui/material/LinearProgress';
import CircularProgress from '@mui/material/CircularProgress';
import ScheduleIcon from '@mui/icons-material/Schedule';
import EditIcon from '@mui/icons-material/Edit';
import WorkIcon from '@mui/icons-material/Work';
import ReplayIcon from '@mui/icons-material/Replay';
import SearchIcon from '@mui/icons-material/Search';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import TuneIcon from '@mui/icons-material/Tune';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import SaveIcon from '@mui/icons-material/Save';

export default function Search({ profile, showToast, navigate }) {
  const [jobTitle, setJobTitle] = useState('');
  const [selectedSkills, setSelectedSkills] = useState(new Set());
  const [customSkills, setCustomSkills] = useState('');
  const [locationType, setLocationType] = useState('remote');
  const [customLocation, setCustomLocation] = useState('');
  const [remoteCountry, setRemoteCountry] = useState('');
  const [levels, setLevels] = useState(new Set(['Senior']));
  const [minScore, setMinScore] = useState(30);
  const [minSalary, setMinSalary] = useState(0);
  const [searchStatus, setSearchStatus] = useState(null);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleInterval, setScheduleInterval] = useState(24);
  const [scheduleLastRun, setScheduleLastRun] = useState(null);
  const [scheduleSaving, setScheduleSaving] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [scheduleEditing, setScheduleEditing] = useState(true);
  const [scheduleLocType, setScheduleLocType] = useState('remote');
  const [scheduleCountry, setScheduleCountry] = useState('India');
  const pollRef = useRef(null);

  const _computeNextRun = (lastRun, intervalH) => {
    if (!lastRun) return new Date(Date.now() + intervalH * 3600 * 1000);
    return new Date(new Date(lastRun).getTime() + intervalH * 3600 * 1000);
  };

  const toggleSkill = (skill) => {
    setSelectedSkills(prev => { const n = new Set(prev); n.has(skill) ? n.delete(skill) : n.add(skill); return n; });
  };

  const toggleLevel = (level) => {
    setLevels(prev => { const n = new Set(prev); n.has(level) ? n.delete(level) : n.add(level); return n; });
  };

  const selectRecommended = () => {
    setSelectedSkills(new Set(['Java', 'Python', 'Spring Boot', 'React.js', 'PostgreSQL', 'AWS', 'Docker', 'Kafka', 'Microservices', 'REST APIs', 'Redis']));
    if (!jobTitle) setJobTitle('Senior Backend Engineer');
  };

  const selectGroup = (group) => {
    const skills = profile.skills[group] || [];
    const allSelected = skills.every(s => selectedSkills.has(s));
    setSelectedSkills(prev => {
      const n = new Set(prev);
      skills.forEach(s => allSelected ? n.delete(s) : n.add(s));
      return n;
    });
  };

  const startSearch = async () => {
    const allSkills = [...selectedSkills, ...customSkills.split(',').map(s => s.trim()).filter(Boolean)];
    if (!jobTitle && allSkills.length === 0) { showToast('Enter a job title or select skills', 'error'); return; }

    let location = 'remote';
    let country = remoteCountry || 'India';
    if (locationType === 'remote_country') location = `remote ${remoteCountry}`;
    else if (locationType === 'custom') { location = customLocation; country = ''; }

    setSearchStatus({ running: true, progress: 5, message: 'Preparing search...' });

    const res = await api.post('/api/search', { job_title: jobTitle, skills: allSkills, location, country, levels: [...levels], min_score: minScore / 100, min_salary: minSalary });
    if (res && res.error) {
      setSearchStatus({ running: false, progress: 0, message: res.error });
      showToast(res.error, 'error');
      return;
    }
    pollStatus();
  };

  const pollStatus = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.get('/api/search/status');
        setSearchStatus(status);
        if (!status.running) {
          clearInterval(pollRef.current); pollRef.current = null;
          if (status.progress >= 100) {
            showToast(status.message || 'Search complete!', 'success');
            navigate('jobs');
          }
        }
      } catch (_) { }
    }, 2000);
  };

  useEffect(() => {
    api.get('/api/search/status').then(s => { setSearchStatus(s); if (s.running) pollStatus(); });
    api.get('/api/search/schedule').then(s => {
      setScheduleEnabled(s.enabled || false);
      setScheduleInterval(s.interval_hours || 24);
      setScheduleLastRun(s.last_run || null);
      if (s.enabled) setScheduleEditing(false);
      const savedLoc = (s.params || {}).location || 'remote';
      if (savedLoc === 'remote') { setScheduleLocType('remote'); }
      else if (savedLoc.startsWith('remote ')) { setScheduleLocType('remote_country'); setScheduleCountry(savedLoc.replace('remote ', '')); }
      else { setScheduleLocType('custom'); setScheduleCountry(savedLoc); }
    }).catch(() => {});
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const saveSchedule = async () => {
    setScheduleSaving(true);
    const customSkillList = customSkills.split(',').map(s => s.trim()).filter(Boolean);
    const allSkills = [...selectedSkills, ...customSkillList];
    let schedLocation = 'remote';
    let schedCountryVal = scheduleCountry.trim();
    if (scheduleLocType === 'remote_country') schedLocation = `remote ${schedCountryVal}`;
    else if (scheduleLocType === 'custom') schedLocation = schedCountryVal;
    try {
      await api.put('/api/search/schedule', {
        enabled: scheduleEnabled,
        interval_hours: scheduleInterval,
        params: { job_title: jobTitle, skills: allSkills, location: schedLocation, country: scheduleLocType === 'remote_country' ? schedCountryVal : '', levels: [...levels], min_score: minScore / 100, min_salary: minSalary },
      });
      showToast(scheduleEnabled ? `Auto-search enabled (every ${scheduleInterval}h)` : 'Auto-search disabled', 'success');
      setScheduleLastRun(new Date().toISOString());
      setScheduleEditing(false);
    } catch { showToast('Failed to save schedule', 'error'); }
    setScheduleSaving(false);
  };

  return (
    <div style={styles.container}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <SearchIcon sx={{ fontSize: 28, color: 'var(--accent2)' }} /> Search Jobs
      </h1>

      <div style={styles.card}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Configure Your Search</h2>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.4rem', fontSize: '0.9rem' }}>Job Title / Role</label>
          <input style={styles.input} value={jobTitle} onChange={e => setJobTitle(e.target.value)} placeholder="e.g. Senior Backend Engineer, Java Developer..." />
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.4rem', fontSize: '0.9rem' }}>Location</label>
          <div style={{ display: 'flex', gap: '1.25rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', color: 'var(--text2)' }}>
              <input type="radio" checked={locationType === 'remote'} onChange={() => setLocationType('remote')} style={{ accentColor: 'var(--accent)' }} /> Remote (Worldwide)
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', color: 'var(--text2)' }}>
              <input type="radio" checked={locationType === 'remote_country'} onChange={() => setLocationType('remote_country')} style={{ accentColor: 'var(--accent)' }} /> Remote in Country
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', color: 'var(--text2)' }}>
              <input type="radio" checked={locationType === 'custom'} onChange={() => setLocationType('custom')} style={{ accentColor: 'var(--accent)' }} /> Specific Location
            </label>
          </div>
          {locationType === 'remote_country' && (
            <div style={{ marginTop: '0.75rem' }}>
              <select style={{ ...styles.select, width: '100%', maxWidth: 350 }} value={remoteCountry} onChange={e => setRemoteCountry(e.target.value)}>
                <option value="">Select country...</option>
                <option value="USA">United States (USA)</option>
                <option value="UK">United Kingdom (UK)</option>
                <option value="Canada">Canada</option>
                <option value="Germany">Germany</option>
                <option value="Netherlands">Netherlands</option>
                <option value="India">India</option>
                <option value="Australia">Australia</option>
                <option value="Singapore">Singapore</option>
                <option value="UAE">UAE / Dubai</option>
                <option value="France">France</option>
                <option value="Spain">Spain</option>
                <option value="Ireland">Ireland</option>
                <option value="Sweden">Sweden</option>
                <option value="Switzerland">Switzerland</option>
                <option value="Japan">Japan</option>
                <option value="Brazil">Brazil</option>
                <option value="Europe">Europe (Any)</option>
                <option value="APAC">Asia-Pacific (Any)</option>
                <option value="LATAM">Latin America (Any)</option>
              </select>
              <input style={{ ...styles.input, marginTop: '0.5rem', maxWidth: 350 }} value={remoteCountry} onChange={e => setRemoteCountry(e.target.value)} placeholder="Or type any country/region..." />
            </div>
          )}
          {locationType === 'custom' && (
            <input style={{ ...styles.input, marginTop: '0.75rem', maxWidth: 350 }} value={customLocation} onChange={e => setCustomLocation(e.target.value)} placeholder="e.g. New York, Berlin, Bangalore..." />
          )}
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.4rem', fontSize: '0.9rem' }}>
            Minimum Salary (USD): <strong style={{ color: minSalary > 0 ? 'var(--green2)' : 'var(--text)' }}>{minSalary > 0 ? `$${minSalary.toLocaleString()}+/yr` : 'Any'}</strong>
          </label>
          <input type="range" min="0" max="300000" step="10000" value={minSalary} onChange={e => setMinSalary(Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--accent)' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.2rem' }}>
            <span>Any</span><span>$50k</span><span>$100k</span><span>$150k</span><span>$200k</span><span>$300k</span>
          </div>
          {minSalary > 0 && (
            <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.3rem' }}>
              Auto-converts to job's local currency (&#8377;{Math.round(minSalary * 83.5).toLocaleString()} INR · &pound;{Math.round(minSalary * 0.79).toLocaleString()} GBP · &euro;{Math.round(minSalary * 0.92).toLocaleString()} EUR)
            </p>
          )}
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.4rem', fontSize: '0.9rem' }}>Select Skills <span style={{ fontWeight: 400, fontSize: '0.82rem' }}>(click to toggle)</span></label>
          {profile.skills && Object.entries(profile.skills).map(([group, skills]) => (
            <div key={group} style={{ marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.3rem' }}>
                <span style={{ color: '#64748b', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{group.replace(/_/g, ' ')}</span>
                <button style={{ background: 'none', border: '1px solid #475569', color: 'var(--muted)', padding: '0.1rem 0.5rem', borderRadius: 4, fontSize: '0.72rem', cursor: 'pointer' }} onClick={() => selectGroup(group)}>Toggle All</button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                {skills.map(skill => <SkillChip key={skill} label={skill} selected={selectedSkills.has(skill)} onClick={() => toggleSkill(skill)} />)}
              </div>
            </div>
          ))}
          <div style={{ marginTop: '0.75rem' }}>
            <span style={{ color: '#64748b', fontSize: '0.78rem', textTransform: 'uppercase' }}>Custom Skills</span>
            <input style={{ ...styles.input, marginTop: '0.3rem' }} value={customSkills} onChange={e => setCustomSkills(e.target.value)} placeholder="e.g. Kubernetes, GraphQL, Terraform (comma-separated)" />
          </div>
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.4rem', fontSize: '0.9rem' }}>Experience Level</label>
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {[
              { label: 'Junior', years: '0–2 yrs' },
              { label: 'Mid-Level', years: '2–5 yrs' },
              { label: 'Senior', years: '5–8 yrs' },
              { label: 'Lead', years: '7–12 yrs' },
              { label: 'Staff', years: '10–15 yrs' },
              { label: 'Principal', years: '12+ yrs' },
            ].map(({ label, years }) => (
              <button key={label} onClick={() => toggleLevel(label)}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center',
                  padding: '0.4rem 0.85rem', borderRadius: 20, border: `1px solid ${levels.has(label) ? 'var(--accent2)' : 'var(--border)'}`,
                  background: levels.has(label) ? 'rgba(37,99,235,0.18)' : 'transparent',
                  color: levels.has(label) ? 'var(--accent2)' : 'var(--muted)',
                  cursor: 'pointer', transition: 'all 0.15s', lineHeight: 1.2,
                }}>
                <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>{label}</span>
                <span style={{ fontSize: '0.7rem', opacity: 0.75 }}>{years}</span>
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', color: 'var(--muted)', fontWeight: 600, marginBottom: '0.4rem', fontSize: '0.9rem' }}>Minimum Match Score: <strong style={{ color: 'var(--text)' }}>{minScore}%</strong></label>
          <input type="range" min="0" max="80" value={minScore} onChange={e => setMinScore(Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--accent)' }} />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button style={{ ...styles.btn, ...styles.btnPrimary }} onClick={startSearch} disabled={searchStatus?.running}>
            {searchStatus?.running
              ? <><CircularProgress size={14} sx={{ color: '#fff', mr: 0.5 }} /> Searching…</>
              : <><SearchIcon style={{ fontSize: 16 }} /> Start Search</>}
          </button>
          <button style={{ ...styles.btn, ...styles.btnSecondary }} onClick={selectRecommended}>
            <AutoAwesomeIcon style={{ fontSize: 16 }} /> Auto-Select Recommended
          </button>
        </div>
      </div>

      <div style={styles.card}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }} onClick={() => setShowSchedule(v => !v)}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <ScheduleIcon sx={{ fontSize: 20, color: scheduleEnabled ? '#6ee7b7' : 'var(--muted)' }} />
            <div>
              <span style={{ fontWeight: 700, fontSize: '0.92rem' }}>Auto-Search Schedule</span>
              {scheduleEnabled
                ? <span style={{ marginLeft: '0.5rem', background: 'rgba(5,150,105,0.15)', color: '#6ee7b7', border: '1px solid rgba(5,150,105,0.3)', borderRadius: 20, padding: '0.05rem 0.5rem', fontSize: '0.72rem', fontWeight: 700 }}>Every {scheduleInterval}h</span>
                : <span style={{ marginLeft: '0.5rem', color: 'var(--muted)', fontSize: '0.78rem' }}>Off</span>
              }
            </div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            style={{ transition: 'transform 0.25s', transform: showSchedule ? 'rotate(180deg)' : 'rotate(0deg)', color: 'var(--muted)' }}>
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
        {showSchedule && (
          <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border)' }}>
            {!scheduleEditing ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', minWidth: 110 }}>Status</span>
                  <span style={{ background: scheduleEnabled ? 'rgba(5,150,105,0.12)' : 'rgba(100,116,139,0.12)', color: scheduleEnabled ? '#6ee7b7' : '#94a3b8', padding: '0.25rem 0.85rem', borderRadius: 20, fontSize: '0.84rem', fontWeight: 700, border: `1px solid ${scheduleEnabled ? 'rgba(5,150,105,0.3)' : 'rgba(100,116,139,0.25)'}` }}>
                    {scheduleEnabled ? `Enabled — every ${scheduleInterval}h` : 'Disabled'}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', minWidth: 110 }}>Location</span>
                  <span style={{ color: '#e2e8f0', fontSize: '0.88rem' }}>
                    {scheduleLocType === 'remote' ? 'Remote (Any Country)' : scheduleLocType === 'remote_country' ? `Remote — ${scheduleCountry}` : scheduleCountry || 'Custom'}
                  </span>
                </div>
                {scheduleEnabled && (
                  <>
                    {scheduleLastRun && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', minWidth: 110 }}>Last Run</span>
                        <span style={{ color: '#e2e8f0', fontSize: '0.9rem' }}>{new Date(scheduleLastRun).toLocaleString()}</span>
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', minWidth: 110 }}>Next Search</span>
                      <span style={{ color: '#6ee7b7', fontSize: '0.9rem', fontWeight: 600 }}>
                        {_computeNextRun(scheduleLastRun, scheduleInterval).toLocaleString()}
                      </span>
                      <span style={{ color: 'var(--muted)', fontSize: '0.78rem' }}>— runs automatically</span>
                    </div>
                  </>
                )}
                <div style={{ marginTop: '0.25rem' }}>
                  <button onClick={() => setScheduleEditing(true)} style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--text2)', borderRadius: 8, padding: '0.35rem 0.85rem', cursor: 'pointer', fontSize: '0.82rem', fontWeight: 500, display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                    <EditIcon style={{ fontSize: 14 }} /> Edit Schedule
                  </button>
                </div>
              </div>
            ) : (
              <>
                <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginBottom: '0.9rem' }}>
                  Automatically search with your current filters every N hours. Uses the title, skills, and levels selected above.
                </p>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontWeight: 600, color: 'var(--muted)', fontSize: '0.78rem', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Work Mode &amp; Location</label>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    {[
                      { v: 'remote', l: 'Remote (Any Country)' },
                      { v: 'remote_country', l: 'Remote in Country' },
                      { v: 'custom', l: 'Custom' },
                    ].map(opt => (
                      <label key={opt.v} onClick={() => setScheduleLocType(opt.v)} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', padding: '0.35rem 0.8rem', borderRadius: 20, border: '1px solid ' + (scheduleLocType === opt.v ? '#3b82f6' : 'var(--border)'), background: scheduleLocType === opt.v ? 'rgba(59,130,246,0.15)' : 'transparent', color: scheduleLocType === opt.v ? '#60a5fa' : 'var(--text2)', fontSize: '0.82rem', fontWeight: scheduleLocType === opt.v ? 600 : 400, userSelect: 'none' }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid ' + (scheduleLocType === opt.v ? '#3b82f6' : '#475569'), background: scheduleLocType === opt.v ? '#3b82f6' : 'transparent', display: 'inline-block', flexShrink: 0 }}></span>
                        {opt.l}
                      </label>
                    ))}
                    {(scheduleLocType === 'remote_country' || scheduleLocType === 'custom') && (
                      <input
                        value={scheduleCountry}
                        onChange={e => setScheduleCountry(e.target.value)}
                        placeholder={scheduleLocType === 'remote_country' ? 'e.g. India' : 'e.g. Bangalore'}
                        style={{ ...styles.input, width: 140, padding: '0.35rem 0.7rem', fontSize: '0.85rem' }}
                      />
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer', userSelect: 'none' }}>
                    <Switch
                      checked={scheduleEnabled}
                      onChange={e => setScheduleEnabled(e.target.checked)}
                      size="small"
                      sx={{
                        '& .MuiSwitch-switchBase.Mui-checked': { color: '#fff' },
                        '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: '#059669', opacity: 1 },
                        '& .MuiSwitch-track': { backgroundColor: '#334155', opacity: 1 },
                      }}
                    />
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: scheduleEnabled ? '#6ee7b7' : 'var(--muted)' }}>
                      {scheduleEnabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </label>
                  {scheduleEnabled && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>Every</span>
                      {[6, 12, 24, 48].map(h => (
                        <button key={h} onClick={() => setScheduleInterval(h)}
                          style={{ ...styles.btn, ...styles.btnSm, background: scheduleInterval === h ? 'var(--accent)' : 'var(--bg3)', color: scheduleInterval === h ? '#fff' : 'var(--muted)', fontWeight: scheduleInterval === h ? 700 : 400, border: scheduleInterval === h ? '1px solid var(--accent)' : '1px solid var(--border)', minWidth: 40 }}>
                          {h}h
                        </button>
                      ))}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '0.5rem', marginLeft: 'auto', alignItems: 'center' }}>
                    {scheduleLastRun && <button type="button" onClick={() => setScheduleEditing(false)} style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '0.85rem', padding: '0.4rem 0.5rem' }}>Cancel</button>}
                    <button onClick={saveSchedule} disabled={scheduleSaving}
                      style={{ ...styles.btn, ...styles.btnSm, background: '#059669', color: '#fff' }}>
                      {scheduleSaving
                        ? <><CircularProgress size={12} sx={{ color: '#fff' }} /> Saving…</>
                        : <><SaveIcon style={{ fontSize: 14 }} /> Save Schedule</>}
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {searchStatus && (searchStatus.running || searchStatus.progress > 0) && (
        <div style={styles.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h2 style={{ fontSize: '1rem', margin: 0, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              {searchStatus.running
                ? <><CircularProgress size={16} sx={{ color: '#60a5fa' }} /> Searching…</>
                : searchStatus.progress >= 100
                  ? <><CheckCircleIcon sx={{ fontSize: 18, color: '#6ee7b7' }} /> Search Complete</>
                  : <><WarningAmberIcon sx={{ fontSize: 18, color: '#fcd34d' }} /> Search Ended</>
              }
            </h2>
            {searchStatus.progress > 0 && (
              <span style={{ fontSize: '1rem', fontWeight: 700, color: searchStatus.progress >= 100 ? 'var(--green2)' : 'var(--accent2)' }}>
                {searchStatus.progress}%
              </span>
            )}
          </div>
          {searchStatus.progress > 0 && (
            <div style={{ marginBottom: '0.75rem' }}>
              <LinearProgress
                variant="determinate"
                value={searchStatus.progress}
                sx={{
                  height: 10,
                  borderRadius: 5,
                  backgroundColor: 'var(--bg3)',
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 5,
                    background: searchStatus.progress >= 100
                      ? '#059669'
                      : searchStatus.running
                        ? 'linear-gradient(90deg, #2563eb, #7c3aed)'
                        : '#dc2626',
                    transition: 'transform 0.4s ease',
                  },
                }}
              />
              <div style={{ textAlign: 'right', fontSize: '0.72rem', color: 'var(--muted)', marginTop: '0.2rem' }}>
                {searchStatus.progress}%
              </div>
            </div>
          )}
          <p style={{ color: searchStatus.message?.startsWith('Error') ? '#fca5a5' : 'var(--muted)', fontSize: '0.88rem', marginBottom: !searchStatus.running ? '0.75rem' : 0 }}>{searchStatus.message}</p>
          {!searchStatus.running && (
            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button onClick={() => navigate('jobs')} style={{ ...styles.btn, ...styles.btnPrimary, ...styles.btnSm }}>
                <WorkIcon style={{ fontSize: 15 }} /> View Jobs
              </button>
              {searchStatus.progress < 100 && (
                <button onClick={startSearch} style={{ ...styles.btn, ...styles.btnSecondary, ...styles.btnSm }}>
                  <ReplayIcon style={{ fontSize: 15 }} /> Retry Search
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

'use client';
import { useEffect } from 'react';
import styles from '@/lib/styles';
import { Badge } from '@/components/shared/Badge';
import { DonutChart, LineChart, BarChart, FunnelChart } from '@/components/shared/Charts';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import AutorenewIcon from '@mui/icons-material/Autorenew';
import SendIcon from '@mui/icons-material/Send';
import GroupsIcon from '@mui/icons-material/Groups';
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import InsightsIcon from '@mui/icons-material/Insights';
import SearchIcon from '@mui/icons-material/Search';
import ListAltIcon from '@mui/icons-material/ListAlt';
import BusinessCenterIcon from '@mui/icons-material/BusinessCenter';
import WavingHandIcon from '@mui/icons-material/WavingHand';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';

export default function Dashboard({ navigate, dashData, onRefresh }) {
  const _emptyStats = { new: 0, applied: 0, interview: 0, offer: 0, not_interested: 0, total: 0, response_rate: 0, sources: {}, cover_letter_ab: {} };

  const stats = (dashData && dashData.stats) || _emptyStats;
  const statsLoading = !dashData;
  const recentJobs = {
    new:       (dashData && dashData.recentNew)       || [],
    applied:   (dashData && dashData.recentApplied)   || [],
    interview: (dashData && dashData.recentInterview) || [],
  };

  useEffect(() => { if (onRefresh) onRefresh(); }, []);

  const statusDonut = {
    labels: ['New', 'Applied', 'Interview', 'Offer', 'Not Interested'],
    values: [stats.new, stats.applied, stats.interview, stats.offer || 0, stats.not_interested],
    colors: ['#2563eb', '#059669', '#7c3aed', '#f59e0b', '#dc2626'],
  };

  const scoreLabels = (stats.score_distribution || []).map(s => s.label);
  const scoreValues = (stats.score_distribution || []).map(s => s.count);
  const scoreColors = ['#dc2626','#f97316','#f59e0b','#22c55e','#2563eb'];

  const topCoNames = (stats.top_companies || []).map(c => c.name.length > 18 ? c.name.slice(0, 16) + '…' : c.name);
  const topCoCounts = (stats.top_companies || []).map(c => c.count);

  const activityLabels = (stats.daily_activity || []).map(d => d.date.slice(5));
  const activityValues = (stats.daily_activity || []).map(d => d.count);

  const totalActive = stats.new + stats.applied + stats.interview + (stats.offer || 0);

  return (
    <div style={styles.container} className="responsive-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Dashboard</h1>
          <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginTop: '0.2rem' }}>Your job search at a glance</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button style={{ ...styles.btn, ...styles.btnPrimary }} onClick={() => navigate('search')}>
            <SearchIcon style={{ fontSize: 16 }} /> Search Jobs
          </button>
          <button style={{ ...styles.btn, ...styles.btnSuccess }} onClick={() => navigate('jobs')}>
            <ListAltIcon style={{ fontSize: 16 }} /> All Jobs
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
          { n: stats.total,   l: 'Total Found', c: '#60a5fa', icon: <FolderOpenIcon sx={{ fontSize: 24, color: '#60a5fa' }} /> },
          { n: stats.new,     l: 'New',         c: '#67e8f9', icon: <AutorenewIcon  sx={{ fontSize: 24, color: '#67e8f9' }} /> },
          { n: stats.applied, l: 'Applied',     c: '#6ee7b7', icon: <SendIcon        sx={{ fontSize: 24, color: '#6ee7b7' }} /> },
          { n: stats.interview, l: 'Interviews',c: '#d8b4fe', icon: <GroupsIcon      sx={{ fontSize: 24, color: '#d8b4fe' }} /> },
          { n: stats.offer || 0, l: 'Offers',  c: '#fcd34d', icon: <EmojiEventsIcon sx={{ fontSize: 24, color: '#fcd34d' }} /> },
          { n: stats.not_interested, l: 'Skipped', c: '#f87171', icon: <SkipNextIcon sx={{ fontSize: 24, color: '#f87171' }} /> },
          { n: `${Math.round((stats.avg_score || 0) * 100)}%`, l: 'Avg Match', c: '#fb923c', icon: <InsightsIcon sx={{ fontSize: 24, color: '#fb923c' }} /> },
        ].map((s, i) => (
          <div key={i} style={{ ...styles.card, textAlign: 'center', padding: '0.9rem 0.5rem', cursor: i < 3 ? 'pointer' : 'default', animation: statsLoading ? 'pulse 1.4s ease-in-out infinite' : 'none' }}
            onClick={() => { if (i === 0 || i === 1) navigate('jobs'); if (i === 2) navigate('jobs'); }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.3rem' }}>{s.icon}</div>
            {statsLoading
              ? <div style={{ height: 28, borderRadius: 6, background: 'var(--bg3)', margin: '0 auto', width: 48, animation: 'pulse 1.2s ease-in-out infinite' }} />
              : <div style={{ fontSize: '1.7rem', fontWeight: 800, color: s.c, lineHeight: 1 }}>{s.n}</div>
            }
            <div style={{ color: 'var(--muted)', fontSize: '0.75rem', marginTop: '0.3rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.l}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
        <div style={styles.card}>
          <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.9rem' }}>Status Breakdown</h3>
          {statsLoading
            ? <div style={{ height: 180, borderRadius: 10, background: 'var(--bg3)', animation: 'pulse 1.2s ease-in-out infinite' }} />
            : totalActive === 0
            ? <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '2rem 0', fontSize: '0.85rem' }}>No jobs yet — run a search first</p>
            : <div style={{ height: 200 }}><DonutChart data={statusDonut.values} labels={statusDonut.labels} colors={statusDonut.colors} /></div>
          }
        </div>

        <div style={styles.card}>
          <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.9rem' }}>Jobs Added — Last 14 Days</h3>
          {statsLoading
            ? <div style={{ height: 140, borderRadius: 10, background: 'var(--bg3)', animation: 'pulse 1.2s ease-in-out infinite' }} />
            : activityValues.every(v => v === 0)
            ? <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '2rem 0', fontSize: '0.85rem' }}>No recent activity</p>
            : <div style={{ height: 160 }}><LineChart labels={activityLabels} values={activityValues} /></div>
          }
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
        <div style={styles.card}>
          <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.9rem' }}>Match Score Distribution</h3>
          <div style={{ height: 180 }}>
            <BarChart labels={scoreLabels} values={scoreValues} color={scoreColors} />
          </div>
        </div>

        <div style={styles.card}>
          <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '1rem' }}>Application Funnel</h3>
          <FunnelChart stages={stats.funnel} />
          {stats.funnel && stats.funnel[0]?.count > 0 && stats.funnel[2]?.count > 0 && (
            <p style={{ color: 'var(--muted)', fontSize: '0.78rem', marginTop: '0.75rem', textAlign: 'center' }}>
              Application rate: <span style={{ color: '#6ee7b7', fontWeight: 700 }}>
                {Math.round((stats.funnel[2].count / stats.funnel[0].count) * 100)}%
              </span> of discovered jobs applied
            </p>
          )}
        </div>
      </div>

      {topCoCounts.length > 0 && (
        <div style={{ ...styles.card, marginBottom: '0.75rem' }}>
          <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.9rem' }}>Top Hiring Companies</h3>
          <div style={{ height: Math.max(180, topCoNames.length * 30) }}>
            <BarChart labels={topCoNames} values={topCoCounts} color="#2563eb" horizontal={true} />
          </div>
        </div>
      )}

      {(stats.cover_letter_ab || []).length > 1 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
          {(stats.cover_letter_ab || []).length > 1 && (
            <div style={styles.card}>
              <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.9rem' }}>
                Cover Letter A/B — Tone vs Callbacks
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {(stats.cover_letter_ab || []).map((ab, i) => (
                  <div key={i} style={{ padding: '0.7rem 0.9rem', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 8, display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {ab.tone === 'formal'
                        ? <BusinessCenterIcon sx={{ fontSize: 26, color: '#a5b4fc' }} />
                        : <WavingHandIcon sx={{ fontSize: 26, color: '#fcd34d' }} />}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.88rem', textTransform: 'capitalize' }}>{ab.tone}</span>
                        <span style={{ fontSize: '0.88rem', fontWeight: 800, color: ab.rate >= 15 ? '#4ade80' : '#fbbf24' }}>{ab.rate}%</span>
                      </div>
                      <div style={{ color: 'var(--muted)', fontSize: '0.75rem', marginTop: '0.15rem' }}>{ab.interviews} interviews from {ab.total} letters</div>
                      <div style={{ background: 'var(--bg3)', borderRadius: 4, height: 4, marginTop: '0.4rem', overflow: 'hidden' }}>
                        <div style={{ height: '100%', borderRadius: 4, width: `${Math.min(ab.rate * 3, 100)}%`, background: ab.tone === 'formal' ? '#6366f1' : '#f59e0b', transition: 'width 0.5s' }} />
                      </div>
                    </div>
                  </div>
                ))}
                <p style={{ fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'center', marginTop: '0.2rem' }}>More data accumulates as you generate cover letters</p>
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.75rem' }}>
        {[
          { key: 'new',       label: 'Top New Matches',   color: '#2563eb', jobs: recentJobs.new },
          { key: 'applied',   label: 'Recently Applied',  color: '#059669', jobs: recentJobs.applied },
          { key: 'interview', label: 'Active Interviews', color: '#7c3aed', jobs: recentJobs.interview },
        ].map(group => (
          <div key={group.key} style={{ ...styles.card, padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '0.7rem 1rem', borderBottom: '1px solid var(--border)', borderLeft: `3px solid ${group.color}`, background: 'rgba(255,255,255,0.02)' }}>
              <span style={{ fontWeight: 700, fontSize: '0.88rem' }}>{group.label}</span>
              <span style={{ color: 'var(--muted)', fontSize: '0.78rem', marginLeft: '0.5rem' }}>({group.jobs.length})</span>
            </div>
            {group.jobs.length === 0
              ? <p style={{ color: 'var(--muted)', fontSize: '0.82rem', padding: '1.25rem', textAlign: 'center' }}>None yet</p>
              : group.jobs.map(j => (
                  <div key={j.id} onClick={() => navigate('jobs')}
                    style={{ padding: '0.6rem 1rem', borderBottom: '1px solid rgba(51,65,85,0.5)', cursor: 'pointer', transition: 'background 0.1s' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#93c5fd', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }} title={j.title}>{j.title}</div>
                      {j.followup_due && <span title={`Applied ${j.days_since_applied} days ago — follow up`} style={{ display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: '0.62rem', color: '#fde68a', background: 'rgba(234,179,8,0.2)', border: '1px solid rgba(234,179,8,0.4)', padding: '0.05rem 0.35rem', borderRadius: 6, whiteSpace: 'nowrap', flexShrink: 0 }}>
                        <AccessTimeIcon style={{ fontSize: 10 }} />{j.days_since_applied}d
                      </span>}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.2rem' }}>
                      <span style={{ color: 'var(--muted)', fontSize: '0.76rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>{j.company}</span>
                      <Badge score={j.score} />
                    </div>
                  </div>
                ))
            }
            {group.jobs.length > 0 && (
              <div style={{ padding: '0.5rem', textAlign: 'center', borderTop: '1px solid rgba(51,65,85,0.4)' }}>
                <button onClick={() => navigate('jobs')} style={{ ...styles.btn, ...styles.btnSm, ...styles.btnSecondary, fontSize: '0.76rem' }}>
                View All <ArrowForwardIcon style={{ fontSize: 13, verticalAlign: 'middle' }} />
              </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

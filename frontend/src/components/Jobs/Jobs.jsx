'use client';
import { useState, useEffect, useCallback, useRef } from 'react';
import api from '@/lib/api';
import sse from '@/lib/sse';
import { useTier } from '@/lib/tier';
import { ProBadge, UpgradeBanner } from '@/components/shared/UpgradePrompt';
import styles from '@/lib/styles';
import { Badge, StatusBadge } from '@/components/shared/Badge';

const CURRENCY_SYMBOLS = { INR:'₹', GBP:'£', EUR:'€', JPY:'¥', AUD:'A$', CAD:'C$', SGD:'S$', AED:'AED ', ZAR:'R', BRL:'R$', USD:'$', CHF:'CHF ', SEK:'SEK ', NOK:'NOK ', DKK:'DKK ', PLN:'PLN ', HUF:'HUF ', MXN:'MX$', NZD:'NZ$', HKD:'HK$' };

// Returns the direct application form URL, deriving it from known ATS patterns when possible.
function getApplyUrl(job) {
  if (job.apply_url) return job.apply_url;
  const url = (job.url || '').split('?')[0].replace(/\/$/, '');
  if (!url) return job.url || '';
  // Lever: jobs.lever.co/company/uuid → .../apply
  if (/jobs\.lever\.co\/[^/]+\/[^/]+$/.test(url)) return url + '/apply';
  // Greenhouse: boards.greenhouse.io/company/jobs/id
  if (/boards\.greenhouse\.io\/.+\/jobs\/\d+$/.test(url)) return url + '/apply';
  // Ashby: jobs.ashbyhq.com/company/uuid
  if (/jobs\.ashbyhq\.com\/[^/]+\/[^/]+$/.test(url)) return url + '/apply';
  // Workable: apply.workable.com — already an apply URL
  // Default: use listing URL as-is
  return job.url || '';
}

function detectCurrency(salaryStr, location) {
  const s = salaryStr || '';
  if (/₹|INR|Rs/i.test(s)) return 'INR';
  if (/£|GBP/i.test(s)) return 'GBP';
  if (/€|EUR/i.test(s)) return 'EUR';
  if (/A\$|AUD/i.test(s)) return 'AUD';
  if (/C\$|CAD/i.test(s)) return 'CAD';
  if (/S\$|SGD/i.test(s)) return 'SGD';
  if (/AED|dirham/i.test(s)) return 'AED';
  if (/R\$|BRL/i.test(s)) return 'BRL';
  if (/CHF/i.test(s)) return 'CHF';
  if (/NZ\$|NZD/i.test(s)) return 'NZD';
  if (/HK\$|HKD/i.test(s)) return 'HKD';
  if (/\$/.test(s)) return 'USD';
  const loc = (location || '').toLowerCase();
  if (loc.includes('india')) return 'INR';
  if (loc.includes('uk') || loc.includes('united kingdom') || loc.includes('london')) return 'GBP';
  if (loc.includes('germany') || loc.includes('france') || loc.includes('netherlands') || loc.includes('europe')) return 'EUR';
  if (loc.includes('australia')) return 'AUD';
  if (loc.includes('canada')) return 'CAD';
  if (loc.includes('singapore')) return 'SGD';
  if (loc.includes('uae') || loc.includes('dubai')) return 'AED';
  return 'USD';
}

export function fmtDate(d) {
  if (!d) return '';
  const s = String(d).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return d;
  const dt = new Date(s + 'T00:00:00');
  return dt.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatSalary(salaryStr, location) {
  if (!salaryStr || !salaryStr.trim()) return null;
  const currency = detectCurrency(salaryStr, location);
  const sym = CURRENCY_SYMBOLS[currency] || '';
  const nums = (salaryStr.match(/[\d,]+/g) || []).map(n => parseInt(n.replace(/,/g, '')));
  if (!nums.length) return salaryStr;
  const hasK = /k/i.test(salaryStr);
  const mult = hasK ? 1000 : 1;
  const fmt = n => {
    const v = n * mult;
    if (v >= 100000) return sym + (v / 1000).toFixed(0) + 'k';
    if (v >= 1000)   return sym + v.toLocaleString();
    return sym + v;
  };
  if (nums.length === 1) return fmt(nums[0]);
  return `${fmt(Math.min(...nums))} – ${fmt(Math.max(...nums))}`;
}

async function exportCoverLetterPdf(letter, jobTitle, company) {
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' });

  const PAGE_W = 210, PAGE_H = 297;
  const ML = 25, MR = 25, MB = 25;
  const CONTENT_W = PAGE_W - ML - MR;
  const BODY_SIZE = 11, LINE_H = 6.8, PARA_GAP = 5, BULLET_INDENT = 5;
  const ACCENT = [37, 99, 235];
  const TEXT_DARK = [22, 22, 22];
  const TEXT_MUTED = [100, 100, 100];

  // ── Header bar ──────────────────────────────────────────────────────────
  doc.setFillColor(...ACCENT);
  doc.rect(0, 0, PAGE_W, 22, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(14);
  doc.setTextColor(255, 255, 255);
  doc.text(jobTitle || 'Cover Letter', ML, 13);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.text(company ? `Application · ${company}` : '', ML, 19.5);

  const dateStr = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  doc.text(dateStr, PAGE_W - MR, 19.5, { align: 'right' });

  // ── Body ─────────────────────────────────────────────────────────────────
  let y = 34; // first body line below header

  const addPage = () => {
    doc.addPage();
    doc.setFillColor(...ACCENT);
    doc.rect(0, 0, PAGE_W, 4, 'F');
    y = 16;
  };

  const ensureSpace = (needed) => { if (y + needed > PAGE_H - MB) addPage(); };

  // Split letter into paragraphs (double newline) then into individual lines
  const rawParas = letter.trim().split(/\n{2,}|\r\n\r\n/);

  for (const para of rawParas) {
    const rawLines = para.split(/\n/);

    for (const rawLine of rawLines) {
      const line = rawLine.trimEnd();
      if (!line) { y += PARA_GAP * 0.5; continue; }

      // Detect bullet lines: -, •, *, –
      const bulletMatch = line.match(/^(\s*[-•*–])\s+(.+)/);
      // Detect salutation / closing (Dear…, Sincerely…, Best…, Regards…)
      const isSalutation = /^(Dear |To |Hiring|Regards|Sincerely|Best|Yours|Warm|Thank you)/i.test(line.trim());
      // Detect section heading (all caps short line, or ends with :)
      const isHeading = /^[A-Z][A-Z\s]{2,}:?\s*$/.test(line.trim()) || (line.trim().endsWith(':') && line.trim().length < 50);

      if (isHeading) {
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(BODY_SIZE);
        doc.setTextColor(...ACCENT);
        const wrapped = doc.splitTextToSize(line.trim(), CONTENT_W);
        ensureSpace(wrapped.length * LINE_H + PARA_GAP);
        doc.text(wrapped, ML, y);
        y += wrapped.length * LINE_H + 2;
        doc.setTextColor(...TEXT_DARK);
        doc.setFont('helvetica', 'normal');
      } else if (isSalutation) {
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(BODY_SIZE);
        doc.setTextColor(...TEXT_DARK);
        const wrapped = doc.splitTextToSize(line.trim(), CONTENT_W);
        ensureSpace(wrapped.length * LINE_H + PARA_GAP);
        doc.text(wrapped, ML, y);
        y += wrapped.length * LINE_H + PARA_GAP;
      } else if (bulletMatch) {
        const bulletText = bulletMatch[2];
        const textW = CONTENT_W - BULLET_INDENT;
        const wrapped = doc.splitTextToSize(bulletText, textW);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(BODY_SIZE);
        doc.setTextColor(...TEXT_DARK);
        ensureSpace(wrapped.length * LINE_H + 2);
        // Draw accent bullet dot
        doc.setFillColor(...ACCENT);
        doc.circle(ML + 1.2, y - 1.5, 0.9, 'F');
        doc.text(wrapped, ML + BULLET_INDENT, y);
        y += wrapped.length * LINE_H + 2;
      } else {
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(BODY_SIZE);
        doc.setTextColor(...TEXT_DARK);
        const wrapped = doc.splitTextToSize(line.trim(), CONTENT_W);
        ensureSpace(wrapped.length * LINE_H + 1);
        doc.text(wrapped, ML, y);
        y += wrapped.length * LINE_H + 1;
      }
    }

    y += PARA_GAP; // space between paragraphs
  }

  // ── Page numbers (multi-page only) ───────────────────────────────────────
  const totalPages = doc.internal.getNumberOfPages();
  if (totalPages > 1) {
    for (let p = 1; p <= totalPages; p++) {
      doc.setPage(p);
      doc.setFontSize(7.5);
      doc.setTextColor(...TEXT_MUTED);
      doc.text(`${p} / ${totalPages}`, PAGE_W - MR, PAGE_H - 10, { align: 'right' });
    }
  }

  const slug = s => (s || '').replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase();
  doc.save(`cover_letter_${slug(company)}_${slug(jobTitle)}.pdf`);
}

export default function Jobs({ navigate, showToast, isVisible }) {
  const tierData = useTier();
  const tier = tierData?.tier || 'free';
  const isFree = tier === 'free';
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [filters, setFilters] = useState({ status: '', min_score: 0, salary: '' });
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [tab, setTab] = useState('not_applied');
  const [jobPanel, setJobPanel] = useState(null);
  const [jobPanelLoading, setJobPanelLoading] = useState(false);
  const [tabCounts, setTabCounts] = useState({ not_applied: null, applied: null, not_interested: null, saved: null, history: null });
  const [searchQ, setSearchQ] = useState('');
  const [sortBy, setSortBy] = useState('');
  const [sortDir, setSortDir] = useState('desc');
  const searchTimer = useRef(null);
  const [perPage, setPerPage] = useState(30);

  const _jobMode = (j) => {
    const jt = (j.job_type || '').toLowerCase();
    const loc = (j.location || '').toLowerCase();
    if (jt === 'remote' || loc.includes('remote') || loc.includes('wfh') || loc.includes('work from home') || loc.includes('telecommute')) return 'Remote';
    if (loc.includes('hybrid')) return 'Hybrid';
    return 'Onsite';
  };

  const _COUNTRY_MAP = [
    ['india', 'India'], ['united states', 'USA'], ['(us)', 'USA'], [' us,', 'USA'], ['us-', 'USA'],
    ['united kingdom', 'UK'], ['(uk)', 'UK'], [' uk,', 'UK'], ['britain', 'UK'], ['england', 'UK'],
    ['canada', 'Canada'], ['(ca)', 'Canada'], ['australia', 'Australia'], ['(au)', 'Australia'],
    ['germany', 'Germany'], ['france', 'France'], ['singapore', 'Singapore'],
    ['netherlands', 'Netherlands'], ['sweden', 'Sweden'], ['norway', 'Norway'],
    ['finland', 'Finland'], ['denmark', 'Denmark'], ['switzerland', 'Switzerland'],
    ['poland', 'Poland'], ['spain', 'Spain'], ['italy', 'Italy'], ['portugal', 'Portugal'],
    ['ireland', 'Ireland'], ['austria', 'Austria'], ['belgium', 'Belgium'],
    ['new zealand', 'NZ'], ['brazil', 'Brazil'], ['mexico', 'Mexico'],
    ['japan', 'Japan'], ['south korea', 'S. Korea'], ['china', 'China'],
    ['hong kong', 'Hong Kong'], ['taiwan', 'Taiwan'], ['philippines', 'PH'],
    ['indonesia', 'Indonesia'], ['malaysia', 'Malaysia'], ['thailand', 'Thailand'],
    ['vietnam', 'Vietnam'], ['pakistan', 'Pakistan'], ['bangladesh', 'Bangladesh'],
    ['uae', 'UAE'], ['united arab', 'UAE'], ['israel', 'Israel'],
    ['south africa', 'S. Africa'], ['nigeria', 'Nigeria'], ['kenya', 'Kenya'],
    ['worldwide', 'Worldwide'], ['global', 'Worldwide'], ['anywhere', 'Worldwide'],
  ];

  const _jobCountry = (j) => {
    const loc = (' ' + (j.location || '') + ' ').toLowerCase();
    for (const [key, display] of _COUNTRY_MAP) {
      if (loc.includes(key)) return display;
    }
    return '—';
  };

  const _modePill = (mode) => {
    const cfg = {
      Remote:  { bg: 'rgba(16,185,129,0.12)', color: '#34d399', border: 'rgba(16,185,129,0.3)' },
      Hybrid:  { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.3)' },
      Onsite:  { bg: 'rgba(99,102,241,0.12)', color: '#818cf8', border: 'rgba(99,102,241,0.3)' },
    }[mode] || { bg: 'rgba(100,116,139,0.1)', color: 'var(--muted)', border: 'transparent' };
    return { fontSize: '0.68rem', fontWeight: 700, padding: '0.15rem 0.45rem', borderRadius: 20,
             background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
             whiteSpace: 'nowrap', letterSpacing: '0.03em' };
  };

  const SORT_COLS = [
    { key: 'score',       label: 'Score',    sortable: true,  width: '64px' },
    { key: 'title',       label: 'Title',    sortable: true },
    { key: 'company',     label: 'Company',  sortable: true,  cls: 'hide-sm' },
    { key: 'mode',        label: 'Mode',     sortable: false, cls: 'hide-md', width: '80px' },
    { key: 'country',     label: 'Country',  sortable: false, cls: 'hide-md', width: '90px' },
    { key: 'salary',      label: 'Salary',   sortable: true,  cls: 'hide-sm' },
    { key: 'updated_at',  label: 'Updated',  sortable: true,  cls: 'hide-sm' },
    { key: 'actions',     label: '',         sortable: false, width: '1%' },
  ];

  const toggleSort = (key) => {
    if (!key) return;
    if (sortBy === key) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortBy(key); setSortDir('desc'); }
    setPage(1);
  };

  const [debouncedQ, setDebouncedQ] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(searchQ), 350);
    return () => clearTimeout(t);
  }, [searchQ]);

  const refreshCounts = useCallback(() => {
    api.get('/api/jobs/tab-counts').then(r => setTabCounts(r));
  }, []);

  const MAX_SELECT = 10;
  const appliedStatuses = ['applied', 'interview', 'offer'];

  const PREDEFINED_REASONS = [
    'Salary too low',
    'Location not suitable',
    'Role mismatch — not what I do',
    'Company concerns',
    'Too senior / too junior',
    'Already applied elsewhere',
    'Poor job description',
    'Contract / freelance only',
  ];

  const [niModal, setNiModal] = useState(null);
  const [niReason, setNiReason] = useState('');
  const [niOtherText, setNiOtherText] = useState('');
  const [niSavedReasons, setNiSavedReasons] = useState([]);
  const [niSaving, setNiSaving] = useState(false);

  const [skipReasons, setSkipReasons] = useState([]);
  const [showSkipPanel, setShowSkipPanel] = useState(false);

  const loadSkipKeywords = useCallback(() => {
    api.get('/api/jobs/skip-keywords').then(r => {
      setSkipReasons(r.custom_reasons || []);
    });
  }, []);

  const removeSkipReason = async (reason) => {
    const res = await api.post('/api/jobs/not-interested-reasons/delete', { reason });
    setNiSavedReasons(res.reasons || []);
    loadSkipKeywords();
    loadJobs();
    showToast(`Skip topic "${reason}" removed`, 'success');
  };

  useEffect(() => {
    api.get('/api/jobs/not-interested-reasons').then(r => setNiSavedReasons(r.reasons || []));
    loadSkipKeywords();
    refreshCounts();
  }, []);

  const openNiModal = (job) => {
    setNiModal(job);
    setNiReason('');
    setNiOtherText('');
  };

  const submitNotInterested = async () => {
    if (!niReason) return;
    setNiSaving(true);
    let finalReason = niReason === '__other__' ? niOtherText.trim() : niReason;
    if (!finalReason) { setNiSaving(false); return; }

    if (niReason === '__other__' && finalReason) {
      const res = await api.post('/api/jobs/not-interested-reasons', { reason: finalReason });
      setNiSavedReasons(res.reasons || niSavedReasons);
    }

    const removedId = niModal.id;
    await api.post(`/api/jobs/${removedId}/status`, { status: 'not_interested', notes: finalReason });
    showToast(`Marked as Not Interested: "${finalReason}"`, 'success');
    setNiModal(null);
    setNiSaving(false);
    setJobPanel(null);
    setJobs(prev => prev.filter(x => x.id !== removedId));
    setTotal(prev => Math.max(0, prev - 1));
    refreshCounts();
    loadSkipKeywords();
  };

  const [clModal, setClModal] = useState(null);
  const openCoverLetter = async (job) => {
    setClModal({ job, letter: job.cover_letter || '', loading: !job.cover_letter });
    if (!job.cover_letter) {
      const res = await api.post(`/api/jobs/${job.id}/cover-letter`);
      setClModal(m => m && m.job.id === job.id ? { ...m, letter: res.cover_letter || '', loading: false } : m);
      setJobs(prev => prev.map(j => j.id === job.id ? { ...j, cover_letter: res.cover_letter } : j));
    }
  };

  const copyCoverLetter = (text) => {
    navigator.clipboard.writeText(text).then(() => showToast('Cover letter copied!', 'success'));
  };

  const [missingModal, setMissingModal] = useState(null);
  const [missingValues, setMissingValues] = useState({});
  const [applyResults, setApplyResults] = useState(null);
  const [copiedIdx, setCopiedIdx] = useState(null);

  const _showApplyResults = (details) => {
    setApplyResults(details);
    setSelected(new Set());
  };

  const _markApplied = async (item) => {
    await api.post(`/api/jobs/${item.id}/status`, { status: 'applied' });
    setApplyResults(prev => prev.filter(x => x.id !== item.id));
    setJobs(prev => prev.filter(x => x.id !== item.id));
    setTotal(prev => Math.max(0, prev - 1));
    refreshCounts();
    showToast(`✓ ${item.title} marked as Applied`, 'success');
  };

  const _copyLetter = async (letter, idx) => {
    try { await navigator.clipboard.writeText(letter); } catch(e) {}
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const submitMissingAndApply = async () => {
    const res = await api.post('/api/auto-apply', {
      job_ids: missingModal.jobIds,
      profile_patch: missingValues,
    });
    if (res.needs_info) {
      showToast('Please fill in all required fields.', 'error');
      return;
    }
    setMissingModal(null);
    setMissingValues({});
    _showApplyResults(res.details || []);
  };

  const loadJobs = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set('tab', tab);
    if (filters.status && tab === 'applied' && appliedStatuses.includes(filters.status)) {
      params.set('status', filters.status);
    } else if (filters.status && tab === 'not_applied' && !appliedStatuses.includes(filters.status) && filters.status !== 'not_interested') {
      params.set('status', filters.status);
    }
    if (filters.min_score) params.set('min_score', filters.min_score);
    if (debouncedQ.trim()) params.set('search', debouncedQ.trim());
    if (sortBy) { params.set('sort_by', sortBy); params.set('sort_dir', sortDir); }
    params.set('page', page);
    params.set('per_page', perPage);
    api.get(`/api/jobs?${params}`).then(res => {
      let filtered = (res && res.jobs) ? res.jobs : [];
      setTotal((res && res.total) || 0);
      if (filters.salary === 'has_salary') {
        filtered = filtered.filter(job => job.salary && job.salary.trim() && job.salary !== '-');
      } else if (filters.salary) {
        const minSal = parseInt(filters.salary);
        filtered = filtered.filter(job => {
          if (!job.salary) return false;
          const nums = job.salary.match(/[\d,]+/g);
          if (!nums) return false;
          const maxNum = Math.max(...nums.map(n => parseInt(n.replace(/,/g, ''))));
          return maxNum >= minSal;
        });
      }
      setJobs(filtered);
      setLoading(false);
      refreshCounts();
    }).catch(() => { setJobs([]); setLoading(false); });
  }, [filters, page, perPage, tab, debouncedQ, sortBy, sortDir, refreshCounts]);

  const hasInitialLoad = useRef(false);
  useEffect(() => {
    if (isVisible) {
      if (!hasInitialLoad.current) {
        hasInitialLoad.current = true;
        setLoading(true);
      }
      loadJobs();
    }
  }, [loadJobs, isVisible]);

  // Live updates: refetch when the server pushes a jobs_changed event.
  useEffect(() => {
    if (!isVisible) return undefined;
    const offJobs = sse.subscribe('jobs_changed', () => {
      loadJobs();
      api.get('/api/jobs/tab-counts').then(r => setTabCounts(r)).catch(() => {});
    });
    return () => { offJobs(); };
  }, [loadJobs, isVisible]);

  const totalPages = Math.ceil(total / perPage);

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < MAX_SELECT) next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (selected.size > 0) { setSelected(new Set()); return; }
    const ids = new Set();
    for (const j of jobs) { if (j.status !== 'applied' && ids.size < MAX_SELECT) ids.add(j.id); }
    setSelected(ids);
  };

  const [applying, setApplying] = useState(false);

  const applySelected = async () => {
    if (selected.size === 0) return;
    if (!confirm(`Mark ${selected.size} job(s) as applied?`)) return;
    const res = await api.post('/api/apply', { job_ids: [...selected] });
    showToast(`Marked ${res.applied} job(s) as applied!`, 'success');
    setSelected(new Set());
    loadJobs();
  };

  const autoApplySelected = async () => {
    if (selected.size === 0) return;
    if (!confirm(`Auto-apply to ${selected.size} job(s)?\n\nThis will:\n1. Generate personalised AI cover letters\n2. Show each job with its cover letter\n3. You open each job link & paste the letter\n4. Mark as Applied once submitted\n\nContinue?`)) return;
    setApplying(true);
    showToast('Generating personalised cover letters...', 'warning');
    try {
      const res = await api.post('/api/auto-apply', { job_ids: [...selected] });

      if (res.needs_info) {
        setApplying(false);
        setMissingModal({ missing: res.missing || [], jobIds: [...selected] });
        const init = {};
        (res.missing || []).forEach(f => { init[f.field] = ''; });
        setMissingValues(init);
        return;
      }

      _showApplyResults(res.details || []);
      showToast(`${res.details?.length || 0} cover letter(s) ready — open each job and apply!`, 'success');
    } catch (err) {
      showToast('Auto-apply failed. Please try again.', 'error');
    }
    setApplying(false);
  };

  return (
    <div style={styles.container}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '1.5rem' }}>
          Jobs <ProBadge tier={tier} />
        </h1>
        <span style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>
          {total > 0 ? `${((page-1)*perPage)+1}–${Math.min(page*perPage, total)} of ${total} jobs` : '0 jobs'}
        </span>
      </div>

      {isFree && (
        <div style={{ marginBottom: '1rem' }}>
          <UpgradeBanner
            title={`You're on the Free plan — ${tierData?.usage?.jobs_visible ?? 0}/${tierData?.limits?.jobs_visible ?? 5} jobs viewed this month`}
            body="Upgrade to Pro for unlimited job views, unlimited applications, and unlimited cover letters."
            onUpgrade={() => window.kalibrUpgrade && window.kalibrUpgrade()}
          />
        </div>
      )}

      <div style={{ display: 'flex', gap: '0', marginBottom: '1rem', borderBottom: '2px solid var(--border)' }}>
        {[
          { key: 'not_applied',    label: 'Not Applied',    color: 'var(--accent2)' },
          { key: 'saved',          label: 'Saved',          color: '#fbbf24'        },
          { key: 'applied',        label: 'Applied',        color: 'var(--green2)'  },
          { key: 'not_interested', label: 'Not Interested', color: 'var(--red2)'    },
          { key: 'history',        label: 'History',        color: '#94a3b8'        },
        ].map(t => {
          const count = tabCounts[t.key];
          return (
            <button key={t.key} onClick={() => { setTab(t.key); setPage(1); setSelected(new Set()); setFilters({ status: '', min_score: 0, salary: '' }); setSortBy(''); setSortDir('desc'); }}
              style={{
                padding: '0.6rem 1.25rem', border: 'none', cursor: 'pointer', fontSize: '0.92rem', fontWeight: 600,
                background: 'none', color: tab === t.key ? t.color : 'var(--muted)',
                borderBottom: tab === t.key ? `2px solid ${t.color}` : '2px solid transparent',
                marginBottom: '-2px', display: 'flex', alignItems: 'center', gap: '0.4rem',
              }}>
              {t.label}
              {count !== null && (
                <span style={{
                  fontSize: '0.72rem', fontWeight: 700, lineHeight: 1,
                  padding: '0.15rem 0.45rem', borderRadius: 20,
                  background: tab === t.key ? t.color : 'var(--bg3)',
                  color: tab === t.key ? 'var(--bg)' : 'var(--muted)',
                  minWidth: 20, textAlign: 'center',
                }}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {showSkipPanel && tab === 'not_applied' && (
        <div style={{ marginBottom: '0.75rem', background: 'var(--bg2)', border: '1px solid rgba(220,38,38,0.3)', borderRadius: 10, padding: '0.85rem 1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <div>
              <h4 style={{ fontSize: '0.85rem', color: '#f87171', margin: 0 }}>Skip Topics</h4>
              <p style={{ fontSize: '0.75rem', color: 'var(--muted)', margin: '0.2rem 0 0' }}>Jobs whose title or description matches these reasons are excluded from future searches.</p>
            </div>
            <button onClick={() => setShowSkipPanel(false)} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '1.1rem', lineHeight: 1, flexShrink: 0 }}>×</button>
          </div>
          {skipReasons.length === 0 ? (
            <p style={{ fontSize: '0.82rem', color: 'var(--muted)', margin: 0 }}>No custom skip topics yet. Skip a job with your own reason to add one.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.6rem' }}>
              {skipReasons.map(reason => (
                <div key={reason} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: '0.45rem 0.75rem', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text2)', flex: 1 }}>{reason}</span>
                  <button onClick={() => removeSkipReason(reason)}
                    title="Remove — matching jobs will appear again in next search"
                    style={{ background: 'rgba(220,38,38,0.12)', border: '1px solid rgba(220,38,38,0.3)', borderRadius: 6, color: '#f87171', cursor: 'pointer', fontSize: '0.75rem', padding: '0.2rem 0.55rem', flexShrink: 0, whiteSpace: 'nowrap' }}>
                    ✕ Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ position: 'relative', marginBottom: '0.9rem' }}>
        <span style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', fontSize: '0.95rem', pointerEvents: 'none', color: 'var(--muted)' }}>🔍</span>
        <input
          type="text"
          value={searchQ}
          onChange={e => { setSearchQ(e.target.value); setPage(1); }}
          placeholder="Search jobs by title, company, location, or skill…"
          style={{ ...styles.input, paddingLeft: '2.2rem', paddingRight: searchQ ? '2.2rem' : '0.75rem', marginBottom: 0, width: '100%', fontSize: '0.92rem' }}
        />
        {searchQ && (
          <button onClick={() => { setSearchQ(''); setPage(1); }}
            style={{ position: 'absolute', right: '0.5rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '1.1rem', lineHeight: 1, padding: '0.15rem' }}>×</button>
        )}
      </div>

      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {tab === 'not_applied' && (
          <select style={styles.select} value={filters.status} onChange={e => { setPage(1); setFilters(f => ({ ...f, status: e.target.value })); }}>
            <option value="">All Statuses</option>
            {['new', 'previous', 'saved', 'rejected'].map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
        )}
        {tab === 'applied' && (
          <select style={styles.select} value={filters.status} onChange={e => { setPage(1); setFilters(f => ({ ...f, status: e.target.value })); }}>
            <option value="">All Applied</option>
            {['applied', 'interview', 'offer'].map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
        )}
        <select style={styles.select} value={filters.min_score} onChange={e => { setPage(1); setFilters(f => ({ ...f, min_score: parseFloat(e.target.value) })); }}>
          <option value="0">Any Score</option>
          <option value="0.3">30%+</option>
          <option value="0.5">50%+</option>
          <option value="0.7">70%+</option>
        </select>
        <select style={styles.select} value={filters.salary} onChange={e => { setPage(1); setFilters(f => ({ ...f, salary: e.target.value })); }}>
          <option value="">Any Salary</option>
          <option value="has_salary">Has Salary Info</option>
          <option value="50000">$50k+</option>
          <option value="80000">$80k+</option>
          <option value="100000">$100k+</option>
          <option value="150000">$150k+</option>
          <option value="200000">$200k+</option>
        </select>
        <button style={{ ...styles.btn, ...styles.btnSm, ...styles.btnSecondary }} onClick={() => { setPage(1); setFilters({ status: '', min_score: 0, salary: '' }); }}>Reset</button>
        <select style={{ ...styles.select, minWidth: 110 }} value={perPage} onChange={e => { setPerPage(Number(e.target.value)); setPage(1); }} title="Rows per page">
          {[30, 40, 50, 75, 100].map(n => <option key={n} value={n}>{n} / page</option>)}
        </select>
        {tab !== 'history' && (
          <button style={{ ...styles.btn, ...styles.btnSm, ...styles.btnDanger }} onClick={async () => {
            if (!confirm('Clear all non-applied jobs from view? Their records are kept to prevent re-applying. Applied, Interview, and Offer jobs are unaffected.')) return;
            const res = await api.post('/api/jobs/clear', {});
            showToast(`Cleared ${res.cleared} jobs from view. Status history preserved.`, 'success');
            setPage(1); loadJobs();
          }}>Clear Old Jobs</button>
        )}
      </div>

      {tab === 'history' && !loading && jobs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginBottom: '1.5rem' }}>
          {jobs.map(j => {
            const isCleared = j.cleared;
            const statusColor = {
              applied: '#6ee7b7', interview: '#d8b4fe', offer: '#86efac',
              rejected: '#fca5a5', not_interested: '#fca5a5',
            }[j.status] || '#94a3b8';
            const statusBg = {
              applied: '#065f46', interview: '#581c87', offer: '#14532d',
              rejected: '#7f1d1d', not_interested: '#7f1d1d',
            }[j.status] || '#1e293b';
            const displayStatus = isCleared && j.status !== 'not_interested' && !['applied','interview','offer','rejected'].includes(j.status)
              ? 'cleared' : j.status;
            return (
              <div key={j.id} style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '0.85rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <a href={j.url} target="_blank" rel="noopener noreferrer"
                      style={{ fontWeight: 700, color: '#93c5fd', fontSize: '0.95rem', textDecoration: 'none', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={j.title}>{j.title}</a>
                    <span style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>{String(j.company || '')}{j.location ? ` · ${j.location}` : ''}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
                    <Badge score={j.score} />
                    <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '0.15rem 0.55rem', borderRadius: 20, background: statusBg, color: statusColor, border: `1px solid ${statusColor}33`, textTransform: 'capitalize' }}>
                      {displayStatus}
                    </span>
                  </div>
                </div>
                {j.notes && (
                  <div style={{ fontSize: '0.82rem', color: '#cbd5e1', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '0.4rem 0.65rem', marginTop: '0.15rem' }}>
                    <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginRight: '0.4rem' }}>Note:</span>
                    {j.notes}
                  </div>
                )}
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)', display: 'flex', gap: '1rem', marginTop: '0.1rem' }}>
                  {j.applied_at && <span>Applied: {fmtDate(j.applied_at?.slice(0,10))}</span>}
                  {j.updated_at && <span>Updated: {fmtDate(j.updated_at?.slice(0,10))}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {tab !== 'history' && <div style={{ ...styles.card, padding: 0, overflow: 'hidden', marginBottom: selected.size > 0 ? 70 : 0 }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="jobs-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr>
              {tab === 'not_applied' && (
                <th style={{ padding: '0.6rem', width: 40, borderBottom: '1px solid var(--border)', background: 'var(--bg)', color: 'var(--muted)', fontSize: '0.78rem' }}>
                  <input type="checkbox" checked={selected.size > 0} onChange={selectAll} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                </th>
              )}
              {SORT_COLS.map(({ key, label, cls, sortable, width }) => {
                const isActive = sortBy === key;
                const arrow = !sortable ? '' : isActive ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ' ↕';
                return (
                  <th key={key} className={cls || ''}
                    onClick={sortable ? () => toggleSort(key) : undefined}
                    style={{
                      padding: '0.5rem 0.6rem', textAlign: 'left',
                      borderBottom: '1px solid var(--border)',
                      background: isActive ? 'var(--hover)' : 'var(--bg)',
                      color: isActive ? 'var(--accent)' : 'var(--muted)',
                      fontSize: '0.72rem', textTransform: 'uppercase',
                      letterSpacing: '0.05em', whiteSpace: 'nowrap',
                      cursor: sortable ? 'pointer' : 'default',
                      userSelect: 'none',
                      ...(width ? { width } : {}),
                    }}>
                    {label}{arrow}
                  </th>
                );
              })}
            </tr></thead>
            <tbody>
              {jobs.map(j => j.blurred ? (
                <tr key={j.id} style={{ borderBottom: '1px solid var(--border)', background: 'rgba(124,58,237,0.04)', cursor: 'not-allowed', userSelect: 'none' }}>
                  <td colSpan={9} style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', filter: 'blur(0.5px)', opacity: 0.85 }}>
                      <span style={{ fontSize: '1.1rem' }}>🔒</span>
                      <span style={{ flex: 1, color: '#cbd5e1', fontStyle: 'italic' }}>
                        Premium job — upgrade to Pro to unlock this and unlimited matches
                      </span>
                      <span style={{ background: '#1e293b', color: '#475569', padding: '0.2rem 0.7rem', borderRadius: 8, fontSize: '0.75rem', letterSpacing: '0.04em' }}>HIDDEN</span>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={j.id} onClick={async () => {
                  setJobPanel(j);
                  setJobPanelLoading(true);
                  try {
                    const full = await api.get(`/api/jobs/${j.id}`);
                    if (full && !full.error) setJobPanel(full);
                    else if (full?.blurred) {
                      showToast(full.message || 'Upgrade to Pro to view more jobs', 'warning');
                      setJobPanel(null);
                    }
                  } finally { setJobPanelLoading(false); }
                }} style={{ borderBottom: '1px solid var(--border)', background: selected.has(j.id) ? 'rgba(37,99,235,0.08)' : 'transparent', transition: 'background 0.1s', cursor: 'pointer' }}>
                  {tab === 'not_applied' && (
                    <td style={{ padding: '0.6rem', textAlign: 'center' }} onClick={e => e.stopPropagation()}>
                      <input type="checkbox" checked={selected.has(j.id)} disabled={j.status === 'applied'} onChange={() => toggleSelect(j.id)}
                             style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: j.status === 'applied' ? 'not-allowed' : 'pointer' }} />
                    </td>
                  )}
                  <td style={{ padding: '0.5rem 0.6rem' }}><Badge score={j.score} /></td>
                  <td style={{ padding: '0.5rem 0.6rem', maxWidth: 0, width: '40%' }}>
                    <span onClick={e => { e.stopPropagation(); setJobPanel(j); }} style={{ fontWeight: 600, cursor: 'pointer', color: '#93c5fd', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={j.title}>{j.title}</span>
                    {(() => {
                      // Required years: prefer backend value if set, fallback to inline regex.
                      const reqYears = j.required_years
                        ?? (j.description || j.title || '').match(/(\d+)\+?\s*(?:to\s*\d+\s*)?years?\s*(?:of\s*)?(?:experience|exp)/i)?.[1]
                        ?? null;
                      const tags = (j.tags || []).slice(0, 4);
                      if (!reqYears && tags.length === 0) return null;
                      return (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginTop: '0.3rem', alignItems: 'center' }} onClick={e => e.stopPropagation()}>
                          {reqYears && (
                            <span title={`Requires ${reqYears}+ years of experience`} style={{ fontSize: '0.7rem', color: '#fcd34d', background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)', padding: '0.08rem 0.4rem', borderRadius: 8, fontWeight: 600, whiteSpace: 'nowrap' }}>
                              🎓 {reqYears}+ yrs
                            </span>
                          )}
                          {tags.map((t, i) => (
                            <span key={i} title={t} style={{ fontSize: '0.7rem', color: '#93c5fd', background: 'rgba(37,99,235,0.12)', border: '1px solid rgba(37,99,235,0.25)', padding: '0.08rem 0.4rem', borderRadius: 8, whiteSpace: 'nowrap' }}>
                              {String(t).length > 18 ? String(t).slice(0, 17) + '…' : t}
                            </span>
                          ))}
                          {(j.tags || []).length > 4 && (
                            <span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>+{(j.tags || []).length - 4}</span>
                          )}
                        </div>
                      );
                    })()}
                  </td>
                  <td className="hide-sm" style={{ padding: '0.5rem 0.6rem', fontSize: '0.83rem', maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{String(j.company || '').substring(0, 20)}</td>
                  <td className="hide-md" style={{ padding: '0.5rem 0.6rem' }}>
                    <span style={_modePill(_jobMode(j))}>{_jobMode(j)}</span>
                  </td>
                  <td className="hide-md" style={{ padding: '0.5rem 0.6rem', fontSize: '0.8rem', color: 'var(--muted)', whiteSpace: 'nowrap' }} title={j.location || ''}>
                    {_jobCountry(j)}
                  </td>
                  <td className="hide-sm" style={{ padding: '0.5rem 0.6rem', fontSize: '0.82rem' }}>
                    {(() => {
                      const fs = formatSalary(j.salary, j.location);
                      if (fs) return <span style={{ color: 'var(--green2)', fontWeight: 600 }}>{fs}</span>;
                      if (j.salary && j.salary.trim()) return <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>{j.salary.substring(0, 22)}</span>;
                      return <span style={{ color: '#475569' }}>—</span>;
                    })()}
                  </td>
                  <td style={{ padding: '0.5rem 0.6rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', alignItems: 'flex-start' }}>
                      <StatusBadge status={j.status} />
                      {j.followup_due && <span title={`Applied ${j.days_since_applied} days ago — consider following up`} style={{ fontSize: '0.66rem', color: '#fde68a', background: 'rgba(234,179,8,0.18)', border: '1px solid rgba(234,179,8,0.35)', padding: '0.1rem 0.4rem', borderRadius: 8, whiteSpace: 'nowrap', cursor: 'default' }}>⏰ Follow up ({j.days_since_applied}d)</span>}
                      {j.interview_details?.date && <span title={`Interview: ${j.interview_details.round || 'Scheduled'} on ${j.interview_details.date}`} style={{ fontSize: '0.68rem', color: '#d8b4fe', background: '#2d1b4e', padding: '0.1rem 0.4rem', borderRadius: 8, whiteSpace: 'nowrap' }}>📅 {j.interview_details.date}</span>}
                      {j.offer_details?.salary && <span title={`Offer: ${j.offer_details.salary}`} style={{ fontSize: '0.68rem', color: '#86efac', background: '#14532d', padding: '0.1rem 0.4rem', borderRadius: 8, whiteSpace: 'nowrap' }}>💰 {j.offer_details.salary}</span>}
                    </div>
                  </td>
                  <td className="action-cell" style={{ padding: '0.4rem 0.6rem', width: '1%' }} onClick={e => e.stopPropagation()}>
                    {tab === 'not_interested' ? (
                      <div className="action-btns">
                        <a href={getApplyUrl(j)} target="_blank" rel="noopener"
                          title="Apply Directly"
                          className="action-btn"
                          style={{ background: 'var(--bg3)', color: 'var(--muted)', textDecoration: 'none' }}>
                          ↗<span className="btn-label">Apply</span>
                        </a>
                      </div>
                    ) : tab === 'applied' ? (
                      <div className="action-btns">
                        <a href={getApplyUrl(j)} target="_blank" rel="noopener"
                          title="Apply Directly"
                          className="action-btn"
                          style={{ background: 'var(--bg3)', color: 'var(--muted)', textDecoration: 'none' }}>
                          ↗<span className="btn-label">Apply</span>
                        </a>
                        <button
                          title="Track Interview / Offer"
                          onClick={e => { e.stopPropagation(); navigate(`job/${j.id}`); }}
                          className="action-btn"
                          style={{ background: j.status === 'offer' ? 'rgba(245,158,11,0.18)' : 'rgba(124,58,237,0.18)', color: j.status === 'offer' ? '#fde68a' : '#c4b5fd', border: `1px solid ${j.status === 'offer' ? 'rgba(245,158,11,0.35)' : 'rgba(124,58,237,0.35)'}` }}>
                          {j.status === 'offer' ? '💰' : '📅'}<span className="btn-label">{j.status === 'offer' ? 'Offer' : 'Interview'}</span>
                        </button>
                        <button
                          title={j.cover_letter ? 'View Cover Letter' : 'Generate Cover Letter'}
                          onClick={e => { e.stopPropagation(); openCoverLetter(j); }}
                          className="action-btn"
                          style={{ background: 'rgba(124,58,237,0.22)', color: '#c4b5fd', border: '1px solid rgba(124,58,237,0.4)' }}>
                          📄<span className="btn-label">Cover Letter</span>
                        </button>
                      </div>
                    ) : tab === 'saved' ? (
                      <div className="action-btns">
                        <a href={getApplyUrl(j)} target="_blank" rel="noopener"
                          onClick={e => e.stopPropagation()}
                          title="Apply Directly"
                          className="action-btn"
                          style={{ background: 'var(--accent)', color: '#fff', textDecoration: 'none' }}>
                          ↗<span className="btn-label">Apply</span>
                        </a>
                        <button
                          title="Mark as Applied"
                          onClick={async (e) => {
                            e.stopPropagation();
                            await api.post(`/api/jobs/${j.id}/status`, { status: 'applied' });
                            setJobs(prev => prev.filter(x => x.id !== j.id));
                            setTotal(prev => Math.max(0, prev - 1));
                            refreshCounts();
                            showToast('Moved to Applied ✓', 'success');
                          }}
                          className="action-btn"
                          style={{ background: 'var(--green)', color: '#fff' }}>
                          ✓<span className="btn-label">Applied</span>
                        </button>
                        <button
                          title="Unsave — move back to Not Applied"
                          onClick={async (e) => {
                            e.stopPropagation();
                            await api.post(`/api/jobs/${j.id}/unsave`);
                            setJobs(prev => prev.filter(x => x.id !== j.id));
                            setTotal(prev => Math.max(0, prev - 1));
                            refreshCounts();
                            showToast('Removed from Saved', 'info');
                          }}
                          className="action-btn"
                          style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.35)' }}>
                          🔖<span className="btn-label">Unsave</span>
                        </button>
                        <button
                          title="Not Interested"
                          onClick={e => { e.stopPropagation(); openNiModal(j); }}
                          className="action-btn"
                          style={{ background: 'rgba(220,38,38,0.15)', color: 'var(--red2)', border: '1px solid rgba(220,38,38,0.35)' }}>
                          ✕<span className="btn-label">Skip</span>
                        </button>
                      </div>
                    ) : (
                      <div className="action-btns">
                        <a href={getApplyUrl(j)} target="_blank" rel="noopener"
                          onClick={e => e.stopPropagation()}
                          title="Apply Directly"
                          className="action-btn"
                          style={{ background: 'var(--accent)', color: '#fff', textDecoration: 'none' }}>
                          ↗<span className="btn-label">Apply</span>
                        </a>
                        <button
                          title="Save for later"
                          onClick={async (e) => {
                            e.stopPropagation();
                            await api.post(`/api/jobs/${j.id}/save`);
                            setJobs(prev => prev.filter(x => x.id !== j.id));
                            setTotal(prev => Math.max(0, prev - 1));
                            refreshCounts();
                            showToast('Job saved 🔖', 'success');
                          }}
                          className="action-btn"
                          style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.35)' }}>
                          🔖<span className="btn-label">Save</span>
                        </button>
                        <button
                          title="Mark as Applied"
                          disabled={j._marking}
                          onClick={async (e) => {
                            e.stopPropagation();
                            j._marking = true;
                            e.currentTarget.disabled = true;
                            await api.post(`/api/jobs/${j.id}/status`, { status: 'applied' });
                            setJobs(prev => prev.filter(x => x.id !== j.id));
                            setTotal(prev => Math.max(0, prev - 1));
                            refreshCounts();
                            showToast('Moved to Applied ✓', 'success');
                          }}
                          className="action-btn"
                          style={{ background: 'var(--green)', color: '#fff' }}>
                          ✓<span className="btn-label">Applied</span>
                        </button>
                        <button
                          title={j.cover_letter ? 'View Cover Letter' : 'Generate Cover Letter'}
                          onClick={e => { e.stopPropagation(); openCoverLetter(j); }}
                          className="action-btn"
                          style={{ background: 'rgba(124,58,237,0.22)', color: '#c4b5fd', border: '1px solid rgba(124,58,237,0.4)' }}>
                          📄<span className="btn-label">{j.cover_letter ? 'Cover Letter' : 'Gen CL'}</span>
                        </button>
                        <button
                          title="Not Interested"
                          onClick={e => { e.stopPropagation(); openNiModal(j); }}
                          className="action-btn"
                          style={{ background: 'rgba(220,38,38,0.15)', color: 'var(--red2)', border: '1px solid rgba(220,38,38,0.35)' }}>
                          ✕<span className="btn-label">Skip</span>
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>}

      {loading && <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '2rem' }}>Loading...</p>}
      {!loading && jobs.length === 0 && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--muted)' }}>
          <p style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>No jobs found.</p>
          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
            <button style={{ ...styles.btn, ...styles.btnSecondary }} onClick={loadJobs}>↻ Refresh</button>
            <button style={{ ...styles.btn, ...styles.btnPrimary }} onClick={() => navigate('search')}>Run a Search</button>
          </div>
        </div>
      )}

      {total > perPage && (() => {
        const btnStyle = (active, disabled) => ({
          ...styles.btn, ...styles.btnSm,
          ...(active ? styles.btnPrimary : styles.btnSecondary),
          opacity: disabled ? 0.35 : 1,
          minWidth: 36, padding: '0.35rem 0.6rem',
          fontWeight: active ? 700 : 400,
        });
        const pageNums = [];
        for (let i = 1; i <= totalPages; i++) {
          if (i === 1 || i === totalPages || (i >= page - 2 && i <= page + 2)) pageNums.push(i);
          else if (pageNums[pageNums.length - 1] !== '…') pageNums.push('…');
        }
        return (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.35rem', padding: '1.25rem 0', flexWrap: 'wrap' }}>
            <button onClick={() => setPage(1)} disabled={page === 1} style={btnStyle(false, page === 1)}>«</button>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} style={btnStyle(false, page === 1)}>‹</button>
            {pageNums.map((n, i) => n === '…'
              ? <span key={`ellipsis-${i}`} style={{ color: 'var(--muted)', padding: '0 0.2rem', userSelect: 'none' }}>…</span>
              : <button key={n} onClick={() => setPage(n)} style={btnStyle(n === page, false)}>{n}</button>
            )}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} style={btnStyle(false, page === totalPages)}>›</button>
            <button onClick={() => setPage(totalPages)} disabled={page === totalPages} style={btnStyle(false, page === totalPages)}>»</button>
            <span style={{ color: 'var(--muted)', fontSize: '0.8rem', marginLeft: '0.5rem' }}>
              {((page - 1) * perPage) + 1}–{Math.min(page * perPage, total)} of {total}
            </span>
          </div>
        );
      })()}

      {selected.size > 0 && (
        <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, background: 'var(--bg2)', borderTop: '2px solid var(--accent)', padding: '0.75rem 2rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 100, boxShadow: '0 -4px 20px rgba(0,0,0,0.5)', animation: 'fadeIn 0.2s' }}>
          <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--accent2)' }}>{selected.size} selected <span style={{ fontWeight: 400, color: 'var(--muted)' }}>(max {MAX_SELECT})</span></span>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <button style={{ ...styles.btn, ...styles.btnSecondary }} onClick={() => setSelected(new Set())}>Clear</button>
            <button style={{ ...styles.btn, ...styles.btnPrimary }} onClick={applySelected}>Mark Applied</button>
            <button style={{ ...styles.btn, background: 'linear-gradient(135deg, #059669, #2563eb)', color: '#fff', padding: '0.6rem 1.5rem', fontSize: '0.95rem' }} onClick={autoApplySelected} disabled={applying}>
              {applying ? 'Applying...' : `Auto-Apply ${selected.size} Job${selected.size > 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      )}

      {jobPanel && (() => {
        const j = jobPanel;
        const fmtSalary = formatSalary(j.salary, j.location);
        const currency = detectCurrency(j.salary || '', j.location || '');
        const expMatch = (j.description || j.title || '').match(/(\d+)\+?\s*(?:to\s*\d+\s*)?years?\s*(?:of\s*)?(?:experience|exp)/i)
                      || (j.description || '').match(/experience[^.]{0,20}(\d+)\+?\s*years?/i)
                      || (j.description || '').match(/minimum\s+(\d+)\s*years?/i);
        const reqYears = expMatch ? expMatch[1] : null;
        return (
          <div style={{ position: 'fixed', inset: 0, zIndex: 150, display: 'flex' }}
            onClick={e => { if (e.target === e.currentTarget) setJobPanel(null); }}>
            <div style={{ flex: 1, background: 'rgba(0,0,0,0.5)' }} onClick={() => setJobPanel(null)} />
            <div className="jobs-drawer" style={{ width: 520, maxWidth: '95vw', background: 'var(--bg2)', borderLeft: '1px solid var(--border)', height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 32px rgba(0,0,0,0.5)', animation: 'slideInRight 0.2s ease' }}>
              <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border)', position: 'sticky', top: 0, background: 'var(--bg2)', zIndex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.2rem', lineHeight: 1.3 }}>{j.title}</h2>
                    <p style={{ color: '#60a5fa', fontWeight: 600, fontSize: '0.95rem', marginBottom: '0.15rem' }}>{String(j.company || '')}</p>
                    <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{[j.location, fmtDate(j.date_posted)].filter(Boolean).join(' · ')}</p>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.4rem', flexShrink: 0 }}>
                    <Badge score={j.score} />
                    <StatusBadge status={j.status} />
                    <button onClick={() => setJobPanel(null)} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '1.3rem', lineHeight: 1, padding: 0 }}>×</button>
                  </div>
                </div>
              </div>

              <div style={{ padding: '1.25rem 1.5rem', flex: 1 }}>
                {fmtSalary ? (
                  <div style={{ background: 'rgba(5,150,105,0.12)', border: '1px solid rgba(5,150,105,0.3)', borderRadius: 10, padding: '0.75rem 1rem', marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--muted)', fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Salary</span>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ color: 'var(--green2)', fontWeight: 700, fontSize: '1.1rem' }}>{fmtSalary}</span>
                      {currency !== 'USD' && <span style={{ color: 'var(--muted)', fontSize: '0.75rem', display: 'block' }}>{currency}</span>}
                    </div>
                  </div>
                ) : (
                  <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: '0.65rem 1rem', marginBottom: '1rem' }}>
                    <span style={{ color: '#475569', fontSize: '0.88rem' }}>Salary not listed</span>
                  </div>
                )}

                <div style={{ marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Match Score</span>
                    <span style={{ fontSize: '0.88rem', fontWeight: 700, color: j.score >= 0.7 ? 'var(--green2)' : j.score >= 0.4 ? 'var(--yellow2)' : 'var(--red2)' }}>{Math.round((j.score || 0) * 100)}%</span>
                  </div>
                  <div style={{ background: 'var(--bg3)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: 6, width: `${Math.round((j.score || 0) * 100)}%`, background: j.score >= 0.7 ? 'var(--green)' : j.score >= 0.4 ? 'var(--yellow)' : 'var(--red)', transition: 'width 0.4s' }} />
                  </div>
                  {j.score_details && (
                    <div style={{ display: 'flex', gap: '1rem', marginTop: '0.4rem', fontSize: '0.78rem', color: 'var(--muted)' }}>
                      <span>Local: {Math.round((j.score_details.local_score || 0) * 100)}%</span>
                      {j.score_details.ai_score != null && <span>AI: {Math.round(j.score_details.ai_score * 100)}%</span>}
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '1rem' }}>
                  {j.job_type && <span style={{ background: 'var(--bg3)', color: 'var(--muted)', padding: '0.2rem 0.6rem', borderRadius: 20, fontSize: '0.78rem' }}>{j.job_type}</span>}
                  {j.date_posted && <span style={{ background: 'var(--bg3)', color: 'var(--muted)', padding: '0.2rem 0.6rem', borderRadius: 20, fontSize: '0.78rem' }}>📅 {fmtDate(j.date_posted)}</span>}
                  {reqYears && <span style={{ background: 'rgba(245,158,11,0.15)', color: '#fcd34d', padding: '0.2rem 0.6rem', borderRadius: 20, fontSize: '0.78rem', fontWeight: 600, border: '1px solid rgba(245,158,11,0.3)' }}>🎓 {reqYears}+ yrs exp required</span>}
                </div>

                {j.tags && j.tags.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <p style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.4rem' }}>Skills & Tags</p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                      {j.tags.map((t, i) => <span key={i} style={{ background: '#1e3a5f', color: '#93c5fd', padding: '0.2rem 0.6rem', borderRadius: 20, fontSize: '0.78rem' }}>{t}</span>)}
                    </div>
                  </div>
                )}

                {jobPanelLoading && <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginBottom: '1rem' }}>Loading full details…</p>}

                {j.description ? (
                  <div style={{ marginBottom: '1rem' }}>
                    <p style={{ fontSize: '0.78rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>📋 Job Description</p>
                    <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: '0.75rem 1rem', fontSize: '0.85rem', lineHeight: 1.75, color: '#cbd5e1', whiteSpace: 'pre-wrap' }}>
                      {j.description}
                    </div>
                  </div>
                ) : !jobPanelLoading && (
                  <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: '0.75rem 1rem', marginBottom: '1rem', color: 'var(--muted)', fontSize: '0.85rem' }}>
                    No description available. <a href={j.url} target="_blank" rel="noopener" style={{ color: 'var(--accent2)' }}>View on job site ↗</a>
                  </div>
                )}

                {j.notes && <div style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 8, padding: '0.6rem 0.9rem', fontSize: '0.85rem', color: 'var(--yellow2)', marginBottom: '1rem' }}>{j.notes}</div>}

                {j.interview_details?.date && (
                  <div style={{ background: 'rgba(124,58,237,0.1)', border: '1px solid rgba(124,58,237,0.3)', borderRadius: 8, padding: '0.75rem 1rem', marginBottom: '0.75rem' }}>
                    <p style={{ fontSize: '0.75rem', color: '#d8b4fe', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.35rem', fontWeight: 600 }}>Interview Scheduled</p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem 1.5rem', fontSize: '0.85rem', color: '#e2e8f0' }}>
                      {j.interview_details.round && <span><span style={{ color: 'var(--muted)' }}>Round: </span>{j.interview_details.round}</span>}
                      <span><span style={{ color: 'var(--muted)' }}>Date: </span>{j.interview_details.date}{j.interview_details.time ? ` at ${j.interview_details.time}` : ''}{j.interview_details.timezone ? ` ${j.interview_details.timezone}` : ''}</span>
                      {j.interview_details.platform && <span><span style={{ color: 'var(--muted)' }}>Via: </span>{j.interview_details.platform}</span>}
                      {j.interview_details.interviewer && <span><span style={{ color: 'var(--muted)' }}>With: </span>{j.interview_details.interviewer}</span>}
                    </div>
                    {j.interview_details.meeting_link && (
                      <a href={j.interview_details.meeting_link} target="_blank" rel="noopener" style={{ display: 'inline-block', marginTop: '0.5rem', fontSize: '0.82rem', color: '#a78bfa', textDecoration: 'none', fontWeight: 600 }}>🔗 Join Meeting →</a>
                    )}
                  </div>
                )}

                {j.offer_details?.salary && (
                  <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 8, padding: '0.75rem 1rem', marginBottom: '0.75rem' }}>
                    <p style={{ fontSize: '0.75rem', color: '#fde68a', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.35rem', fontWeight: 600 }}>Offer Received</p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem 1.5rem', fontSize: '0.85rem', color: '#e2e8f0' }}>
                      <span><span style={{ color: 'var(--muted)' }}>Salary: </span><strong style={{ color: '#86efac' }}>{j.offer_details.salary}</strong>{j.offer_details.currency ? ` ${j.offer_details.currency}` : ''}</span>
                      {j.offer_details.joining_date && <span><span style={{ color: 'var(--muted)' }}>Joining: </span>{j.offer_details.joining_date}</span>}
                      {j.offer_details.deadline && <span><span style={{ color: 'var(--muted)' }}>Deadline: </span>{j.offer_details.deadline}</span>}
                      {j.offer_details.location && <span><span style={{ color: 'var(--muted)' }}>Location: </span>{j.offer_details.location}</span>}
                    </div>
                    {j.offer_details.benefits && <p style={{ fontSize: '0.82rem', color: 'var(--muted)', marginTop: '0.35rem' }}>Benefits: {j.offer_details.benefits}</p>}
                  </div>
                )}
              </div>

              <div style={{ padding: '0.85rem 1rem', borderTop: '1px solid var(--border)', display: 'flex', gap: '0.4rem', background: 'var(--bg2)', position: 'sticky', bottom: 0 }}>
                <a href={getApplyUrl(j)} target="_blank" rel="noopener" onClick={e => e.stopPropagation()}
                  style={{ ...styles.btn, ...styles.btnPrimary, flex: 1, fontSize: '0.82rem', padding: '0.5rem 0.4rem', justifyContent: 'center', minWidth: 0, whiteSpace: 'nowrap' }}>↗ Apply</a>
                {getApplyUrl(j) !== j.url && j.url && (
                  <a href={j.url} target="_blank" rel="noopener" onClick={e => e.stopPropagation()}
                    style={{ ...styles.btn, flex: 1, background: 'var(--bg3)', color: 'var(--muted)', border: '1px solid var(--border)', fontSize: '0.82rem', padding: '0.5rem 0.4rem', justifyContent: 'center', minWidth: 0, whiteSpace: 'nowrap', textDecoration: 'none' }}>View Posting</a>
                )}
                <button onClick={() => openCoverLetter(j)}
                  style={{ ...styles.btn, flex: 1, background: 'rgba(124,58,237,0.2)', color: '#c4b5fd', border: '1px solid rgba(124,58,237,0.4)', fontSize: '0.82rem', padding: '0.5rem 0.4rem', minWidth: 0, whiteSpace: 'nowrap' }}>
                  {j.cover_letter ? '📄 Cover Letter' : '✨ Gen CL'}
                </button>
                {(j.status === 'interview' || j.status === 'offer' || j.status === 'applied') && (
                  <button onClick={() => { setJobPanel(null); navigate(`job/${j.id}`); }}
                    style={{ ...styles.btn, flex: 1, background: j.status === 'offer' ? 'rgba(245,158,11,0.15)' : 'rgba(124,58,237,0.15)', color: j.status === 'offer' ? '#fde68a' : '#d8b4fe', border: `1px solid ${j.status === 'offer' ? 'rgba(245,158,11,0.3)' : 'rgba(124,58,237,0.3)'}`, fontSize: '0.82rem', padding: '0.5rem 0.4rem', minWidth: 0, whiteSpace: 'nowrap' }}>
                    {j.status === 'offer' ? '💰 Offer' : '📅 Interview'}
                  </button>
                )}
                {tab === 'not_applied' && (
                  <button onClick={async () => { await api.post(`/api/jobs/${j.id}/save`); setJobPanel(null); setJobs(prev => prev.filter(x => x.id !== j.id)); setTotal(prev => Math.max(0, prev - 1)); refreshCounts(); showToast('Job saved 🔖', 'success'); }}
                    style={{ ...styles.btn, flex: 1, background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.35)', fontSize: '0.82rem', padding: '0.5rem 0.4rem', minWidth: 0, whiteSpace: 'nowrap' }}>🔖 Save</button>
                )}
                {tab === 'saved' && (
                  <button onClick={async () => { await api.post(`/api/jobs/${j.id}/unsave`); setJobPanel(null); setJobs(prev => prev.filter(x => x.id !== j.id)); setTotal(prev => Math.max(0, prev - 1)); refreshCounts(); showToast('Removed from Saved', 'info'); }}
                    style={{ ...styles.btn, flex: 1, background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.35)', fontSize: '0.82rem', padding: '0.5rem 0.4rem', minWidth: 0, whiteSpace: 'nowrap' }}>🔖 Unsave</button>
                )}
                {tab !== 'applied' && tab !== 'not_interested' && (<>
                  <button onClick={async () => { await api.post(`/api/jobs/${j.id}/status`, { status: 'applied' }); setJobPanel(null); setJobs(prev => prev.filter(x => x.id !== j.id)); setTotal(prev => Math.max(0, prev - 1)); refreshCounts(); showToast('Moved to Applied ✓', 'success'); }}
                    style={{ ...styles.btn, ...styles.btnSuccess, flex: 1, fontSize: '0.82rem', padding: '0.5rem 0.4rem', minWidth: 0, whiteSpace: 'nowrap' }}>✓ Applied</button>
                  <button onClick={() => { setJobPanel(null); openNiModal(j); }}
                    style={{ ...styles.btn, flex: 1, background: 'rgba(220,38,38,0.15)', color: 'var(--red2)', border: '1px solid rgba(220,38,38,0.3)', fontSize: '0.82rem', padding: '0.5rem 0.4rem', minWidth: 0, whiteSpace: 'nowrap' }}>✕ Skip</button>
                </>)}
              </div>
            </div>
          </div>
        );
      })()}

      {applyResults && applyResults.length > 0 && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 400, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}
          onClick={e => { if (e.target === e.currentTarget) setApplyResults(null); }}>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, width: '100%', maxWidth: 680, maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ fontSize: '1rem', margin: 0 }}>🚀 Auto-Apply — {applyResults.length} Job{applyResults.length > 1 ? 's' : ''}</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.78rem', margin: '0.2rem 0 0' }}>
                  For each job: copy the cover letter → open the job link → paste & submit → Mark Applied
                </p>
              </div>
              <button onClick={() => setApplyResults(null)} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '1.3rem', lineHeight: 1, padding: '0.2rem 0.4rem' }}>×</button>
            </div>
            <div style={{ overflowY: 'auto', flex: 1, padding: '0.75rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {applyResults.map((item, idx) => (
                <div key={item.id} style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: '0.9rem 1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.65rem' }}>
                    <div style={{ minWidth: 0 }}>
                      <p style={{ fontWeight: 700, fontSize: '0.92rem', margin: 0, color: '#93c5fd' }}>{item.title}</p>
                      <p style={{ color: 'var(--muted)', fontSize: '0.78rem', margin: '0.15rem 0 0' }}>{item.company}</p>
                    </div>
                    <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
                      <a href={item.url} target="_blank" rel="noopener"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 6, padding: '0.35rem 0.75rem', fontSize: '0.78rem', fontWeight: 600, textDecoration: 'none', cursor: 'pointer' }}>
                        ↗ Open Job
                      </a>
                      <button onClick={() => _markApplied(item)}
                        style={{ background: 'var(--green)', color: '#fff', border: 'none', borderRadius: 6, padding: '0.35rem 0.75rem', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer' }}>
                        ✓ Mark Applied
                      </button>
                    </div>
                  </div>
                  <div style={{ position: 'relative' }}>
                    <textarea readOnly value={item.cover_letter || ''}
                      style={{ width: '100%', minHeight: 120, maxHeight: 180, resize: 'vertical', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)', borderRadius: 6, padding: '0.6rem 0.75rem', color: 'var(--text2)', fontSize: '0.78rem', lineHeight: 1.5, boxSizing: 'border-box', fontFamily: 'inherit' }} />
                    <button onClick={() => _copyLetter(item.cover_letter, idx)}
                      style={{ position: 'absolute', top: '0.4rem', right: '0.5rem', background: copiedIdx === idx ? 'rgba(52,211,153,0.2)' : 'rgba(99,102,241,0.2)', color: copiedIdx === idx ? '#34d399' : '#818cf8', border: `1px solid ${copiedIdx === idx ? 'rgba(52,211,153,0.4)' : 'rgba(99,102,241,0.4)'}`, borderRadius: 5, padding: '0.2rem 0.55rem', fontSize: '0.72rem', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }}>
                      {copiedIdx === idx ? '✓ Copied!' : '📋 Copy'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ padding: '0.75rem 1.25rem', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--muted)', fontSize: '0.78rem' }}>{applyResults.length} remaining — mark each as applied after submitting</span>
              <button onClick={() => setApplyResults(null)} style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--muted)', borderRadius: 6, padding: '0.35rem 0.9rem', fontSize: '0.78rem', cursor: 'pointer' }}>Done</button>
            </div>
          </div>
        </div>
      )}

      {clModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}
          onClick={e => { if (e.target === e.currentTarget) setClModal(null); }}>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, width: '100%', maxWidth: 640, maxHeight: '88vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '0.85rem 0.75rem 0.85rem 1.5rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h3 style={{ fontSize: '1rem', marginBottom: '0.15rem' }}>Cover Letter</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clModal.job.title} — {clModal.job.company}</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexShrink: 0 }}>
                <button onClick={async () => {
                  setClModal(m => ({ ...m, loading: true, letter: '' }));
                  const res = await api.post(`/api/jobs/${clModal.job.id}/cover-letter`);
                  setClModal(m => m ? { ...m, letter: res.cover_letter || '', loading: false } : m);
                  setJobs(prev => prev.map(j => j.id === clModal.job.id ? { ...j, cover_letter: res.cover_letter } : j));
                }} disabled={clModal.loading} style={{ ...styles.btn, ...styles.btnSm, background: 'rgba(124,58,237,0.2)', color: '#c4b5fd', border: '1px solid rgba(124,58,237,0.4)', fontSize: '0.8rem' }}>
                  {clModal.loading ? '…' : '↺ Regenerate'}
                </button>
                <button onClick={() => setClModal(null)} title="Close"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, background: 'rgba(220,38,38,0.15)', border: '1px solid rgba(220,38,38,0.4)', borderRadius: 7, color: '#f87171', cursor: 'pointer', fontSize: '1.1rem', lineHeight: 1, flexShrink: 0, transition: 'background 0.15s' }}
                  onMouseEnter={e => e.currentTarget.style.background='rgba(220,38,38,0.4)'}
                  onMouseLeave={e => e.currentTarget.style.background='rgba(220,38,38,0.15)'}>×</button>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem 1.5rem' }}>
              {clModal.loading ? (
                <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--muted)' }}>
                  <p style={{ marginBottom: '0.5rem' }}>Generating personalised cover letter with AI...</p>
                  <p style={{ fontSize: '0.8rem' }}>Using your profile + job description</p>
                </div>
              ) : clModal.letter ? (
                <pre style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: '0.9rem', color: '#e2e8f0', fontFamily: 'inherit' }}>{clModal.letter}</pre>
              ) : (
                <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '2rem' }}>No cover letter yet — click Regenerate above.</p>
              )}
            </div>
            {!clModal.loading && clModal.letter && (
              <div style={{ padding: '0.75rem 1.5rem', borderTop: '1px solid var(--border)', display: 'flex', gap: '0.5rem' }}>
                <button onClick={() => copyCoverLetter(clModal.letter)} style={{ ...styles.btn, ...styles.btnPrimary, flex: 1 }}>📋 Copy to Clipboard</button>
                <button onClick={() => exportCoverLetterPdf(clModal.letter, clModal.job?.title, clModal.job?.company)}
                  style={{ ...styles.btn, ...styles.btnSecondary, flex: 1 }}>⬇ Download PDF</button>
              </div>
            )}
          </div>
        </div>
      )}

      {missingModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, width: '100%', maxWidth: 480, overflow: 'hidden' }}>
            <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border)', background: 'rgba(245,158,11,0.08)' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '0.25rem', color: 'var(--yellow2)' }}>⚠ Profile Incomplete</h3>
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>Please fill in the missing details so we can generate a personalised cover letter and auto-apply on your behalf.</p>
            </div>
            <div style={{ padding: '1.25rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '0.9rem', maxHeight: '55vh', overflowY: 'auto' }}>
              {missingModal.missing.map(f => (
                <div key={f.field}>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '0.3rem', fontWeight: 600 }}>{f.label} <span style={{ color: 'var(--red2)' }}>*</span></label>
                  <input
                    type={f.type || 'text'}
                    placeholder={f.label}
                    value={missingValues[f.field] || ''}
                    onChange={e => setMissingValues(v => ({ ...v, [f.field]: e.target.value }))}
                    style={{ ...styles.input, marginBottom: 0 }}
                  />
                  {f.field === 'skills_text' && <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.25rem' }}>Comma-separated, e.g. Java, Spring Boot, AWS</p>}
                </div>
              ))}
            </div>
            <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--border)', display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button onClick={() => { setMissingModal(null); setMissingValues({}); }} style={{ ...styles.btn, ...styles.btnSecondary }}>Cancel</button>
              <button
                disabled={missingModal.missing.some(f => !missingValues[f.field]?.trim())}
                onClick={submitMissingAndApply}
                style={{ ...styles.btn, background: 'linear-gradient(135deg,#059669,#2563eb)', color: '#fff', opacity: missingModal.missing.some(f => !missingValues[f.field]?.trim()) ? 0.45 : 1 }}>
                Save & Auto-Apply
              </button>
            </div>
          </div>
        </div>
      )}

      {niModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}
          onClick={e => { if (e.target === e.currentTarget) setNiModal(null); }}>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '1.75rem', width: '100%', maxWidth: 480, maxHeight: '85vh', overflowY: 'auto' }}>
            <h3 style={{ marginBottom: '0.25rem', fontSize: '1.1rem' }}>Not Interested</h3>
            <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>
              {niModal.title.substring(0, 50)} — {niModal.company}
            </p>

            <p style={{ fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Select a reason</p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {PREDEFINED_REASONS.map(reason => (
                <label key={reason} style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', cursor: 'pointer', padding: '0.5rem 0.75rem', borderRadius: 8, background: niReason === reason ? 'rgba(220,38,38,0.12)' : 'transparent', border: `1px solid ${niReason === reason ? 'rgba(220,38,38,0.4)' : 'transparent'}`, transition: 'all 0.15s' }}>
                  <input type="radio" name="ni_reason" value={reason} checked={niReason === reason} onChange={() => { setNiReason(reason); setNiOtherText(''); }}
                    style={{ accentColor: 'var(--red)', width: 15, height: 15, flexShrink: 0 }} />
                  <span style={{ fontSize: '0.9rem' }}>{reason}</span>
                </label>
              ))}

              {niSavedReasons.filter(r => !PREDEFINED_REASONS.includes(r)).map(reason => (
                <label key={reason} style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', cursor: 'pointer', padding: '0.5rem 0.75rem', borderRadius: 8, background: niReason === reason ? 'rgba(220,38,38,0.12)' : 'rgba(255,255,255,0.03)', border: `1px solid ${niReason === reason ? 'rgba(220,38,38,0.4)' : 'rgba(255,255,255,0.06)'}`, transition: 'all 0.15s' }}>
                  <input type="radio" name="ni_reason" value={reason} checked={niReason === reason} onChange={() => { setNiReason(reason); setNiOtherText(''); }}
                    style={{ accentColor: 'var(--red)', width: 15, height: 15, flexShrink: 0 }} />
                  <span style={{ fontSize: '0.9rem' }}>{reason}</span>
                  <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--muted)', background: 'var(--bg3)', padding: '0.1rem 0.4rem', borderRadius: 4 }}>saved</span>
                </label>
              ))}

              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.65rem', cursor: 'pointer', padding: '0.5rem 0.75rem', borderRadius: 8, background: niReason === '__other__' ? 'rgba(220,38,38,0.12)' : 'transparent', border: `1px solid ${niReason === '__other__' ? 'rgba(220,38,38,0.4)' : 'transparent'}`, transition: 'all 0.15s' }}>
                <input type="radio" name="ni_reason" value="__other__" checked={niReason === '__other__'} onChange={() => setNiReason('__other__')}
                  style={{ accentColor: 'var(--red)', width: 15, height: 15, flexShrink: 0, marginTop: 3 }} />
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: '0.9rem' }}>Other</span>
                  {niReason === '__other__' && (
                    <input
                      autoFocus
                      type="text"
                      placeholder="Describe your reason..."
                      value={niOtherText}
                      onChange={e => setNiOtherText(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter' && niOtherText.trim()) submitNotInterested(); }}
                      style={{ display: 'block', marginTop: '0.5rem', width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '0.4rem 0.65rem', color: 'var(--text)', fontSize: '0.88rem', outline: 'none' }}
                    />
                  )}
                </div>
              </label>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
              <button style={{ ...styles.btn, ...styles.btnSecondary }} onClick={() => setNiModal(null)}>Cancel</button>
              <button
                disabled={!niReason || (niReason === '__other__' && !niOtherText.trim()) || niSaving}
                onClick={submitNotInterested}
                style={{ ...styles.btn, background: '#dc2626', color: '#fff', opacity: (!niReason || (niReason === '__other__' && !niOtherText.trim())) ? 0.4 : 1, cursor: (!niReason || (niReason === '__other__' && !niOtherText.trim())) ? 'not-allowed' : 'pointer' }}>
                {niSaving ? 'Saving...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

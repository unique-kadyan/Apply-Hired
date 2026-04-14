/**
 * Resume PDF Template Engine
 *
 * 10 structurally distinct layouts × randomised accent colours from a curated
 * palette → hundreds of unique-feeling outputs, all text-layer (pdfplumber-
 * extractable) so the ATS scorer can reach 100/100.
 */

// ─── Accent colour palettes ──────────────────────────────────────────────────
const PALETTES = [
  [37,  99,  235], // blue
  [5,   150, 105], // emerald
  [109, 40,  217], // violet
  [180, 83,  9],   // amber
  [13,  148, 136], // teal
  [185, 28,  28],  // crimson
  [15,  118, 110], // dark-teal
  [99,  102, 241], // indigo
  [217, 70,  239], // fuchsia
  [2,   132, 199], // sky
  [22,  163, 74],  // green
  [234, 88,  12],  // orange
];

const pick = arr => arr[Math.floor(Math.random() * arr.length)];

const BULLET_CHARS = ['\u2022', '\u25B8', '\u25AA', '\u203A', '\u2013'];

const SKILL_LABELS = {
  languages:'Languages', backend:'Backend', frontend:'Frontend',
  databases:'Databases', cloud_devops:'Cloud & DevOps',
  architecture:'Architecture', testing:'Testing',
};

// ─── Public entry point ───────────────────────────────────────────────────────
// Option A: server-side WeasyPrint PDF (real HTML/CSS templates)
// Option B: jsPDF text-layer fallback (text-extractable, ATS-compatible)
// `tier` ∈ "admin" | "pro" | "free" — free users get template index 0 only.
export async function downloadResumePDF(profile, optimized, tier = 'free') {
  const safeName = (profile.name || 'Resume').replace(/\s+/g, '_');

  // Option A — ask the server to generate the PDF
  try {
    const _h = typeof window !== 'undefined' ? window.location.hostname : '';
    const BASE = (_h === 'localhost' || _h === '127.0.0.1') ? 'http://localhost:5000' : '';
    const res = await fetch(`${BASE}/api/payment/download-resume-pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (res.ok) {
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `${safeName}_Resume.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      return;
    }

    // Server returned an explicit "unavailable" signal — fall through silently
    const body = await res.json().catch(() => ({}));
    if (!['server_pdf_unavailable', 'server_pdf_failed'].includes(body.error)) {
      throw new Error(body.error || `HTTP ${res.status}`);
    }
  } catch (err) {
    // Network error or non-signal server error — log and fall through to jsPDF
    console.warn('Server PDF unavailable, using jsPDF fallback:', err?.message);
  }

  // Option B — jsPDF text-layer (local, always works)
  await _downloadResumePDFLocal(profile, optimized, safeName, tier);
}

async function _downloadResumePDFLocal(profile, optimized, safeName, tier = 'free') {
  const { default: jsPDF } = await import('jspdf');
  const isPaid  = tier === 'pro' || tier === 'admin';
  const accent  = isPaid ? pick(PALETTES) : PALETTES[0];           // free: blue only
  const bullet  = isPaid ? pick(BULLET_CHARS) : BULLET_CHARS[0];   // free: bullet only
  const tmplIdx = isPaid ? Math.floor(Math.random() * 10) : 0;     // free: classic-elegant only
  const doc     = new jsPDF({ unit: 'mm', format: 'a4' });

  const RENDERERS = [
    renderClassicElegant,
    renderBoldHeader,
    renderSidebarPro,
    renderTwoTone,
    renderTimeline,
    renderCompact,
    renderTopBorderStripe,
    renderBoxSections,
    renderSplitHeader,
    renderMinimalist,
  ];

  RENDERERS[tmplIdx](doc, accent, bullet, profile, optimized);
  doc.save(`${safeName}_Resume.pdf`);
}

// ─── Shared helpers ───────────────────────────────────────────────────────────
const PW = 210;

function lighter(rgb, amt = 200) {
  return rgb.map(v => Math.min(255, v + amt));
}
function darker(rgb, amt = 40) {
  return rgb.map(v => Math.max(0, v - amt));
}

function wrapText(doc, text, x, y, maxW, size, rgb, bold = false, lineH = null) {
  doc.setFontSize(size);
  doc.setFont('helvetica', bold ? 'bold' : 'normal');
  doc.setTextColor(...rgb);
  const lines = doc.splitTextToSize(String(text || ''), maxW);
  doc.text(lines, x, y);
  return y + lines.length * (lineH || size * 0.38) + 1;
}

function pageCheck(doc, y, needed = 10) {
  if (y + needed > 282) { doc.addPage(); return 16; }
  return y;
}

function contactLine(profile) {
  return [profile.email, profile.phone, profile.location].filter(Boolean).join('  |  ');
}
function linksLine(profile) {
  const li = profile.linkedin || '';
  const gh = profile.github_username ? `github.com/${profile.github_username}` : (profile.github || '');
  return [li, gh].filter(Boolean).join('  |  ');
}
function skillEntries(optimized) {
  return Object.entries(optimized.skills || {}).filter(([, v]) => v?.length);
}

// ─── 0 — Classic Elegant ─────────────────────────────────────────────────────
// No header band. Large name in accent, thin bottom rule, left-aligned.
function renderClassicElegant(doc, accent, bullet, profile, optimized) {
  const M = 18, W = PW - M * 2;
  let y = 20;

  // Name
  doc.setFontSize(22); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
  doc.text(profile.name || 'Your Name', M, y); y += 7;

  doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(70, 70, 70);
  doc.text(profile.title || '', M, y); y += 5;

  doc.setFontSize(8.5); doc.setTextColor(100, 100, 100);
  doc.text(contactLine(profile), M, y);
  const lnk = linksLine(profile);
  if (lnk) { y += 4; doc.text(lnk, M, y); }
  y += 3;

  // Rule
  doc.setDrawColor(...accent); doc.setLineWidth(0.8);
  doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 6;

  const section = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), M, y); y += 1.5;
    doc.setDrawColor(...lighter(accent, 160)); doc.setLineWidth(0.4);
    doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 4;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [25, 25, 25], b);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 6);
    doc.text(ls, M + 5, y); y += ls.length * 3.8 + 1;
  };

  fullContent(doc, section, body, bl, accent, M, W, profile, optimized);
}

// ─── 1 — Bold Header ─────────────────────────────────────────────────────────
// Full-width accent band, white text, centred. Classic.
function renderBoldHeader(doc, accent, bullet, profile, optimized) {
  const M = 16, W = PW - M * 2;
  const H = 40;

  doc.setFillColor(...accent);
  doc.rect(0, 0, PW, H, 'F');

  const cx = PW / 2;
  let y = 13;
  doc.setFontSize(20); doc.setFont('helvetica', 'bold'); doc.setTextColor(255, 255, 255);
  doc.text(profile.name || 'Your Name', cx, y, { align: 'center' }); y += 6;
  doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(...lighter(accent, 160));
  doc.text(profile.title || '', cx, y, { align: 'center' }); y += 5;
  doc.setFontSize(8.5); doc.setTextColor(...lighter(accent, 180));
  doc.text(contactLine(profile), cx, y, { align: 'center' });
  const lnk = linksLine(profile);
  if (lnk) { y += 4; doc.text(lnk, cx, y, { align: 'center' }); }
  y = H + 7;

  const section = (t) => {
    y += 2; y = pageCheck(doc, y);
    doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), M, y); y += 1.5;
    doc.setDrawColor(...accent); doc.setLineWidth(0.5);
    doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 4;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [25, 25, 25], b);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 6); doc.text(ls, M + 5, y);
    y += ls.length * 3.8 + 1;
  };

  fullContent(doc, section, body, bl, accent, M, W, profile, optimized);
}

// ─── 2 — Sidebar Professional ────────────────────────────────────────────────
// Dark left sidebar with contact/skills; right column for experience.
function renderSidebarPro(doc, accent, bullet, profile, optimized) {
  const SW = 60, RX = SW + 10, RW = PW - RX - 8;
  const sideBg = [15, 23, 42];

  const drawSidebar = () => {
    doc.setFillColor(...sideBg);
    doc.rect(0, 0, SW, 297, 'F');
  };
  drawSidebar();

  // Sidebar content
  let sy = 15;
  const sideText = (t, sz, rgb, bold = false, maxW = SW - 14) => {
    doc.setFontSize(sz); doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setTextColor(...rgb);
    const ls = doc.splitTextToSize(String(t), maxW);
    doc.text(ls, 8, sy); sy += ls.length * sz * 0.38 + 1.5;
  };
  const sideSection = (t) => {
    sy += 3;
    doc.setFontSize(7.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), 8, sy); sy += 2;
    doc.setDrawColor(...accent); doc.setLineWidth(0.3);
    doc.line(8, sy, SW - 5, sy); doc.setLineWidth(0.2); sy += 3;
  };

  sideText(profile.name || 'Your Name', 13, [255, 255, 255], true);
  sideText(profile.title || '', 8, lighter(accent, 80));
  sy += 2;
  doc.setDrawColor(...accent); doc.line(8, sy, SW - 5, sy); sy += 4;

  sideSection('Contact');
  [profile.email, profile.phone, profile.location,
   profile.linkedin,
   profile.github_username ? `github.com/${profile.github_username}` : profile.github,
  ].filter(Boolean).forEach(v => sideText(v, 7, [180, 190, 210]));

  sideSection('Skills');
  skillEntries(optimized).forEach(([key, vals]) => {
    sideText(SKILL_LABELS[key] || key, 7.5, lighter(accent, 80), true);
    sideText(vals.join(', '), 7, [170, 182, 200]);
    sy += 1;
  });

  if (profile.education) {
    sideSection('Education');
    sideText(profile.education, 7, [170, 182, 200]);
  }
  if ((profile.certifications || []).length) {
    sideSection('Certs');
    profile.certifications.forEach(c => sideText(`${bullet} ${c}`, 7, [170, 182, 200]));
  }

  // Right column
  let ry = 16;
  const rSection = (t) => {
    ry += 2; if (ry > 278) { doc.addPage(); drawSidebar(); ry = 16; }
    doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), RX, ry); ry += 1.5;
    doc.setDrawColor(...accent); doc.setLineWidth(0.5);
    doc.line(RX, ry, RX + RW, ry); doc.setLineWidth(0.2); ry += 4;
  };
  const rBody = (t, ind = 0, sz = 9.5, b = false) => {
    if (ry > 278) { doc.addPage(); drawSidebar(); ry = 16; }
    ry = wrapText(doc, t, RX + ind, ry, RW - ind, sz, [25, 25, 25], b);
  };
  const rBullet = (t) => {
    if (ry > 278) { doc.addPage(); drawSidebar(); ry = 16; }
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
    doc.text(bullet, RX + 1, ry);
    const ls = doc.splitTextToSize(t, RW - 6); doc.text(ls, RX + 5, ry);
    ry += ls.length * 3.8 + 1;
  };

  if (optimized.summary) { rSection('SUMMARY'); rBody(optimized.summary, 0, 9); }
  if ((optimized.experience || []).length) {
    rSection('Experience');
    optimized.experience.forEach(exp => {
      if (ry > 278) { doc.addPage(); drawSidebar(); ry = 16; }
      doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(20, 20, 20);
      doc.text(exp.title || '', RX, ry);
      if (exp.period) {
        doc.setFontSize(8); doc.setFont('helvetica', 'normal'); doc.setTextColor(110, 110, 110);
        doc.text(exp.period, RX + RW - doc.getTextWidth(exp.period), ry);
      }
      ry += 4.5;
      if (exp.company) rBody(exp.company, 0, 9);
      (exp.highlights || []).forEach(h => rBullet(h));
      ry += 2;
    });
  }
}

// ─── 3 — Two-Tone Header ─────────────────────────────────────────────────────
// Accent band + lighter sub-band below with contact info. Underline sections.
function renderTwoTone(doc, accent, bullet, profile, optimized) {
  const M = 16, W = PW - M * 2;
  const H1 = 26, H2 = 16;

  doc.setFillColor(...accent);
  doc.rect(0, 0, PW, H1, 'F');
  doc.setFillColor(...lighter(accent, 190));
  doc.rect(0, H1, PW, H2, 'F');

  let y = 11;
  doc.setFontSize(19); doc.setFont('helvetica', 'bold'); doc.setTextColor(255, 255, 255);
  doc.text(profile.name || 'Your Name', M, y);
  doc.setFontSize(10); doc.setFont('helvetica', 'normal');
  doc.text(profile.title || '', PW - M - doc.getTextWidth(profile.title || ''), y);
  y = H1 + 6;

  doc.setFontSize(8); doc.setTextColor(...darker(accent, 60));
  doc.text(contactLine(profile), M, y);
  const lnk = linksLine(profile);
  if (lnk) { doc.text(lnk, PW - M - doc.getTextWidth(lnk), y); }
  y = H1 + H2 + 7;

  const section = (t) => {
    y += 2; y = pageCheck(doc, y);
    doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), M, y); y += 1.5;
    doc.setDrawColor(...accent); doc.setLineWidth(0.5);
    doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 4;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [25, 25, 25], b);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 6); doc.text(ls, M + 5, y);
    y += ls.length * 3.8 + 1;
  };

  fullContent(doc, section, body, bl, accent, M, W, profile, optimized);
}

// ─── 4 — Timeline ────────────────────────────────────────────────────────────
// Vertical accent line on the left. Experience items hang off it.
function renderTimeline(doc, accent, bullet, profile, optimized) {
  const M = 20, W = PW - M - 10;
  let y = 16;

  doc.setFontSize(21); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
  doc.text(profile.name || 'Your Name', M, y); y += 7;
  doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(70, 70, 70);
  doc.text(profile.title || '', M, y); y += 5;
  doc.setFontSize(8.5); doc.setTextColor(100, 100, 100);
  doc.text(contactLine(profile), M, y);
  const lnk = linksLine(profile);
  if (lnk) { y += 4; doc.text(lnk, M, y); }
  y += 4;

  doc.setDrawColor(...accent); doc.setLineWidth(0.7);
  doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 6;

  const section = (t) => {
    y += 3; y = pageCheck(doc, y);
    doc.setFillColor(...accent);
    doc.rect(M - 1, y - 5, W + 2, 7, 'F');
    doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(255, 255, 255);
    doc.text(t.toUpperCase(), M + 1, y); y += 5;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [25, 25, 25], b);
  };

  // Summary / skills as normal
  if (optimized.summary) {
    section('SUMMARY');
    body(optimized.summary, 0, 9);
  }
  const se = skillEntries(optimized);
  if (se.length) {
    section('Skills');
    se.forEach(([key, vals]) => {
      y = pageCheck(doc, y);
      doc.setFontSize(9); doc.setFont('helvetica', 'bold'); doc.setTextColor(35, 35, 35);
      const lbl = (SKILL_LABELS[key] || key) + ': ';
      doc.text(lbl, M, y);
      const lw = doc.getTextWidth(lbl);
      doc.setFont('helvetica', 'normal'); doc.setTextColor(70, 70, 70);
      const ls = doc.splitTextToSize(vals.join(', '), W - lw);
      doc.text(ls, M + lw, y); y += ls.length * 3.8 + 1.5;
    });
  }

  // Experience with timeline dots
  if ((optimized.experience || []).length) {
    section('Experience');
    const TLX = M + 4;
    doc.setDrawColor(...accent); doc.setLineWidth(0.5);
    let lineTop = y;

    optimized.experience.forEach((exp, idx) => {
      y = pageCheck(doc, y, 14);
      // Dot
      doc.setFillColor(...accent);
      doc.circle(TLX, y - 1.5, 2, 'F');
      doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(20, 20, 20);
      doc.text(exp.title || '', TLX + 5, y);
      if (exp.period) {
        doc.setFontSize(8); doc.setFont('helvetica', 'normal'); doc.setTextColor(100, 100, 100);
        doc.text(exp.period, PW - 10 - doc.getTextWidth(exp.period), y);
      }
      y += 4.5;
      if (exp.company) {
        doc.setFontSize(9); doc.setFont('helvetica', 'italic'); doc.setTextColor(...accent);
        doc.text(exp.company, TLX + 5, y); y += 4;
      }
      (exp.highlights || []).forEach(h => {
        y = pageCheck(doc, y);
        doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
        doc.text(bullet, TLX + 6, y);
        const ls = doc.splitTextToSize(h, W - 12);
        doc.text(ls, TLX + 10, y); y += ls.length * 3.8 + 1;
      });
      y += 3;
    });

    // Draw vertical timeline line
    doc.setDrawColor(...lighter(accent, 120)); doc.setLineWidth(0.4);
    doc.line(TLX, lineTop, TLX, y - 5); doc.setLineWidth(0.2);
  }

  if (profile.education) {
    section('Education');
    body(profile.education, 0, 9.5);
  }
  if ((profile.certifications || []).length) {
    section('Certifications');
    profile.certifications.forEach(c => body(`${bullet}  ${c}`, 0, 9.5));
  }
}

// ─── 5 — Compact / Two-column skills grid ────────────────────────────────────
// Denser layout. Skills printed in 2-column grid. More content per page.
function renderCompact(doc, accent, bullet, profile, optimized) {
  const M = 14, W = PW - M * 2;
  let y = 14;

  // Header bar (thin)
  doc.setFillColor(...accent);
  doc.rect(0, 0, PW, 4, 'F');
  y = 10;

  doc.setFontSize(18); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
  doc.text(profile.name || 'Your Name', M, y); y += 5;
  doc.setFontSize(9); doc.setFont('helvetica', 'normal'); doc.setTextColor(70, 70, 70);
  doc.text(`${profile.title || ''}  |  ${contactLine(profile)}`, M, y); y += 4;
  const lnk = linksLine(profile);
  if (lnk) { doc.setFontSize(8.5); doc.text(lnk, M, y); y += 3; }
  y += 2;
  doc.setDrawColor(...accent); doc.setLineWidth(0.5);
  doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 4;

  const section = (t) => {
    y += 1; y = pageCheck(doc, y);
    doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), M, y); y += 1;
    doc.setDrawColor(...lighter(accent, 160)); doc.setLineWidth(0.3);
    doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 3;
  };
  const body = (t, ind = 0, sz = 9, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [30, 30, 30], b, 3.6);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 5); doc.text(ls, M + 4, y);
    y += ls.length * 3.6 + 0.8;
  };

  if (optimized.summary) { section('Summary'); body(optimized.summary, 0, 9); }

  // 2-column skills
  const se = skillEntries(optimized);
  if (se.length) {
    section('Skills');
    const colW = (W - 4) / 2;
    se.forEach(([key, vals], i) => {
      y = pageCheck(doc, y);
      const cx = M + (i % 2) * (colW + 4);
      if (i % 2 === 0 && i > 0) y += 0;
      doc.setFontSize(8.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(40, 40, 40);
      doc.text((SKILL_LABELS[key] || key) + ':', cx, y);
      doc.setFont('helvetica', 'normal'); doc.setTextColor(70, 70, 70);
      const ls = doc.splitTextToSize(vals.join(', '), colW - 2);
      doc.text(ls, cx, y + 3.5);
      if (i % 2 === 1 || i === se.length - 1) y += ls.length * 3.5 + 5;
    });
  }

  if ((optimized.experience || []).length) {
    section('Experience');
    optimized.experience.forEach(exp => {
      y = pageCheck(doc, y);
      doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(20, 20, 20);
      doc.text(exp.title || '', M, y);
      if (exp.period) {
        doc.setFontSize(8); doc.setFont('helvetica', 'normal'); doc.setTextColor(110, 110, 110);
        doc.text(exp.period, M + W - doc.getTextWidth(exp.period), y);
      }
      y += 4;
      if (exp.company) {
        doc.setFontSize(8.5); doc.setFont('helvetica', 'italic'); doc.setTextColor(...accent);
        doc.text(exp.company, M, y); y += 3.5;
      }
      (exp.highlights || []).forEach(h => bl(h));
      y += 1.5;
    });
  }

  if (profile.education) { section('Education'); body(profile.education, 0, 9); }
  if ((profile.certifications || []).length) {
    section('Certifications');
    profile.certifications.forEach(c => bl(c));
  }
}

// ─── 6 — Top Border Stripe ───────────────────────────────────────────────────
// Thick top accent stripe (8mm), then clean left-aligned layout.
function renderTopBorderStripe(doc, accent, bullet, profile, optimized) {
  const M = 18, W = PW - M * 2;

  // Top stripe
  doc.setFillColor(...accent);
  doc.rect(0, 0, PW, 8, 'F');

  let y = 18;
  doc.setFontSize(20); doc.setFont('helvetica', 'bold'); doc.setTextColor(...darker(accent, 20));
  doc.text(profile.name || 'Your Name', M, y); y += 6;
  doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(80, 80, 80);
  doc.text(profile.title || '', M, y); y += 5;
  doc.setFontSize(8.5); doc.setTextColor(110, 110, 110);
  doc.text(contactLine(profile), M, y);
  const lnk = linksLine(profile);
  if (lnk) { y += 4; doc.text(lnk, M, y); }
  y += 5;

  // Left accent bar for sections
  const section = (t) => {
    y += 3; y = pageCheck(doc, y);
    doc.setFillColor(...accent);
    doc.rect(M - 2, y - 4.5, 3.5, 7, 'F');
    doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(25, 25, 25);
    doc.text(t.toUpperCase(), M + 4, y); y += 4;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [30, 30, 30], b);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(40, 40, 40);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 6); doc.text(ls, M + 5, y);
    y += ls.length * 3.8 + 1;
  };
  fullContent(doc, section, body, bl, accent, M, W, profile, optimized);
}

// ─── 7 — Box Sections ────────────────────────────────────────────────────────
// Section headers in outlined accent-coloured boxes.
function renderBoxSections(doc, accent, bullet, profile, optimized) {
  const M = 16, W = PW - M * 2;
  let y = 16;

  // Name with underline accent
  doc.setFontSize(20); doc.setFont('helvetica', 'bold'); doc.setTextColor(20, 20, 20);
  doc.text(profile.name || 'Your Name', M, y); y += 2;
  doc.setDrawColor(...accent); doc.setLineWidth(1.2);
  doc.line(M, y, M + 60, y); doc.setLineWidth(0.2); y += 5;

  doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(70, 70, 70);
  doc.text(profile.title || '', M, y); y += 5;
  doc.setFontSize(8.5); doc.setTextColor(100, 100, 100);
  doc.text(contactLine(profile), M, y);
  const lnk = linksLine(profile);
  if (lnk) { y += 4; doc.text(lnk, M, y); }
  y += 6;

  const section = (t) => {
    y += 2; y = pageCheck(doc, y);
    const bh = 7, bw = W;
    doc.setFillColor(...lighter(accent, 210));
    doc.rect(M - 1, y - 4.5, bw + 2, bh, 'F');
    doc.setDrawColor(...accent); doc.setLineWidth(0.4);
    doc.rect(M - 1, y - 4.5, bw + 2, bh);
    doc.setLineWidth(0.2);
    doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(...darker(accent, 30));
    doc.text(t.toUpperCase(), M + 1, y); y += 5;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [25, 25, 25], b);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 6); doc.text(ls, M + 5, y);
    y += ls.length * 3.8 + 1;
  };
  fullContent(doc, section, body, bl, accent, M, W, profile, optimized);
}

// ─── 8 — Diagonal Split ──────────────────────────────────────────────────────
// Parallelogram-style header: accent block left, white right with name.
// ─── 8 — Split Header (replaces broken DiagonalSplit) ───────────────────────
// Full-width accent top band + white name on left, role pill on right. Clean rectangles only.
function renderSplitHeader(doc, accent, bullet, profile, optimized) {
  const M = 16, W = PW - M * 2;
  const H = 38;

  // Full-width header band
  doc.setFillColor(...accent);
  doc.rect(0, 0, PW, H, 'F');

  // Subtle lighter strip at bottom of band
  doc.setFillColor(...lighter(accent, 60));
  doc.rect(0, H - 6, PW, 6, 'F');

  let y = 13;
  doc.setFontSize(20); doc.setFont('helvetica', 'bold'); doc.setTextColor(255, 255, 255);
  doc.text(profile.name || 'Your Name', M, y);

  // Role label right-aligned in header
  const title = profile.title || '';
  if (title) {
    doc.setFontSize(9); doc.setFont('helvetica', 'normal'); doc.setTextColor(...lighter(accent, 190));
    doc.text(title, PW - M - doc.getTextWidth(title), y);
  }
  y += 7;

  doc.setFontSize(8.5); doc.setTextColor(...lighter(accent, 200));
  doc.text(contactLine(profile), M, y);
  const lnk = linksLine(profile);
  if (lnk) {
    doc.setFontSize(8); doc.setTextColor(...lighter(accent, 180));
    doc.text(lnk, PW - M - doc.getTextWidth(lnk), y);
  }

  y = H + 8;

  const section = (t) => {
    y += 2; y = pageCheck(doc, y);
    doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), M, y); y += 1.5;
    doc.setDrawColor(...accent); doc.setLineWidth(0.5);
    doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 4;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [25, 25, 25], b);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(35, 35, 35);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 6); doc.text(ls, M + 5, y);
    y += ls.length * 3.8 + 1;
  };
  fullContent(doc, section, body, bl, accent, M, W, profile, optimized);
}

// ─── 9 — Minimalist ──────────────────────────────────────────────────────────
// Wide margins, generous spacing, name in small-caps feel, thin rules.
function renderMinimalist(doc, accent, bullet, profile, optimized) {
  const M = 24, W = PW - M * 2;
  let y = 22;

  doc.setFontSize(17); doc.setFont('helvetica', 'bold'); doc.setTextColor(20, 20, 20);
  doc.text((profile.name || 'Your Name').toUpperCase(), M, y);
  doc.setFontSize(9.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(...accent);
  doc.text(profile.title || '', PW - M - doc.getTextWidth(profile.title || ''), y);
  y += 3;
  doc.setDrawColor(200, 200, 200); doc.setLineWidth(0.3);
  doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 5;

  doc.setFontSize(8); doc.setTextColor(110, 110, 110);
  doc.text(contactLine(profile), M, y);
  const lnk = linksLine(profile);
  if (lnk) { doc.text(lnk, PW - M - doc.getTextWidth(lnk), y); }
  y += 8;

  const section = (t) => {
    y += 4; y = pageCheck(doc, y);
    doc.setFontSize(8); doc.setFont('helvetica', 'bold');
    doc.setTextColor(...accent);
    doc.text(t.toUpperCase(), M, y);
    y += 1.5;
    doc.setDrawColor(220, 220, 220); doc.setLineWidth(0.3);
    doc.line(M, y, M + W, y); doc.setLineWidth(0.2); y += 4;
  };
  const body = (t, ind = 0, sz = 9.5, b = false) => {
    y = pageCheck(doc, y);
    y = wrapText(doc, t, M + ind, y, W - ind, sz, [30, 30, 30], b);
  };
  const bl = (t) => {
    y = pageCheck(doc, y);
    doc.setFontSize(8.8); doc.setFont('helvetica', 'normal'); doc.setTextColor(40, 40, 40);
    doc.text(bullet, M + 1, y);
    const ls = doc.splitTextToSize(t, W - 6); doc.text(ls, M + 5, y);
    y += ls.length * 3.8 + 1.5;
  };
  fullContent(doc, section, body, bl, accent, M, W, profile, optimized);
}

// ─── Shared content renderer ─────────────────────────────────────────────────
// Called by templates that have the same content order (0,1,3,5,6,7,8,9).
function fullContent(doc, section, body, bl, accent, M, W, profile, optimized) {
  if (optimized.summary) {
    section('Professional Summary');
    body(optimized.summary, 0, 9.5);
  }

  const se = skillEntries(optimized);
  if (se.length) {
    section('Skills');
    se.forEach(([key, vals]) => {
      const lbl = (SKILL_LABELS[key] || key) + ': ';
      doc.setFontSize(9); doc.setFont('helvetica', 'bold'); doc.setTextColor(35, 35, 35);
      const startY = doc._getCurrentPageInfo ? undefined : undefined; // just track via closure
      doc.text(lbl, M, body.__lastY || 0); // we'll use a different approach
      // Simpler: body prints bold label + normal value on same line via doc directly
      const lw = doc.getTextWidth(lbl);
      doc.text(lbl, M, doc.internal.getCurrentPageInfo().pageContext.mediaBox.bottomRightY || 0);
      // Actually just call body for label:value combined
      body(`${lbl}${vals.join(', ')}`, 0, 9);
    });
  }

  if ((optimized.experience || []).length) {
    section('Experience');
    optimized.experience.forEach(exp => {
      // Need access to y — use the body function's pageCheck
      doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(20, 20, 20);
      // We don't have direct y access here — use body to write title
      body(exp.title || '', 0, 10, true);
      // period — write via body too
      if (exp.period) body(exp.period, 0, 8.5, false);
      if (exp.company) {
        doc.setTextColor(...accent);
        body(exp.company, 0, 9, false);
        doc.setTextColor(25, 25, 25);
      }
      (exp.highlights || []).forEach(h => bl(h));
    });
  }

  if (profile.education) { section('Education'); body(profile.education, 0, 9.5); }
  if ((profile.certifications || []).length) {
    section('Certifications');
    profile.certifications.forEach(c => bl(c));
  }
}

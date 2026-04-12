'use client';
import { useEffect, useRef } from 'react';

function useChart(ref, config, deps) {
  useEffect(() => {
    if (!ref.current) return;
    let chart;
    let cancelled = false;
    import('chart.js/auto').then(({ default: Chart }) => {
      if (cancelled || !ref.current) return;
      // Destroy any pre-existing chart on this canvas (navigation back causes reuse)
      const existing = Chart.getChart(ref.current);
      if (existing) existing.destroy();
      chart = new Chart(ref.current.getContext('2d'), config);
    });
    return () => {
      cancelled = true;
      if (chart) chart.destroy();
    };
  }, deps);
}

export function DonutChart({ data, labels, colors, title }) {
  const ref = useRef();
  useChart(ref, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 2, borderColor: '#1e293b', hoverOffset: 6 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '68%',
      plugins: {
        legend: { position: 'right', labels: { color: '#94a3b8', font: { size: 11 }, padding: 10, boxWidth: 12 } },
        title: { display: !!title, text: title, color: '#e2e8f0', font: { size: 13, weight: '600' }, padding: { bottom: 10 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw}` } },
      },
    },
  }, [JSON.stringify(data)]);
  return <canvas ref={ref} style={{ maxHeight: 200 }} />;
}

export function BarChart({ labels, values, color, title, horizontal }) {
  const ref = useRef();
  useChart(ref, {
    type: 'bar',
    data: { labels, datasets: [{ data: values, backgroundColor: color || '#2563eb', borderRadius: 5, borderSkipped: false }] },
    options: {
      indexAxis: horizontal ? 'y' : 'x',
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title: { display: !!title, text: title, color: '#e2e8f0', font: { size: 13, weight: '600' }, padding: { bottom: 10 } },
      },
      scales: {
        x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(51,65,85,0.5)' } },
        y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(51,65,85,0.5)' } },
      },
    },
  }, [JSON.stringify(values)]);
  return <canvas ref={ref} style={{ maxHeight: horizontal ? Math.max(160, labels.length * 28) : 180 }} />;
}

export function LineChart({ labels, values, title }) {
  const ref = useRef();
  useChart(ref, {
    type: 'line',
    data: { labels, datasets: [{
      data: values, borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,0.12)',
      fill: true, tension: 0.4, pointRadius: 3, pointBackgroundColor: '#2563eb',
    }]},
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, title: { display: !!title, text: title, color: '#e2e8f0', font: { size: 13, weight: '600' }, padding: { bottom: 10 } } },
      scales: {
        x: { ticks: { color: '#64748b', font: { size: 9 }, maxRotation: 45 }, grid: { color: 'rgba(51,65,85,0.4)' } },
        y: { ticks: { color: '#64748b', font: { size: 10 }, stepSize: 1 }, grid: { color: 'rgba(51,65,85,0.4)' }, beginAtZero: true },
      },
    },
  }, [JSON.stringify(values)]);
  return <canvas ref={ref} style={{ maxHeight: 160 }} />;
}

export function FunnelChart({ stages }) {
  if (!stages || !stages.length) return null;
  const max = stages[0].count || 1;
  const GAP = 6;
  const COLORS = ['#2563eb','#0891b2','#059669','#d97706','#7c3aed'];
  return (
    <div style={{ width: '100%' }}>
      {stages.map((s, i) => {
        const pct = max > 0 ? (s.count / max) * 100 : 0;
        return (
          <div key={s.stage} style={{ marginBottom: GAP }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
              <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>{s.stage}</span>
              <span style={{ fontSize: '0.78rem', fontWeight: 700, color: COLORS[i] }}>{s.count}</span>
            </div>
            <div style={{ background: 'rgba(51,65,85,0.4)', borderRadius: 4, height: 10, width: '100%' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: COLORS[i], borderRadius: 4, transition: 'width 0.6s ease', minWidth: s.count > 0 ? 4 : 0 }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

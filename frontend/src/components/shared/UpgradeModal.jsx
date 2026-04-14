// Pro upgrade modal — three display modes:
//   mode="default"   manual open via the Upgrade button (just pricing)
//   mode="welcome"   shown once on login for free users; offers "Continue with Free"
//   mode="exhausted" triggered when a 402 quota response fires; no "continue free" — only upgrade
//
// `quotaInfo` (exhausted mode): { feature, used, limit, message } — describes which quota tripped.
import { useEffect, useState } from 'react';
import api from '@/lib/api';
import { refreshTier } from '@/lib/tier';

const FEATURES = [
  ['Job views per month', '5', 'Unlimited'],
  ['Applications per month', '5', 'Unlimited'],
  ['Cover letter generation', '1/month', 'Unlimited'],
  ['Resume optimizer', '₹50 per use', 'Unlimited'],
  ['Resume PDF templates', '1 basic', 'All 12 designs'],
  ['Auto-search scheduler', '—', '✅ Every hour'],
  ['Chrome extension auto-fill', '—', '✅'],
  ['Full AI score breakdown', '—', '✅'],
];

export default function UpgradeModal({
  open,
  onClose,
  showToast,
  mode = 'default',
  quotaInfo = null,
}) {
  const [plans, setPlans] = useState({});
  const [selected, setSelected] = useState('monthly');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get('/api/payment/tier/status').then((r) => {
      if (r?.pro_plans) setPlans(r.pro_plans);
    }).catch(() => {});
  }, [open]);

  if (!open) return null;

  const startCheckout = async () => {
    setBusy(true);
    try {
      const order = await api.post('/api/payment/subscribe/create-order', { plan: selected });
      if (!order || order.error) {
        showToast?.(order?.error || 'Failed to start checkout', 'error');
        setBusy(false);
        return;
      }
      const rzp = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: 'Kalibr',
        description: order.label || 'Pro subscription',
        order_id: order.order_id,
        theme: { color: '#7c3aed' },
        handler: async (resp) => {
          const verify = await api.post('/api/payment/subscribe/verify', {
            order_id: resp.razorpay_order_id,
            payment_id: resp.razorpay_payment_id,
            signature: resp.razorpay_signature,
          });
          setBusy(false);
          if (verify?.upgraded) {
            await refreshTier();
            showToast?.('Welcome to Pro! All features unlocked.', 'success');
            onClose?.();
          } else {
            showToast?.(verify?.error || 'Payment verification failed', 'error');
          }
        },
        modal: { ondismiss: () => setBusy(false) },
      });
      rzp.open();
    } catch (e) {
      setBusy(false);
      showToast?.('Checkout failed. Please try again.', 'error');
    }
  };

  const monthly = plans.monthly;
  const yearly = plans.yearly;

  const headerText = {
    welcome: { title: 'Welcome back! Choose your plan', sub: 'You can stick with Free or unlock everything with Pro.' },
    exhausted: { title: 'Monthly quota exhausted', sub: quotaInfo?.message || 'You\'ve hit your free-plan limit for this month. Upgrade to continue.' },
    default: { title: 'Upgrade to Pro', sub: 'Unlimited everything. Cancel anytime.' },
  }[mode] || { title: 'Upgrade to Pro', sub: 'Unlimited everything. Cancel anytime.' };

  const showContinueFree = mode === 'welcome';
  const allowDismiss = mode !== 'exhausted'; // exhausted modal still dismissable but no soft-out

  return (
    <div onClick={allowDismiss ? onClose : undefined} style={{
      position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.78)',
      backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center',
      justifyContent: 'center', zIndex: 1000, padding: '1rem',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: '#0f172a', border: '1px solid #334155', borderRadius: 14,
        padding: '1.75rem', maxWidth: 560, width: '100%',
        boxShadow: '0 25px 60px rgba(0,0,0,0.5)', maxHeight: '92vh', overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
          <div style={{ flex: 1 }}>
            {mode === 'exhausted' && (
              <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🚫</div>
            )}
            <h2 style={{ margin: 0, fontSize: '1.3rem', background: 'linear-gradient(135deg,#7c3aed,#2563eb)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', fontWeight: 800 }}>
              {headerText.title}
            </h2>
            <p style={{ margin: '0.3rem 0 0', color: '#94a3b8', fontSize: '0.85rem', lineHeight: 1.5 }}>
              {headerText.sub}
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '1.4rem', padding: 0, marginLeft: '0.5rem' }}>×</button>
        </div>

        {mode === 'exhausted' && quotaInfo && (
          <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 10, padding: '0.75rem 1rem', marginBottom: '1rem', color: '#fca5a5', fontSize: '0.85rem' }}>
            <strong>{quotaInfo.feature}:</strong> {quotaInfo.used}/{quotaInfo.limit} used this month
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', marginBottom: '1.25rem' }}>
          <PlanCard
            id="monthly" selected={selected === 'monthly'}
            label={monthly?.label || 'Pro Monthly'} price={monthly?.price_inr ?? 199}
            sub="per month" onClick={() => setSelected('monthly')}
          />
          <PlanCard
            id="yearly" selected={selected === 'yearly'}
            label={yearly?.label || 'Pro Yearly'} price={yearly?.price_inr ?? 1999}
            sub="per year" badge="Save 16%" onClick={() => setSelected('yearly')}
          />
        </div>

        <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 10, padding: '0.85rem 1rem', marginBottom: '1.25rem' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '0.3rem 0.4rem', color: '#94a3b8', fontWeight: 600 }}>Feature</th>
                <th style={{ textAlign: 'right', padding: '0.3rem 0.4rem', color: '#94a3b8', fontWeight: 600 }}>Free</th>
                <th style={{ textAlign: 'right', padding: '0.3rem 0.4rem', color: '#a855f7', fontWeight: 700 }}>Pro</th>
              </tr>
            </thead>
            <tbody>
              {FEATURES.map(([f, free, pro], i) => (
                <tr key={i} style={{ borderTop: '1px solid #334155' }}>
                  <td style={{ padding: '0.4rem', color: '#cbd5e1' }}>{f}</td>
                  <td style={{ padding: '0.4rem', textAlign: 'right', color: '#64748b' }}>{free}</td>
                  <td style={{ padding: '0.4rem', textAlign: 'right', color: '#e2e8f0', fontWeight: 600 }}>{pro}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem', flexDirection: showContinueFree ? 'row' : 'column' }}>
          <button
            onClick={startCheckout}
            disabled={busy}
            style={{
              flex: showContinueFree ? 2 : '1 1 auto',
              padding: '0.85rem', borderRadius: 10, border: 'none',
              background: busy ? '#475569' : 'linear-gradient(135deg,#7c3aed,#2563eb)',
              color: '#fff', fontWeight: 700, fontSize: '0.95rem',
              cursor: busy ? 'wait' : 'pointer',
            }}
          >
            {busy ? 'Opening checkout…' : `Pay ₹${selected === 'yearly' ? (yearly?.price_inr ?? 1999) : (monthly?.price_inr ?? 199)} via Razorpay`}
          </button>
          {showContinueFree && (
            <button
              onClick={onClose}
              style={{
                flex: 1, padding: '0.85rem', borderRadius: 10,
                border: '1px solid #334155', background: 'transparent',
                color: '#cbd5e1', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer',
              }}
            >
              Continue with Free
            </button>
          )}
        </div>
        <p style={{ marginTop: '0.6rem', fontSize: '0.72rem', color: '#64748b', textAlign: 'center' }}>
          Secure checkout via Razorpay · Cards · UPI · Net Banking
        </p>
      </div>
    </div>
  );
}

function PlanCard({ id, label, price, sub, badge, selected, onClick }) {
  return (
    <button onClick={onClick} style={{
      position: 'relative', textAlign: 'left', padding: '0.85rem 1rem', borderRadius: 10,
      background: selected ? 'rgba(124,58,237,0.15)' : '#1e293b',
      border: `1.5px solid ${selected ? '#7c3aed' : '#334155'}`,
      cursor: 'pointer', color: '#e2e8f0',
    }}>
      {badge && (
        <span style={{
          position: 'absolute', top: -8, right: 8, background: '#10b981', color: '#fff',
          fontSize: '0.65rem', padding: '0.1rem 0.5rem', borderRadius: 999, fontWeight: 700,
        }}>{badge}</span>
      )}
      <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '1.4rem', fontWeight: 800 }}>₹{price}</div>
      <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{sub}</div>
    </button>
  );
}

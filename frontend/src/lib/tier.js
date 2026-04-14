// Tier-aware singleton — fetches /api/tier/status once and caches in memory.
// Components subscribe via useTier() and re-render when the cached tier is updated
// (e.g. after a successful Pro upgrade).
import { useEffect, useState } from 'react';
import api from '@/lib/api';

let _cache = null;
const _listeners = new Set();

function notify() { _listeners.forEach(fn => fn(_cache)); }

export async function refreshTier() {
  try {
    const data = await api.get('/api/payment/tier/status');
    if (data && !data.error) {
      _cache = data;
      notify();
    }
  } catch { /* ignore */ }
  return _cache;
}

export function getTierSync() { return _cache; }

export function useTier() {
  const [data, setData] = useState(_cache);
  useEffect(() => {
    _listeners.add(setData);
    if (!_cache) refreshTier();
    return () => { _listeners.delete(setData); };
  }, []);
  return data;
}

export function isPaid(tier) { return tier === 'pro' || tier === 'admin'; }

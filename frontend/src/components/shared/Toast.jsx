'use client';
import { useEffect } from 'react';
import Alert from '@mui/material/Alert';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import InfoIcon from '@mui/icons-material/Info';

const CONFIG = {
  success: { icon: <CheckCircleIcon fontSize="small" />, bg: '#065f46', fg: '#6ee7b7', border: 'rgba(110,231,183,0.25)' },
  error:   { icon: <ErrorIcon fontSize="small" />,        bg: '#7f1d1d', fg: '#fca5a5', border: 'rgba(252,165,165,0.25)' },
  warning: { icon: <WarningAmberIcon fontSize="small" />, bg: '#78350f', fg: '#fcd34d', border: 'rgba(252,211,77,0.25)' },
  info:    { icon: <InfoIcon fontSize="small" />,         bg: '#1e3a5f', fg: '#93c5fd', border: 'rgba(147,197,253,0.25)' },
};

export default function Toast({ message, type, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 4000); return () => clearTimeout(t); }, [message]);
  const c = CONFIG[type] || CONFIG.info;
  return (
    <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, maxWidth: 420, minWidth: 280, animation: 'fadeIn 0.25s ease' }}>
      <Alert
        severity={type || 'info'}
        icon={c.icon}
        onClose={onClose}
        sx={{
          background: c.bg,
          color: c.fg,
          border: `1px solid ${c.border}`,
          borderRadius: '12px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.55)',
          fontWeight: 500,
          fontSize: '0.9rem',
          alignItems: 'center',
          '& .MuiAlert-icon': { color: c.fg, marginRight: '10px' },
          '& .MuiAlert-action button': { color: c.fg, opacity: 0.75, '&:hover': { opacity: 1 } },
        }}
      >
        {message}
      </Alert>
    </div>
  );
}

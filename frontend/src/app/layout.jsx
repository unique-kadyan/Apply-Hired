import './globals.css';

export const metadata = {
  title: 'Kalibr — Calibrate your career',
  description: 'AI-powered job application platform: smart search, ATS-optimized resumes, and auto-detected interviews & offers.',
};

const FAVICON_SVG =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <defs><linearGradient id="g" x1="0%" y1="100%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#2563eb"/><stop offset="55%" stop-color="#3b82f6"/><stop offset="100%" stop-color="#7c3aed"/>
      </linearGradient></defs>
      <path d="M22 14H34V86H22Z" fill="url(#g)"/>
      <path d="M34 50L66 18H82L50 50Z" fill="url(#g)"/>
      <path d="M34 50H50L82 86H66Z" fill="url(#g)" opacity="0.78"/>
      <circle cx="84" cy="14" r="4.5" fill="#60a5fa"/>
    </svg>`
  );

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" type="image/svg+xml" href={FAVICON_SVG} />
        <script src="https://checkout.razorpay.com/v1/checkout.js" async />
      </head>
      <body>{children}</body>
    </html>
  );
}

import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Pulse — Attention radar', description: 'Explore accelerating Hacker News stories and the evidence behind them.' };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }

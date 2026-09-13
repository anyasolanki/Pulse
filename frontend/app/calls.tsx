'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowUpRight, Check, CircleAlert, Clock3, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Empty } from '@/components/ui/empty';
import { Skeleton } from '@/components/ui/skeleton';
import { localUserHeaders } from '@/lib/local-user';

type Prediction = { id: string; story_id: number; story_title: string; call: 'yes' | 'no'; confidence: number; status: 'pending' | 'resolved' | 'unverifiable'; created_at: string; expires_at: string; correct: boolean | null; first_qualified_at: string | null };
type Profile = { total: number; pending: number; resolved: number; unverifiable: number; scored: number; correct: number; accuracy: number | null; average_early_minutes: number | null };
const date = (value: string) => new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
const duration = (minutes: number | null) => minutes === null ? '—' : `${Math.floor(minutes / 60)}h ${Math.round(minutes % 60)}m`;

export default function Calls({ onOpen }: { onOpen: (id: number) => void }) {
  const [calls, setCalls] = useState<Prediction[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      await fetch('/api/pulse/v1/predictions/resolve', { method: 'POST', headers: localUserHeaders() });
      const [callsResponse, profileResponse] = await Promise.all([fetch('/api/pulse/v1/predictions', { headers: localUserHeaders() }), fetch('/api/pulse/v1/profile', { headers: localUserHeaders() })]);
      const data = await callsResponse.json() as { predictions?: Prediction[]; detail?: string };
      const profileData = await profileResponse.json() as Profile & { detail?: string };
      if (!callsResponse.ok) throw new Error(data.detail || 'Could not load your calls.');
      if (!profileResponse.ok) throw new Error(profileData.detail || 'Could not load your record.');
      setCalls(data.predictions || []); setProfile(profileData); setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load your calls.'); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return <section className="calls"><div className="calls-heading"><div><p className="eyebrow">YOUR LOCAL FORECASTS</p><h2>My calls<span className="heading-dot">.</span></h2><p className="intro">Each call is locked to this browser and checked after 24 hours.</p></div><Button variant="outline" className="refresh" onClick={refresh} disabled={busy}>{busy ? 'Checking' : 'Refresh results'}</Button></div>
    {error && <div role="alert" className="notice error">{error}</div>}
    {busy && !calls.length ? <div className="loading"><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div> : !calls.length ? <Empty className="quiet"><Clock3 size={32}/><h3>No calls yet.</h3><p>Open a Hacker News story and make a 24-hour call about whether it will enter Pulse’s top ten signals.</p><span className="quiet-tag">Your history stays on this browser.</span></Empty> : <><section className="record-grid" aria-label="Your prediction record"><div><span>VERIFIED ACCURACY</span><strong>{profile?.accuracy === null || profile?.accuracy === undefined ? '—' : `${Math.round(profile.accuracy)}%`}</strong><small>{profile?.scored || 0} resolved call{profile?.scored === 1 ? '' : 's'}</small></div><div><span>AVERAGE LEAD TIME</span><strong>{duration(profile?.average_early_minutes ?? null)}</strong><small>correct YES calls</small></div><div><span>PREDICTIONS</span><strong>{profile?.total || 0}</strong><small>{profile?.pending || 0} waiting to resolve</small></div></section><div className="calls-list">{calls.map(call => <article key={call.id} className="call-card"><div className="call-status">{call.status === 'pending' ? <Clock3/> : call.correct ? <Check/> : call.status === 'unverifiable' ? <CircleAlert/> : <X/>}</div><div className="call-main"><p className="eyebrow">{call.status === 'pending' ? `LOCKED · CHECKS ${date(call.expires_at)}` : call.status === 'unverifiable' ? 'UNVERIFIABLE · COLLECTION GAP' : call.correct ? 'CORRECT' : 'INCORRECT'}</p><h3>{call.story_title}</h3><p>You called <strong>{call.call.toUpperCase()}</strong> at <strong>{call.confidence}%</strong> confidence — would it reach Pulse’s top 10 HN signals within 24 hours?</p>{call.status === 'resolved' && <small>{call.first_qualified_at ? `It qualified at ${date(call.first_qualified_at)}.` : 'It never reached a top-ten detector snapshot.'}</small>}{call.status === 'unverifiable' && <small>Pulse did not have enough continuous collection history to judge this fairly.</small>}</div><Button variant="ghost" size="icon" aria-label={`Investigate ${call.story_title}`} onClick={() => onOpen(call.story_id)}><ArrowUpRight/></Button></article>)}</div></>}
  </section>;
}

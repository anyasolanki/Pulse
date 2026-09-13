'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowUpRight, Bookmark, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Empty } from '@/components/ui/empty';
import { Skeleton } from '@/components/ui/skeleton';
import { localUserHeaders } from '@/lib/local-user';

type Watch = { story_id: number; story_title: string; story_url: string | null; created_at: string };
const date = (value: string) => new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

export default function Watchlist({ onOpen }: { onOpen: (id: number) => void }) {
  const [items, setItems] = useState<Watch[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const response = await fetch('/api/pulse/v1/watchlist', { headers: localUserHeaders() });
      const data = await response.json() as { watchlist?: Watch[]; detail?: string };
      if (!response.ok) throw new Error(data.detail || 'Could not load your watchlist.');
      setItems(data.watchlist || []); setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load your watchlist.'); }
    finally { setBusy(false); }
  }, []);
  const remove = async (storyId: number) => {
    try {
      const response = await fetch(`/api/pulse/v1/watchlist/${storyId}`, { method: 'DELETE', headers: localUserHeaders() });
      if (!response.ok) throw new Error('Could not remove this story.');
      setItems(current => current.filter(item => item.story_id !== storyId));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not remove this story.'); }
  };
  useEffect(() => { void refresh(); }, [refresh]);
  return <section className="watchlist"><div className="calls-heading"><div><p className="eyebrow">YOUR LOCAL SHORTLIST</p><h2>Watchlist<span className="heading-dot">.</span></h2><p className="intro">Saved stories stay on this browser for easy return visits.</p></div><Button variant="outline" className="refresh" onClick={refresh} disabled={busy}>{busy ? 'Loading' : 'Refresh'}</Button></div>
    {error && <div role="alert" className="notice error">{error}</div>}
    {busy && !items.length ? <div className="loading"><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div> : !items.length ? <Empty className="quiet"><Bookmark size={32}/><h3>Nothing saved yet.</h3><p>Open a Hacker News story and choose Watch story to keep it here.</p><span className="quiet-tag">Your watchlist stays on this browser.</span></Empty> : <div className="watch-list">{items.map(item => <article className="watch-card" key={item.story_id}><Bookmark className="watch-mark"/><div className="watch-main"><p className="eyebrow">WATCHING SINCE {date(item.created_at)}</p><h3>{item.story_title}</h3><p>Hacker News story #{item.story_id}</p></div><div className="watch-actions"><Button variant="ghost" size="icon" aria-label={`Investigate ${item.story_title}`} onClick={() => onOpen(item.story_id)}><ArrowUpRight/></Button><Button variant="ghost" size="icon" aria-label={`Remove ${item.story_title} from watchlist`} onClick={() => void remove(item.story_id)}><Trash2/></Button></div></article>)}</div>}
  </section>;
}

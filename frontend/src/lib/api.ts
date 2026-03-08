const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message || `API error: ${res.status}`);
  }

  return res.json();
}

// Wrestlers
export function getWrestlers(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return apiFetch<any>(`/api/wrestlers${qs}`);
}

export function getWrestler(id: number) {
  return apiFetch<any>(`/api/wrestlers/${id}`);
}

export function getWrestlerMatches(id: number, params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return apiFetch<any>(`/api/wrestlers/${id}/matches${qs}`);
}

export function getWrestlerStats(id: number) {
  return apiFetch<any>(`/api/wrestlers/${id}/stats`);
}

export function getWrestlerTitles(id: number) {
  return apiFetch<any>(`/api/wrestlers/${id}/titles`);
}

// Charts
export function getWrestlerWinRateChart(id: number) {
  return apiFetch<any>(`/api/wrestlers/${id}/charts/win-rate`);
}

export function getWrestlerMomentumChart(id: number) {
  return apiFetch<any>(`/api/wrestlers/${id}/charts/momentum`);
}

export function getWrestlerStreaksChart(id: number) {
  return apiFetch<any>(`/api/wrestlers/${id}/charts/streaks`);
}

export function getWrestlerActivityChart(id: number) {
  return apiFetch<any>(`/api/wrestlers/${id}/charts/activity`);
}

// Matches
export function getMatches(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return apiFetch<any>(`/api/matches${qs}`);
}

export function getMatch(id: number) {
  return apiFetch<any>(`/api/matches/${id}`);
}

// Events
export function getEvents(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return apiFetch<any>(`/api/events${qs}`);
}

export function getEvent(id: number) {
  return apiFetch<any>(`/api/events/${id}`);
}

// Head-to-Head
export function getHeadToHead(id1: number, id2: number) {
  return apiFetch<any>(`/api/head-to-head/${id1}/${id2}`);
}

// Titles
export function getTitles() {
  return apiFetch<any>('/api/titles');
}

export function getTitleHistory(id: number) {
  return apiFetch<any>(`/api/titles/${id}/history`);
}

// Predict
export function predict(body: {
  wrestler_ids: number[];
  match_type?: string;
  event_tier?: string;
  title_match?: boolean;
}) {
  return apiFetch<any>('/api/predict', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

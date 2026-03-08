"use client";

import { useEffect, useState } from "react";
import {
  WinRateTimeline,
  MomentumCurve,
  StreakHistory,
  MatchTypeRadar,
  TitleTimeline,
  ActivityHeatmap,
} from "@/components/charts";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

async function fetchChart(url: string) {
  try {
    const res = await fetch(`${API_BASE}${url}`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.data || [];
  } catch {
    return [];
  }
}

interface MatchTypeBreakdown {
  match_type: string;
  total: number;
  wins: number;
}

interface TitleReign {
  title_name: string;
  won_date: string;
  lost_date: string | null;
  defenses: number;
  promotion: string;
}

interface WrestlerChartsProps {
  wrestlerId: number;
  matchTypeBreakdown: MatchTypeBreakdown[];
  titleReigns: TitleReign[];
}

export default function WrestlerCharts({
  wrestlerId,
  matchTypeBreakdown,
  titleReigns,
}: WrestlerChartsProps) {
  const [winRate, setWinRate] = useState<any[]>([]);
  const [momentum, setMomentum] = useState<any[]>([]);
  const [streaks, setStreaks] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchChart(`/api/wrestlers/${wrestlerId}/charts/win-rate`),
      fetchChart(`/api/wrestlers/${wrestlerId}/charts/momentum`),
      fetchChart(`/api/wrestlers/${wrestlerId}/charts/streaks`),
      fetchChart(`/api/wrestlers/${wrestlerId}/charts/activity`),
    ]).then(([wr, mo, st, ac]) => {
      setWinRate(wr);
      setMomentum(mo);
      setStreaks(st);
      setActivity(ac);
      setLoading(false);
    });
  }, [wrestlerId]);

  // Transform match type breakdown for radar chart
  const radarData = matchTypeBreakdown
    .filter((d) => d.total >= 3)
    .map((d) => ({
      match_type: d.match_type,
      win_rate: d.total > 0 ? Number(d.wins) / Number(d.total) : 0,
      total: Number(d.total),
    }));

  // Transform win rate for timeline
  const winRateData = winRate.map((d: any) => ({
    date: d.month,
    win_rate: Number(d.win_rate),
    matches: Number(d.total),
  }));

  // Transform momentum data
  const momentumData = momentum.map((d: any) => ({
    date: d.date,
    momentum: Number(d.momentum),
    push_score: Number(d.push_score),
  }));

  // Transform streaks — StreakHistory expects { period, win_streak, loss_streak }
  const streakData = streaks.map((d: any) => ({
    period: d.date,
    win_streak: Number(d.win_streak) || 0,
    loss_streak: Number(d.loss_streak) || 0,
  }));

  return (
    <div className="space-y-8">
      <h2 className="text-xl font-semibold">Analytics</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Win Rate Timeline */}
        <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Win Rate Over Time</h3>
          <WinRateTimeline data={winRateData} loading={loading} />
        </div>

        {/* Momentum Curve */}
        <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Momentum & Push Score</h3>
          <MomentumCurve data={momentumData} loading={loading} />
        </div>

        {/* Match Type Radar */}
        <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Win Rate by Match Type</h3>
          <MatchTypeRadar data={radarData} loading={false} />
        </div>

        {/* Streak History */}
        <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Streak History</h3>
          <StreakHistory data={streakData} loading={loading} />
        </div>
      </div>

      {/* Full-width charts */}
      {titleReigns.length > 0 && (
        <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Championship Timeline</h3>
          <TitleTimeline data={titleReigns} loading={false} />
        </div>
      )}

      <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-sm font-medium text-zinc-400 mb-3">Match Activity (Last 12 Months)</h3>
        <ActivityHeatmap data={activity} loading={loading} />
      </div>
    </div>
  );
}

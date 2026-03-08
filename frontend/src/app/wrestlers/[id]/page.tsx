import { Metadata } from "next";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import WrestlerCharts from "@/components/WrestlerCharts";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

async function fetchWrestler(id: string) {
  const res = await fetch(`${API_BASE}/api/wrestlers/${id}`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) return null;
  const json = await res.json();
  return json.data;
}

async function fetchStats(id: string) {
  const res = await fetch(`${API_BASE}/api/wrestlers/${id}/stats`, {
    next: { revalidate: 600 },
  });
  if (!res.ok) return null;
  const json = await res.json();
  return json.data;
}

async function fetchMatches(id: string) {
  const res = await fetch(`${API_BASE}/api/wrestlers/${id}/matches?limit=20`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) return [];
  const json = await res.json();
  return json.data;
}

async function fetchTitles(id: string) {
  const res = await fetch(`${API_BASE}/api/wrestlers/${id}/titles`, {
    next: { revalidate: 600 },
  });
  if (!res.ok) return [];
  const json = await res.json();
  return json.data;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const wrestler = await fetchWrestler(id);
  if (!wrestler) return { title: "Wrestler Not Found" };
  return {
    title: wrestler.ring_name,
    description: `Career stats, match history, and analytics for ${wrestler.ring_name}. ${wrestler.total_matches} matches, ${wrestler.total_wins} wins.`,
    openGraph: {
      title: `${wrestler.ring_name} | Ringside Analytics`,
      description: `Career stats and match history for ${wrestler.ring_name}`,
    },
  };
}

export default async function WrestlerProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [wrestler, stats, matches, titles] = await Promise.all([
    fetchWrestler(id),
    fetchStats(id),
    fetchMatches(id),
    fetchTitles(id),
  ]);

  if (!wrestler) notFound();

  const winRate =
    wrestler.total_matches > 0
      ? ((wrestler.total_wins / wrestler.total_matches) * 100).toFixed(1)
      : "0";

  // JSON-LD structured data for search engines — data is from our own DB, not user input
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: wrestler.ring_name,
    alternateName: wrestler.real_name || undefined,
    description: `Professional wrestler with ${wrestler.total_matches} career matches`,
    jobTitle: "Professional Wrestler",
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold">{wrestler.ring_name}</h1>
          <Badge variant="outline" className="border-zinc-600">
            {wrestler.promotion}
          </Badge>
        </div>
        {wrestler.real_name && (
          <p className="text-zinc-500">{wrestler.real_name}</p>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Matches" value={wrestler.total_matches} />
        <StatCard label="Wins" value={wrestler.total_wins} />
        <StatCard label="Win Rate" value={`${winRate}%`} />
        <StatCard
          label="Status"
          value={wrestler.status}
          className="capitalize"
        />
      </div>

      {/* Rolling Stats */}
      {stats?.rolling && (
        <>
          <h2 className="text-xl font-semibold mb-4">Current Form</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard
              label="30-Day Win Rate"
              value={`${((stats.rolling.win_rate_30d || 0) * 100).toFixed(0)}%`}
            />
            <StatCard
              label="90-Day Win Rate"
              value={`${((stats.rolling.win_rate_90d || 0) * 100).toFixed(0)}%`}
            />
            <StatCard
              label="Momentum"
              value={((stats.rolling.momentum_score || 0) * 100).toFixed(0)}
            />
            <StatCard
              label="Push Score"
              value={((stats.rolling.push_score || 0) * 100).toFixed(0)}
            />
          </div>
        </>
      )}

      <Separator className="bg-zinc-800 mb-8" />

      {/* Charts Section */}
      <WrestlerCharts
        wrestlerId={wrestler.id}
        matchTypeBreakdown={stats?.match_type_breakdown || []}
        titleReigns={titles}
      />

      <Separator className="bg-zinc-800 my-8" />

      {/* Title History */}
      {titles.length > 0 && (
        <>
          <h2 className="text-xl font-semibold mb-4">Championship History</h2>
          <div className="space-y-2 mb-8">
            {titles.map((t: any) => (
              <div
                key={t.id}
                className="flex items-center justify-between p-3 rounded-lg border border-zinc-800 bg-zinc-900/50"
              >
                <div>
                  <span className="font-medium">{t.title_name}</span>
                  <span className="text-zinc-500 text-sm ml-2">
                    ({t.promotion})
                  </span>
                </div>
                <div className="text-sm text-zinc-400">
                  {t.won_date} — {t.lost_date || "Current"}
                  {t.defenses > 0 && (
                    <span className="ml-2 text-zinc-500">
                      ({t.defenses} defenses)
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Recent Matches */}
      <h2 className="text-xl font-semibold mb-4">Recent Matches</h2>
      {matches.length > 0 ? (
        <div className="space-y-2">
          {matches.map((m: any) => (
            <div
              key={m.id}
              className="flex items-center justify-between p-3 rounded-lg border border-zinc-800 bg-zinc-900/50"
            >
              <div className="flex items-center gap-3">
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded ${
                    m.result === "win"
                      ? "bg-emerald-500/10 text-emerald-400"
                      : m.result === "loss"
                        ? "bg-red-500/10 text-red-400"
                        : "bg-zinc-500/10 text-zinc-400"
                  }`}
                >
                  {m.result?.toUpperCase()}
                </span>
                <div>
                  <span className="text-sm">{m.event_name}</span>
                  <span className="text-zinc-500 text-xs ml-2">
                    {m.match_type}
                  </span>
                </div>
              </div>
              <span className="text-xs text-zinc-500">{m.event_date}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-zinc-500">No match history available.</p>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string | number;
  className?: string;
}) {
  return (
    <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${className}`}>{value}</p>
    </div>
  );
}

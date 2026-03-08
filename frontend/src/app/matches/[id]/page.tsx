import { notFound } from "next/navigation";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import PageContainer from "@/components/PageContainer";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

async function fetchMatch(id: string) {
  const res = await fetch(`${API_BASE}/api/matches/${id}`, {
    next: { revalidate: 600 },
  });
  if (!res.ok) return null;
  const json = await res.json();
  return json.data;
}

export default async function MatchDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const match = await fetchMatch(id);
  if (!match) notFound();

  return (
    <PageContainer>
      <div className="mb-6">
        <Link
          href={`/events/${match.event_id}`}
          className="text-amber-400 hover:text-amber-300 text-sm"
        >
          {match.event_name}
        </Link>
        <p className="text-xs text-zinc-500 mt-1">
          {match.event_date}
          {match.venue && ` — ${match.venue}`}
          {match.city && `, ${match.city}`}
        </p>
      </div>

      <div className="p-6 rounded-xl border border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-2 mb-4">
          <Badge variant="outline" className="border-zinc-700 text-zinc-400">
            {match.match_type.replace(/_/g, " ")}
          </Badge>
          {match.title_match && (
            <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/30">
              Title Match
            </Badge>
          )}
          <Badge variant="outline" className="border-zinc-700 text-zinc-400">
            {match.promotion}
          </Badge>
        </div>

        {match.stipulation && (
          <p className="text-sm text-zinc-400 italic mb-4">
            {match.stipulation}
          </p>
        )}

        {/* Participants */}
        <div className="space-y-2 mb-4">
          {match.participants?.map((p: any) => (
            <Link
              key={p.wrestler_id}
              href={`/wrestlers/${p.wrestler_id}`}
              className="flex items-center justify-between p-3 rounded-lg border border-zinc-800 hover:border-zinc-600 transition-colors"
            >
              <span className="font-medium">{p.ring_name}</span>
              <span
                className={`text-xs font-semibold px-2 py-1 rounded ${
                  p.result === "win"
                    ? "bg-emerald-500/10 text-emerald-400"
                    : p.result === "loss"
                      ? "bg-red-500/10 text-red-400"
                      : "bg-zinc-500/10 text-zinc-400"
                }`}
              >
                {p.result?.toUpperCase()}
              </span>
            </Link>
          ))}
        </div>

        {/* Details */}
        <div className="grid grid-cols-2 gap-4 text-sm text-zinc-400">
          {match.duration_seconds && (
            <div>
              <span className="text-zinc-600">Duration: </span>
              {Math.floor(match.duration_seconds / 60)}:
              {String(match.duration_seconds % 60).padStart(2, "0")}
            </div>
          )}
          {match.rating && (
            <div>
              <span className="text-zinc-600">Rating: </span>
              {match.rating} / 5
            </div>
          )}
        </div>
      </div>
    </PageContainer>
  );
}

import { notFound } from "next/navigation";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import PageContainer from "@/components/PageContainer";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

async function fetchEvent(id: string) {
  const res = await fetch(`${API_BASE}/api/events/${id}`, {
    next: { revalidate: 600 },
  });
  if (!res.ok) return null;
  const json = await res.json();
  return json.data;
}

export default async function EventDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const event = await fetchEvent(id);
  if (!event) notFound();

  return (
    <PageContainer>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold">{event.name}</h1>
          <Badge variant="outline" className="border-zinc-600">
            {event.promotion}
          </Badge>
        </div>
        <p className="text-zinc-400">
          {event.date}
          {event.venue && ` — ${event.venue}`}
          {event.city && `, ${event.city}`}
          {event.country && `, ${event.country}`}
        </p>
      </div>

      {/* Match Card */}
      <h2 className="text-xl font-semibold mb-4">Match Card</h2>
      <div className="space-y-3">
        {event.matches?.map((match: any, idx: number) => (
          <div
            key={match.id}
            className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-600 font-mono">
                  #{idx + 1}
                </span>
                <Badge
                  variant="outline"
                  className="border-zinc-700 text-zinc-400 text-xs"
                >
                  {match.match_type.replace(/_/g, " ")}
                </Badge>
                {match.title_match && (
                  <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/30 text-xs">
                    Title Match
                  </Badge>
                )}
              </div>
              {match.rating && (
                <span className="text-xs text-zinc-400">
                  {match.rating} stars
                </span>
              )}
            </div>

            {match.stipulation && (
              <p className="text-xs text-zinc-500 mb-2 italic">
                {match.stipulation}
              </p>
            )}

            {/* Participants */}
            <div className="flex flex-wrap gap-2">
              {match.participants?.map((p: any, i: number) => (
                <Link
                  key={`${p.wrestler_id}-${i}`}
                  href={`/wrestlers/${p.wrestler_id}`}
                  className={`text-sm px-2 py-1 rounded transition-colors ${
                    p.result === "win"
                      ? "bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                      : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                  }`}
                >
                  {p.ring_name}
                  {p.result === "win" && " ★"}
                </Link>
              ))}
            </div>

            {match.duration_seconds && (
              <p className="text-xs text-zinc-600 mt-2">
                {Math.floor(match.duration_seconds / 60)}:
                {String(match.duration_seconds % 60).padStart(2, "0")}
              </p>
            )}
          </div>
        ))}
      </div>

      {(!event.matches || event.matches.length === 0) && (
        <p className="text-zinc-500 text-center py-12">
          No match card available for this event.
        </p>
      )}
    </PageContainer>
  );
}

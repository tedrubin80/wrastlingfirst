import Link from "next/link";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

async function fetchEvents(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/api/events?${qs}&limit=30`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) return { data: [], pagination: { has_more: false } };
  return res.json();
}

export default async function EventsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string>>;
}) {
  const params = await searchParams;
  const filters: Record<string, string> = {};
  if (params.promotion) filters.promotion = params.promotion;
  if (params.year) filters.year = params.year;
  if (params.event_type) filters.event_type = params.event_type;

  const { data: events } = await fetchEvents(filters);

  const typeLabel: Record<string, string> = {
    ppv: "PPV",
    weekly_tv: "TV",
    special: "Special",
    house_show: "House Show",
    tournament: "Tournament",
  };

  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Events</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-6">
        <FilterLink href="/events" label="All" active={!params.promotion} />
        {["WWE", "AEW", "NXT"].map((p) => (
          <FilterLink
            key={p}
            href={`/events?promotion=${p}`}
            label={p}
            active={params.promotion === p}
          />
        ))}
        <span className="border-l border-zinc-700 mx-2" />
        {["ppv", "weekly_tv", "special"].map((t) => (
          <FilterLink
            key={t}
            href={`/events?event_type=${t}${params.promotion ? `&promotion=${params.promotion}` : ""}`}
            label={typeLabel[t] || t}
            active={params.event_type === t}
          />
        ))}
      </div>

      {/* Event List */}
      <div className="space-y-2">
        {events.map((e: any) => (
          <Link
            key={e.id}
            href={`/events/${e.id}`}
            className="flex items-center justify-between p-4 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:border-zinc-600 transition-all group"
          >
            <div>
              <span className="font-semibold group-hover:text-amber-400 transition-colors">
                {e.name}
              </span>
              <div className="flex items-center gap-2 mt-1 text-xs text-zinc-500">
                <Badge
                  variant="outline"
                  className="border-zinc-700 text-zinc-400"
                >
                  {e.promotion}
                </Badge>
                <span>{typeLabel[e.event_type] || e.event_type}</span>
                {e.city && <span>{e.city}</span>}
              </div>
            </div>
            <div className="text-right">
              <span className="text-sm text-zinc-400">{e.date}</span>
              <p className="text-xs text-zinc-600">
                {e.match_count} match{e.match_count !== 1 ? "es" : ""}
              </p>
            </div>
          </Link>
        ))}
      </div>

      {events.length === 0 && (
        <p className="text-zinc-500 text-center py-12">
          No events found. Try adjusting your filters.
        </p>
      )}
    </div>
  );
}

function FilterLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
        active
          ? "bg-amber-500/10 border-amber-500 text-amber-400"
          : "border-zinc-700 text-zinc-400 hover:border-zinc-500"
      }`}
    >
      {label}
    </Link>
  );
}

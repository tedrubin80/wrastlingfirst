import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import PageContainer from "@/components/PageContainer";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

interface Wrestler {
  id: number;
  ring_name: string;
  promotion: string;
  gender: string;
  status: string;
  brand: string;
}

async function fetchWrestlers(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/api/wrestlers?${qs}&limit=50`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) return { data: [], pagination: { has_more: false } };
  return res.json();
}

export default async function WrestlersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string>>;
}) {
  const params = await searchParams;
  const filters: Record<string, string> = {};
  if (params.promotion) filters.promotion = params.promotion;
  if (params.gender) filters.gender = params.gender;
  if (params.status) filters.status = params.status;
  if (params.q) filters.q = params.q;

  const { data: wrestlers } = await fetchWrestlers(filters);

  const promotionColor: Record<string, string> = {
    WWE: "border-blue-500 text-blue-400",
    AEW: "border-yellow-500 text-yellow-400",
    NXT: "border-purple-500 text-purple-400",
    WCW: "border-red-500 text-red-400",
    ECW: "border-green-500 text-green-400",
    TNA: "border-orange-500 text-orange-400",
  };

  const statusColor: Record<string, string> = {
    active: "bg-emerald-500/10 text-emerald-400",
    injured: "bg-red-500/10 text-red-400",
    inactive: "bg-zinc-500/10 text-zinc-400",
    free_agent: "bg-amber-500/10 text-amber-400",
  };

  return (
    <PageContainer>
      <h1 className="text-3xl font-bold mb-6">Wrestlers</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-6">
        <FilterLink href="/wrestlers" label="All" active={!params.promotion} />
        {["WWE", "AEW", "NXT"].map((p) => (
          <FilterLink
            key={p}
            href={`/wrestlers?promotion=${p}`}
            label={p}
            active={params.promotion === p}
          />
        ))}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {wrestlers.map((w: Wrestler) => (
          <Link
            key={w.id}
            href={`/wrestlers/${w.id}`}
            className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:border-zinc-600 transition-all group"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold group-hover:text-amber-400 transition-colors">
                {w.ring_name}
              </span>
              <Badge
                variant="outline"
                className={promotionColor[w.promotion] || "border-zinc-600"}
              >
                {w.promotion}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span
                className={`px-2 py-0.5 rounded-full ${statusColor[w.status] || ""}`}
              >
                {w.status}
              </span>
              {w.brand && <span>{w.brand}</span>}
            </div>
          </Link>
        ))}
      </div>

      {wrestlers.length === 0 && (
        <p className="text-zinc-500 text-center py-12">
          No wrestlers found. Try adjusting your filters.
        </p>
      )}
    </PageContainer>
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

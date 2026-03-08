"use client";

import { Skeleton } from "@/components/ui/skeleton";

interface Reign {
  title_name: string;
  won_date: string;
  lost_date: string | null;
  defenses: number;
  promotion: string;
}

interface TitleTimelineProps {
  data: Reign[];
  loading?: boolean;
}

export default function TitleTimeline({
  data,
  loading = false,
}: TitleTimelineProps) {
  if (loading) return <Skeleton className="w-full h-40 bg-zinc-800" />;
  if (data.length === 0)
    return (
      <div className="flex items-center justify-center h-24 text-zinc-500 text-sm">
        No title reigns
      </div>
    );

  // Find date range
  const allDates = data.flatMap((r) => [
    new Date(r.won_date).getTime(),
    r.lost_date ? new Date(r.lost_date).getTime() : Date.now(),
  ]);
  const minDate = Math.min(...allDates);
  const maxDate = Math.max(...allDates);
  const range = maxDate - minDate || 1;

  const colors = [
    "#f59e0b", "#3b82f6", "#10b981", "#8b5cf6",
    "#ef4444", "#ec4899", "#06b6d4", "#84cc16",
  ];

  return (
    <div className="w-full space-y-2">
      {data.map((reign, idx) => {
        const start = new Date(reign.won_date).getTime();
        const end = reign.lost_date
          ? new Date(reign.lost_date).getTime()
          : Date.now();
        const left = ((start - minDate) / range) * 100;
        const width = Math.max(((end - start) / range) * 100, 1);
        const color = colors[idx % colors.length];

        return (
          <div key={idx} className="relative">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-zinc-400 w-40 truncate">
                {reign.title_name}
              </span>
              <span className="text-xs text-zinc-600">
                {reign.won_date} — {reign.lost_date || "Current"}
              </span>
            </div>
            <div className="relative h-5 bg-zinc-900 rounded-full overflow-hidden">
              <div
                className="absolute h-full rounded-full transition-all"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  backgroundColor: color,
                  opacity: 0.7,
                }}
                title={`${reign.title_name}: ${reign.won_date} — ${reign.lost_date || "Current"} (${reign.defenses} defenses)`}
              />
            </div>
          </div>
        );
      })}
      {/* Date axis */}
      <div className="flex justify-between text-xs text-zinc-600 mt-1">
        <span>{new Date(minDate).getFullYear()}</span>
        <span>{new Date(maxDate).getFullYear()}</span>
      </div>
    </div>
  );
}

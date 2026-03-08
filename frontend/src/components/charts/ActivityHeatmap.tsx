"use client";

import { Skeleton } from "@/components/ui/skeleton";

interface DataPoint {
  date: string;
  count: number;
}

interface ActivityHeatmapProps {
  data: DataPoint[];
  loading?: boolean;
}

export default function ActivityHeatmap({
  data,
  loading = false,
}: ActivityHeatmapProps) {
  if (loading) return <Skeleton className="w-full h-32 bg-zinc-800" />;
  if (data.length === 0)
    return (
      <div className="flex items-center justify-center h-32 text-zinc-500 text-sm">
        No activity data
      </div>
    );

  // Build a map of date -> count
  const countMap = new Map(data.map((d) => [d.date, d.count]));
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  // Generate last 52 weeks of cells
  const today = new Date();
  const weeks: { date: string; count: number }[][] = [];
  let currentWeek: { date: string; count: number }[] = [];

  for (let i = 364; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split("T")[0];
    const count = countMap.get(dateStr) || 0;
    currentWeek.push({ date: dateStr, count });

    if (d.getDay() === 6 || i === 0) {
      weeks.push(currentWeek);
      currentWeek = [];
    }
  }

  function getColor(count: number): string {
    if (count === 0) return "#18181b";
    const intensity = Math.min(count / maxCount, 1);
    if (intensity < 0.25) return "#422006";
    if (intensity < 0.5) return "#78350f";
    if (intensity < 0.75) return "#b45309";
    return "#f59e0b";
  }

  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];

  return (
    <div className="w-full overflow-x-auto">
      {/* Month labels */}
      <div className="flex gap-0.5 mb-1 ml-8">
        {weeks.map((week, wi) => {
          const firstDay = new Date(week[0].date);
          const showMonth = firstDay.getDate() <= 7;
          return (
            <div key={wi} className="w-3 text-center">
              {showMonth && (
                <span className="text-[9px] text-zinc-600">
                  {months[firstDay.getMonth()]}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Heatmap grid */}
      <div className="flex gap-0.5">
        {/* Day labels */}
        <div className="flex flex-col gap-0.5 text-[9px] text-zinc-600 w-7">
          <span className="h-3" />
          <span className="h-3">Mon</span>
          <span className="h-3" />
          <span className="h-3">Wed</span>
          <span className="h-3" />
          <span className="h-3">Fri</span>
          <span className="h-3" />
        </div>

        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-0.5">
            {[0, 1, 2, 3, 4, 5, 6].map((dayOfWeek) => {
              const cell = week.find(
                (d) => new Date(d.date).getDay() === dayOfWeek
              );
              return (
                <div
                  key={dayOfWeek}
                  className="w-3 h-3 rounded-sm"
                  style={{ backgroundColor: getColor(cell?.count || 0) }}
                  title={
                    cell
                      ? `${cell.date}: ${cell.count} match${cell.count !== 1 ? "es" : ""}`
                      : ""
                  }
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-1 mt-2 text-[10px] text-zinc-500">
        <span>Less</span>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <div
            key={v}
            className="w-3 h-3 rounded-sm"
            style={{ backgroundColor: getColor(v * maxCount) }}
          />
        ))}
        <span>More</span>
      </div>
    </div>
  );
}

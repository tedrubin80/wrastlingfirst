"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface DataPoint {
  period: string;
  win_streak: number;
  loss_streak: number;
}

interface StreakHistoryProps {
  data: DataPoint[];
  loading?: boolean;
}

export default function StreakHistory({
  data,
  loading = false,
}: StreakHistoryProps) {
  if (loading) return <Skeleton className="w-full h-64 bg-zinc-800" />;
  if (data.length === 0)
    return (
      <div className="flex items-center justify-center h-64 text-zinc-500 text-sm">
        No data available
      </div>
    );

  // Transform: positive for wins, negative for losses
  const chartData = data.map((d) => ({
    period: d.period,
    streak: d.win_streak > 0 ? d.win_streak : -d.loss_streak,
  }));

  return (
    <div className="w-full h-64">
      <ResponsiveContainer>
        <BarChart
          data={chartData}
          margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis
            dataKey="period"
            tick={{ fill: "#71717a", fontSize: 12 }}
            tickLine={{ stroke: "#3f3f46" }}
          />
          <YAxis
            tick={{ fill: "#71717a", fontSize: 12 }}
            tickLine={{ stroke: "#3f3f46" }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: "8px",
              color: "#fafafa",
            }}
            formatter={(value: any) => [
              `${Math.abs(value)} ${value >= 0 ? "wins" : "losses"}`,
              "Best Streak",
            ]}
          />
          <Bar dataKey="streak" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, idx) => (
              <Cell
                key={idx}
                fill={entry.streak >= 0 ? "#10b981" : "#ef4444"}
                fillOpacity={0.8}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

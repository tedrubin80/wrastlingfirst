"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface DataPoint {
  date: string;
  win_rate: number;
}

interface WinRateTimelineProps {
  data: DataPoint[];
  loading?: boolean;
}

export default function WinRateTimeline({
  data,
  loading = false,
}: WinRateTimelineProps) {
  if (loading) {
    return <Skeleton className="w-full h-64 bg-zinc-800" />;
  }

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-zinc-500 text-sm">
        No data available
      </div>
    );
  }

  return (
    <div className="w-full h-64">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#71717a", fontSize: 12 }}
            tickLine={{ stroke: "#3f3f46" }}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
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
            formatter={(value: any) => [`${(Number(value) * 100).toFixed(1)}%`, "Win Rate"]}
          />
          <Line
            type="monotone"
            dataKey="win_rate"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: "#f59e0b" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

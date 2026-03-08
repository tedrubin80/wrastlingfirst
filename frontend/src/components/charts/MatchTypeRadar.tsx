"use client";

import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface DataPoint {
  match_type: string;
  win_rate: number;
  total: number;
}

interface MatchTypeRadarProps {
  data: DataPoint[];
  loading?: boolean;
}

export default function MatchTypeRadar({
  data,
  loading = false,
}: MatchTypeRadarProps) {
  if (loading) return <Skeleton className="w-full h-72 bg-zinc-800" />;
  if (data.length === 0)
    return (
      <div className="flex items-center justify-center h-72 text-zinc-500 text-sm">
        No data available
      </div>
    );

  const chartData = data.map((d) => ({
    type: d.match_type.replace(/_/g, " "),
    "Win Rate": Math.round(d.win_rate * 100),
    matches: d.total,
  }));

  return (
    <div className="w-full h-72">
      <ResponsiveContainer>
        <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#3f3f46" />
          <PolarAngleAxis
            dataKey="type"
            tick={{ fill: "#a1a1aa", fontSize: 11 }}
          />
          <PolarRadiusAxis
            domain={[0, 100]}
            tick={{ fill: "#52525b", fontSize: 10 }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: "8px",
              color: "#fafafa",
            }}
            formatter={(value: any, name: any, entry: any) => [
              `${value}% (${entry.payload.matches} matches)`,
              name,
            ]}
          />
          <Radar
            dataKey="Win Rate"
            stroke="#f59e0b"
            fill="#f59e0b"
            fillOpacity={0.2}
            strokeWidth={2}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface DataPoint {
  date: string;
  momentum: number;
  push_score?: number;
}

interface MomentumCurveProps {
  data: DataPoint[];
  loading?: boolean;
}

export default function MomentumCurve({
  data,
  loading = false,
}: MomentumCurveProps) {
  if (loading) return <Skeleton className="w-full h-64 bg-zinc-800" />;
  if (data.length === 0)
    return (
      <div className="flex items-center justify-center h-64 text-zinc-500 text-sm">
        No data available
      </div>
    );

  return (
    <div className="w-full h-64">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis
            dataKey="date"
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
          />
          <defs>
            <linearGradient id="momentumGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="momentum"
            stroke="#f59e0b"
            strokeWidth={2}
            fill="url(#momentumGradient)"
          />
          {data[0]?.push_score !== undefined && (
            <Area
              type="monotone"
              dataKey="push_score"
              stroke="#8b5cf6"
              strokeWidth={1.5}
              fill="none"
              strokeDasharray="4 4"
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

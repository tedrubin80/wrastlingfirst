"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface HeadToHeadBarProps {
  wrestler1Name: string;
  wrestler2Name: string;
  wrestler1Wins: number;
  wrestler2Wins: number;
  draws: number;
  loading?: boolean;
}

export default function HeadToHeadBar({
  wrestler1Name,
  wrestler2Name,
  wrestler1Wins,
  wrestler2Wins,
  draws,
  loading = false,
}: HeadToHeadBarProps) {
  if (loading) return <Skeleton className="w-full h-20 bg-zinc-800" />;

  const total = wrestler1Wins + wrestler2Wins + draws;
  if (total === 0)
    return (
      <div className="flex items-center justify-center h-20 text-zinc-500 text-sm">
        No matches found
      </div>
    );

  const data = [
    {
      name: "Record",
      [wrestler1Name]: wrestler1Wins,
      Draws: draws,
      [wrestler2Name]: wrestler2Wins,
    },
  ];

  return (
    <div className="w-full h-20">
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" hide />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: "8px",
              color: "#fafafa",
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "#a1a1aa" }}
          />
          <Bar
            dataKey={wrestler1Name}
            stackId="a"
            fill="#3b82f6"
            radius={[4, 0, 0, 4]}
          />
          <Bar dataKey="Draws" stackId="a" fill="#52525b" />
          <Bar
            dataKey={wrestler2Name}
            stackId="a"
            fill="#ef4444"
            radius={[0, 4, 4, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

interface Stats {
  wrestlers: number;
  matches: number;
  events: number;
  promotions: number;
}

function AnimatedCount({
  target,
  suffix = "",
  duration = 2000,
}: {
  target: number;
  suffix?: string;
  duration?: number;
}) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (target === 0) return;
    const steps = 60;
    const increment = target / steps;
    const stepTime = duration / steps;
    let current = 0;
    const timer = setInterval(() => {
      current += increment;
      if (current >= target) {
        setCount(target);
        clearInterval(timer);
      } else {
        setCount(Math.floor(current));
      }
    }, stepTime);
    return () => clearInterval(timer);
  }, [target, duration]);

  const formatted =
    count >= 1000
      ? `${(count / 1000).toFixed(count >= 10000 ? 0 : 1)}K`
      : count.toString();

  return (
    <span>
      {formatted}
      {suffix}
    </span>
  );
}

export default function StatsTicker() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    async function fetchStats() {
      try {
        const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
        const res = await fetch(`${API}/api/metrics`);
        if (!res.ok) throw new Error();
        const text = await res.text();

        // Parse Prometheus format
        const wrestlers =
          Number(text.match(/wrestler_count (\d+)/)?.[1]) || 15000;
        const matches =
          Number(text.match(/match_count (\d+)/)?.[1]) || 200000;
        const events = Number(text.match(/event_count (\d+)/)?.[1]) || 50000;

        setStats({ wrestlers, matches, events, promotions: 6 });
      } catch {
        // Fallback estimates
        setStats({
          wrestlers: 15000,
          matches: 200000,
          events: 50000,
          promotions: 6,
        });
      }
    }

    fetchStats();
  }, []);

  const items = [
    {
      value: stats?.matches ?? 0,
      suffix: "+",
      label: "Matches",
    },
    {
      value: stats?.wrestlers ?? 0,
      suffix: "+",
      label: "Wrestlers",
    },
    {
      value: 40,
      suffix: "+",
      label: "Years of Data",
    },
    {
      value: stats?.promotions ?? 6,
      suffix: "",
      label: "Promotions",
    },
  ];

  return (
    <div className="relative">
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-amber-500/40 to-transparent" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 md:gap-8 py-8">
        {items.map((item) => (
          <div key={item.label} className="text-center">
            <div className="text-3xl md:text-4xl font-black text-white mb-1">
              <AnimatedCount target={item.value} suffix={item.suffix} />
            </div>
            <div className="text-xs uppercase tracking-widest text-zinc-500 font-medium">
              {item.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

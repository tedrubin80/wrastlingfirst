"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface SpotlightData {
  wrestler1: { id: number; name: string; win_probability: number };
  wrestler2: { id: number; name: string; win_probability: number };
  confidence: number;
  model_version: string;
  factors: { label: string; difference: number }[];
}

export default function PredictionSpotlight() {
  const [data, setData] = useState<SpotlightData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    async function fetchSpotlight() {
      try {
        const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

        // Get two random top wrestlers
        const res = await fetch(
          `${API}/api/wrestlers?limit=50&sort=matches&order=desc`
        );
        if (!res.ok) throw new Error("Failed to fetch wrestlers");
        const wrestlers = await res.json();
        const list = wrestlers.data || wrestlers;

        if (list.length < 2) throw new Error("Not enough wrestlers");

        // Pick two random from the top 50
        const shuffled = [...list].sort(() => Math.random() - 0.5);
        const w1 = shuffled[0];
        const w2 = shuffled[1];

        // Run prediction
        const predRes = await fetch(`${API}/api/predict`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            wrestler_ids: [w1.id, w2.id],
            match_type: "singles",
            event_tier: "ppv",
            title_match: false,
          }),
        });

        if (!predRes.ok) throw new Error("Prediction failed");
        const prediction = await predRes.json();
        const probs = prediction.probabilities || [];

        setData({
          wrestler1: {
            id: w1.id,
            name: w1.name,
            win_probability: probs[0]?.win_probability ?? 0.5,
          },
          wrestler2: {
            id: w2.id,
            name: w2.name,
            win_probability: probs[1]?.win_probability ?? 0.5,
          },
          confidence: probs[0]?.confidence ?? 0,
          model_version: prediction.model_version || "unknown",
          factors: prediction.factors || [],
        });
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    }

    fetchSpotlight();
  }, []);

  if (error) return null;

  return (
    <div className="relative">
      {/* Glow backdrop */}
      <div className="absolute inset-0 bg-gradient-to-b from-red-950/30 via-transparent to-transparent rounded-2xl blur-xl" />

      <div className="relative border border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm rounded-2xl p-8 md:p-10">
        <div className="flex items-center gap-2 mb-6">
          <div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
          <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
            Prediction Spotlight
          </span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-8 py-8">
            <div className="h-16 w-48 bg-zinc-800/50 rounded-lg animate-pulse" />
            <div className="text-3xl font-black text-zinc-700">VS</div>
            <div className="h-16 w-48 bg-zinc-800/50 rounded-lg animate-pulse" />
          </div>
        ) : data ? (
          <>
            {/* Matchup */}
            <div className="flex flex-col md:flex-row items-center justify-center gap-6 md:gap-10 mb-8">
              {/* Wrestler 1 */}
              <div className="flex-1 text-center md:text-right">
                <Link
                  href={`/wrestlers/${data.wrestler1.id}`}
                  className="group"
                >
                  <h3 className="text-2xl md:text-3xl font-black uppercase tracking-tight text-white group-hover:text-amber-400 transition-colors">
                    {data.wrestler1.name}
                  </h3>
                </Link>
              </div>

              {/* VS Divider */}
              <div className="relative flex-shrink-0">
                <div className="absolute inset-0 bg-red-600/20 rounded-full blur-xl" />
                <div className="relative text-3xl md:text-4xl font-black text-red-500 px-4">
                  VS
                </div>
              </div>

              {/* Wrestler 2 */}
              <div className="flex-1 text-center md:text-left">
                <Link
                  href={`/wrestlers/${data.wrestler2.id}`}
                  className="group"
                >
                  <h3 className="text-2xl md:text-3xl font-black uppercase tracking-tight text-white group-hover:text-amber-400 transition-colors">
                    {data.wrestler2.name}
                  </h3>
                </Link>
              </div>
            </div>

            {/* Probability Bar */}
            <div className="max-w-xl mx-auto mb-6">
              <div className="flex justify-between text-sm font-bold mb-2">
                <span className="text-amber-400">
                  {(data.wrestler1.win_probability * 100).toFixed(1)}%
                </span>
                <span className="text-zinc-500 text-xs uppercase tracking-wider">
                  Win Probability
                </span>
                <span className="text-red-400">
                  {(data.wrestler2.win_probability * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-3 rounded-full bg-zinc-800 overflow-hidden flex">
                <div
                  className="bg-gradient-to-r from-amber-500 to-amber-400 rounded-l-full transition-all duration-1000"
                  style={{
                    width: `${data.wrestler1.win_probability * 100}%`,
                  }}
                />
                <div
                  className="bg-gradient-to-r from-red-500 to-red-600 rounded-r-full transition-all duration-1000"
                  style={{
                    width: `${data.wrestler2.win_probability * 100}%`,
                  }}
                />
              </div>
            </div>

            {/* Top Factors */}
            {data.factors.length > 0 && (
              <div className="max-w-xl mx-auto mb-6">
                <p className="text-xs text-zinc-600 uppercase tracking-wider mb-2">
                  Key Factors
                </p>
                <div className="flex flex-wrap gap-2">
                  {data.factors.slice(0, 3).map((f, i) => (
                    <span
                      key={i}
                      className="text-xs px-3 py-1 rounded-full bg-zinc-800/80 text-zinc-400 border border-zinc-700/50"
                    >
                      {f.label}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* CTA */}
            <div className="text-center">
              <Link
                href="/predict"
                className="inline-flex items-center gap-2 text-sm font-semibold text-amber-400 hover:text-amber-300 transition-colors"
              >
                Run your own prediction
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 7l5 5m0 0l-5 5m5-5H6"
                  />
                </svg>
              </Link>
            </div>

            {/* Model badge */}
            <div className="text-center mt-4">
              <span className="text-[10px] text-zinc-600 uppercase tracking-wider">
                {data.model_version} &middot; Confidence{" "}
                {(data.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

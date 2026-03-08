"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import WrestlerSearch from "@/components/search/WrestlerSearch";
import { getHeadToHead } from "@/lib/api";
import PageContainer from "@/components/PageContainer";

interface Wrestler {
  id: number;
  ring_name: string;
  promotion: string;
  status: string;
}

export default function HeadToHeadPage() {
  const [wrestler1, setWrestler1] = useState<Wrestler | null>(null);
  const [wrestler2, setWrestler2] = useState<Wrestler | null>(null);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function compare() {
    if (!wrestler1 || !wrestler2) return;
    setLoading(true);
    setError(null);

    try {
      const res = await getHeadToHead(wrestler1.id, wrestler2.id);
      setResult(res.data);
    } catch (e: any) {
      setError(e.message || "Failed to load head-to-head data");
    } finally {
      setLoading(false);
    }
  }

  const excludeIds = [wrestler1?.id, wrestler2?.id].filter(
    Boolean
  ) as number[];

  return (
    <PageContainer>
      <h1 className="text-3xl font-bold mb-2">Head-to-Head</h1>
      <p className="text-zinc-500 mb-8">
        Compare two wrestlers — series record and match history.
      </p>

      {/* Wrestler selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div>
          <label className="text-sm text-zinc-400 mb-2 block">Wrestler 1</label>
          {wrestler1 ? (
            <div className="flex items-center justify-between p-3 rounded-lg border border-zinc-700 bg-zinc-900">
              <span className="font-semibold">{wrestler1.ring_name}</span>
              <button
                onClick={() => {
                  setWrestler1(null);
                  setResult(null);
                }}
                className="text-zinc-500 hover:text-red-400 text-sm"
              >
                Change
              </button>
            </div>
          ) : (
            <WrestlerSearch
              onSelect={(w) => {
                setWrestler1(w);
                setResult(null);
              }}
              excludeIds={excludeIds}
              placeholder="Search wrestler 1..."
            />
          )}
        </div>

        <div>
          <label className="text-sm text-zinc-400 mb-2 block">Wrestler 2</label>
          {wrestler2 ? (
            <div className="flex items-center justify-between p-3 rounded-lg border border-zinc-700 bg-zinc-900">
              <span className="font-semibold">{wrestler2.ring_name}</span>
              <button
                onClick={() => {
                  setWrestler2(null);
                  setResult(null);
                }}
                className="text-zinc-500 hover:text-red-400 text-sm"
              >
                Change
              </button>
            </div>
          ) : (
            <WrestlerSearch
              onSelect={(w) => {
                setWrestler2(w);
                setResult(null);
              }}
              excludeIds={excludeIds}
              placeholder="Search wrestler 2..."
            />
          )}
        </div>
      </div>

      <Button
        onClick={compare}
        disabled={!wrestler1 || !wrestler2 || loading}
        className="w-full bg-amber-500 text-black font-semibold hover:bg-amber-400 disabled:opacity-50"
      >
        {loading ? "Loading..." : "Compare"}
      </Button>

      {error && (
        <p className="text-red-400 text-sm mt-4 text-center">{error}</p>
      )}

      {/* Results */}
      {result && (
        <div className="mt-8">
          {/* Summary */}
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div className="text-center p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
              <p className="text-3xl font-bold text-emerald-400">
                {result.summary.wrestler1_wins}
              </p>
              <p className="text-sm text-zinc-400">
                {result.wrestler1?.ring_name}
              </p>
            </div>
            <div className="text-center p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
              <p className="text-3xl font-bold text-zinc-400">
                {result.summary.draws}
              </p>
              <p className="text-sm text-zinc-500">Draws</p>
            </div>
            <div className="text-center p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
              <p className="text-3xl font-bold text-emerald-400">
                {result.summary.wrestler2_wins}
              </p>
              <p className="text-sm text-zinc-400">
                {result.wrestler2?.ring_name}
              </p>
            </div>
          </div>

          {/* Win percentage bar */}
          {result.summary.total_matches > 0 && (
            <div className="mb-8">
              <div className="flex rounded-full h-3 overflow-hidden">
                <div
                  className="bg-blue-500"
                  style={{
                    width: `${(result.summary.wrestler1_wins / result.summary.total_matches) * 100}%`,
                  }}
                />
                <div
                  className="bg-zinc-600"
                  style={{
                    width: `${(result.summary.draws / result.summary.total_matches) * 100}%`,
                  }}
                />
                <div
                  className="bg-red-500"
                  style={{
                    width: `${(result.summary.wrestler2_wins / result.summary.total_matches) * 100}%`,
                  }}
                />
              </div>
              <p className="text-xs text-zinc-500 text-center mt-2">
                {result.summary.total_matches} total matches
              </p>
            </div>
          )}

          {/* Match History */}
          <h2 className="text-xl font-semibold mb-4">Match History</h2>
          <div className="space-y-2">
            {result.matches?.map((m: any) => (
              <Link
                key={m.id}
                href={`/matches/${m.id}`}
                className="flex items-center justify-between p-3 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:border-zinc-600 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className="border-zinc-700 text-zinc-400 text-xs"
                  >
                    {m.match_type.replace(/_/g, " ")}
                  </Badge>
                  <span className="text-sm">{m.event_name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-semibold ${
                      m.wrestler1_result === "win"
                        ? "text-blue-400"
                        : m.wrestler2_result === "win"
                          ? "text-red-400"
                          : "text-zinc-400"
                    }`}
                  >
                    {m.wrestler1_result === "win"
                      ? result.wrestler1?.ring_name
                      : m.wrestler2_result === "win"
                        ? result.wrestler2?.ring_name
                        : "Draw"}
                  </span>
                  <span className="text-xs text-zinc-500">{m.event_date}</span>
                </div>
              </Link>
            ))}
          </div>

          {result.matches?.length === 0 && (
            <p className="text-zinc-500 text-center py-8">
              No matches found between these wrestlers.
            </p>
          )}
        </div>
      )}
    </PageContainer>
  );
}

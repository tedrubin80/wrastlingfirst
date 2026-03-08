"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import WrestlerSearch from "@/components/search/WrestlerSearch";
import { predict } from "@/lib/api";

interface Wrestler {
  id: number;
  ring_name: string;
  promotion: string;
  status: string;
}

interface Prediction {
  wrestler_id: number;
  win_probability: number;
  confidence: number;
}

export default function PredictPage() {
  const [selected, setSelected] = useState<Wrestler[]>([]);
  const [matchType, setMatchType] = useState("singles");
  const [eventTier, setEventTier] = useState("weekly_tv");
  const [titleMatch, setTitleMatch] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addWrestler(w: Wrestler) {
    if (selected.length >= 8) return;
    setSelected((prev) => [...prev, w]);
    setResult(null);
  }

  function removeWrestler(id: number) {
    setSelected((prev) => prev.filter((w) => w.id !== id));
    setResult(null);
  }

  async function runPrediction() {
    if (selected.length < 2) return;
    setLoading(true);
    setError(null);

    try {
      const res = await predict({
        wrestler_ids: selected.map((w) => w.id),
        match_type: matchType,
        event_tier: eventTier,
        title_match: titleMatch,
      });
      setResult(res.data);
    } catch (e: any) {
      setError(e.message || "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Match Prediction</h1>
      <p className="text-zinc-500 mb-8">
        Select 2-8 wrestlers and set the match context to get win probabilities.
      </p>

      {/* Wrestler selector */}
      <div className="mb-6">
        <label className="text-sm text-zinc-400 mb-2 block">
          Add Wrestlers ({selected.length}/8)
        </label>
        <WrestlerSearch
          onSelect={addWrestler}
          excludeIds={selected.map((w) => w.id)}
          placeholder="Search for a wrestler to add..."
        />

        {selected.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {selected.map((w) => (
              <Badge
                key={w.id}
                variant="outline"
                className="border-zinc-600 text-zinc-300 gap-1 py-1.5"
              >
                {w.ring_name}
                <button
                  onClick={() => removeWrestler(w.id)}
                  className="ml-1 text-zinc-500 hover:text-red-400"
                >
                  x
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Context controls */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div>
          <label className="text-sm text-zinc-400 mb-1 block">Match Type</label>
          <select
            value={matchType}
            onChange={(e) => setMatchType(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm text-white"
          >
            <option value="singles">Singles</option>
            <option value="tag_team">Tag Team</option>
            <option value="triple_threat">Triple Threat</option>
            <option value="fatal_four_way">Fatal Four Way</option>
            <option value="ladder">Ladder</option>
            <option value="cage">Cage</option>
            <option value="hell_in_a_cell">Hell in a Cell</option>
            <option value="royal_rumble">Royal Rumble</option>
          </select>
        </div>

        <div>
          <label className="text-sm text-zinc-400 mb-1 block">Event Tier</label>
          <select
            value={eventTier}
            onChange={(e) => setEventTier(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm text-white"
          >
            <option value="weekly_tv">Weekly TV</option>
            <option value="ppv">PPV</option>
            <option value="special">Special</option>
          </select>
        </div>

        <div>
          <label className="text-sm text-zinc-400 mb-1 block">
            Title Match
          </label>
          <button
            onClick={() => setTitleMatch(!titleMatch)}
            className={`w-full px-3 py-2 text-sm rounded-md border transition-colors ${
              titleMatch
                ? "bg-amber-500/10 border-amber-500 text-amber-400"
                : "bg-zinc-900 border-zinc-700 text-zinc-400"
            }`}
          >
            {titleMatch ? "Yes" : "No"}
          </button>
        </div>
      </div>

      {/* Predict button */}
      <Button
        onClick={runPrediction}
        disabled={selected.length < 2 || loading}
        className="w-full bg-amber-500 text-black font-semibold hover:bg-amber-400 disabled:opacity-50"
      >
        {loading ? "Predicting..." : "Predict Winner"}
      </Button>

      {error && (
        <p className="text-red-400 text-sm mt-4 text-center">{error}</p>
      )}

      {/* Results */}
      {result && (
        <div className="mt-8">
          <h2 className="text-xl font-semibold mb-4">Prediction Results</h2>

          {result.message && (
            <p className="text-zinc-500 text-sm mb-4 italic">{result.message}</p>
          )}

          <div className="space-y-3">
            {result.probabilities
              ?.sort(
                (a: Prediction, b: Prediction) =>
                  b.win_probability - a.win_probability
              )
              .map((p: Prediction) => {
                const wrestler = selected.find((w) => w.id === p.wrestler_id);
                const pct = (p.win_probability * 100).toFixed(1);
                return (
                  <div
                    key={p.wrestler_id}
                    className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold">
                        {wrestler?.ring_name || `Wrestler #${p.wrestler_id}`}
                      </span>
                      <span className="text-amber-400 font-bold">{pct}%</span>
                    </div>
                    <div className="w-full bg-zinc-800 rounded-full h-2">
                      <div
                        className="bg-amber-500 h-2 rounded-full transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>

          {/* Contributing Factors */}
          {result.factors && result.factors.length > 0 && (
            <div className="mt-6">
              <h3 className="text-lg font-semibold mb-3">Key Factors</h3>
              <div className="space-y-2">
                {result.factors.map((f: any, i: number) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 rounded-lg border border-zinc-800 bg-zinc-900/50"
                  >
                    <span className="text-sm text-zinc-300">{f.label}</span>
                    <span
                      className={`text-xs font-mono px-2 py-1 rounded ${
                        f.difference > 0
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "bg-red-500/10 text-red-400"
                      }`}
                    >
                      {f.difference > 0 ? "+" : ""}
                      {f.difference.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-xs text-zinc-600 mt-4 text-center">
            Model: {result.model_version}
          </p>
        </div>
      )}
    </div>
  );
}

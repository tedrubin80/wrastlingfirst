"use client";

import { useState, useEffect, useRef } from "react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { getWrestlers } from "@/lib/api";

interface Wrestler {
  id: number;
  ring_name: string;
  promotion: string;
  status: string;
}

interface WrestlerSearchProps {
  onSelect: (wrestler: Wrestler) => void;
  placeholder?: string;
  excludeIds?: number[];
}

export default function WrestlerSearch({
  onSelect,
  placeholder = "Search wrestlers...",
  excludeIds = [],
}: WrestlerSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Wrestler[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout>();

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await getWrestlers({ q: query, limit: "10" });
        const filtered = res.data.filter(
          (w: Wrestler) => !excludeIds.includes(w.id)
        );
        setResults(filtered);
        setIsOpen(filtered.length > 0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(debounceRef.current);
  }, [query, excludeIds]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleSelect(wrestler: Wrestler) {
    onSelect(wrestler);
    setQuery("");
    setResults([]);
    setIsOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <Input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        className="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500"
      />
      {loading && (
        <div className="absolute right-3 top-2.5 text-zinc-500 text-sm">
          ...
        </div>
      )}

      {isOpen && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-zinc-900 border border-zinc-700 rounded-md shadow-lg max-h-60 overflow-y-auto">
          {results.map((wrestler) => (
            <button
              key={wrestler.id}
              onClick={() => handleSelect(wrestler)}
              className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-zinc-800 transition-colors"
            >
              <span className="text-sm text-white">{wrestler.ring_name}</span>
              <Badge
                variant="outline"
                className="text-xs border-zinc-600 text-zinc-400"
              >
                {wrestler.promotion}
              </Badge>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

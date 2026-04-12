"use client";

import { useState, useEffect, useRef, useMemo, useId } from "react";
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
  const [popularResults, setPopularResults] = useState<Wrestler[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<NodeJS.Timeout>();
  const listboxId = useId();

  // Stable primitive dep so effects don't re-run on parent array reallocation
  const excludeKey = excludeIds.join(",");

  // Load popular wrestlers once for "browse on focus"
  useEffect(() => {
    async function loadPopular() {
      try {
        const res = await getWrestlers({ limit: "20", sort: "matches", order: "desc" });
        setPopularResults(res.data || []);
      } catch {
        // Non-critical
      }
    }
    loadPopular();
  }, []);

  useEffect(() => {
    if (query.length < 1) {
      setResults([]);
      setHighlightIndex(-1);
      return;
    }

    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await getWrestlers({ q: query, limit: "10" });
        const excluded = new Set(excludeKey ? excludeKey.split(",").map(Number) : []);
        const filtered = (res.data || []).filter((w: Wrestler) => !excluded.has(w.id));
        setResults(filtered);
        setHighlightIndex(-1);
        setIsOpen(filtered.length > 0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(debounceRef.current);
  }, [query, excludeKey]);

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
    setHighlightIndex(-1);
  }

  function handleFocus() {
    if (query.length >= 1 && results.length > 0) {
      setIsOpen(true);
    } else if (query.length === 0 && popularResults.length > 0) {
      setIsOpen(true);
    }
  }

  const displayList = useMemo(() => {
    if (query.length >= 1) return results;
    const excluded = new Set(excludeKey ? excludeKey.split(",").map(Number) : []);
    return popularResults.filter((w) => !excluded.has(w.id));
  }, [query, results, popularResults, excludeKey]);

  const activeOptionId =
    highlightIndex >= 0 ? `${listboxId}-opt-${highlightIndex}` : undefined;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!isOpen || displayList.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((prev) =>
        prev < displayList.length - 1 ? prev + 1 : 0
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((prev) =>
        prev > 0 ? prev - 1 : displayList.length - 1
      );
    } else if (e.key === "Enter" && highlightIndex >= 0) {
      e.preventDefault();
      handleSelect(displayList[highlightIndex]);
    } else if (e.key === "Escape") {
      setIsOpen(false);
      inputRef.current?.blur();
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (e.target.value.length === 0) setIsOpen(true);
          }}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 pr-9"
          role="combobox"
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          aria-controls={listboxId}
          aria-activedescendant={activeOptionId}
          autoComplete="off"
        />
        {/* Dropdown chevron */}
        <button
          type="button"
          tabIndex={-1}
          onClick={() => {
            setIsOpen(!isOpen);
            inputRef.current?.focus();
          }}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {loading ? (
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg
              className={`w-4 h-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </button>
      </div>

      {isOpen && displayList.length > 0 && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-50 w-full mt-1 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl max-h-64 overflow-y-auto"
        >
          {query.length === 0 && (
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-zinc-600 font-semibold border-b border-zinc-800">
              Popular wrestlers
            </div>
          )}
          {displayList.map((wrestler, i) => (
            <button
              key={wrestler.id}
              id={`${listboxId}-opt-${i}`}
              onClick={() => handleSelect(wrestler)}
              onMouseEnter={() => setHighlightIndex(i)}
              className={`w-full flex items-center justify-between px-3 py-2.5 text-left transition-colors ${
                i === highlightIndex
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-300 hover:bg-zinc-800/50"
              }`}
              role="option"
              aria-selected={i === highlightIndex}
            >
              <span className="text-sm font-medium">{wrestler.ring_name}</span>
              <Badge
                variant="outline"
                className="text-[10px] border-zinc-700 text-zinc-500"
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

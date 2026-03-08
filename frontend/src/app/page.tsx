import Link from "next/link";
import PredictionSpotlight from "@/components/PredictionSpotlight";
import StatsTicker from "@/components/StatsTicker";

export default function Home() {
  return (
    <div className="relative">
      {/* ── Hero ────────────────────────────────────────── */}
      <section className="relative min-h-[85vh] flex items-center justify-center overflow-hidden">
        {/* Arena spotlight gradient */}
        <div className="absolute inset-0 bg-zinc-950" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-gradient-radial from-red-950/40 via-amber-950/10 to-transparent rounded-full blur-3xl" />
        <div className="absolute top-20 left-1/4 w-[400px] h-[400px] bg-gradient-radial from-red-900/15 to-transparent rounded-full blur-3xl" />
        <div className="absolute top-40 right-1/4 w-[300px] h-[300px] bg-gradient-radial from-amber-900/10 to-transparent rounded-full blur-3xl" />

        {/* Ring ropes accent lines */}
        <div className="absolute top-1/3 inset-x-0 h-px bg-gradient-to-r from-transparent via-red-800/30 to-transparent" />
        <div className="absolute top-[38%] inset-x-0 h-px bg-gradient-to-r from-transparent via-red-900/20 to-transparent" />
        <div className="absolute top-[43%] inset-x-0 h-px bg-gradient-to-r from-transparent via-red-950/15 to-transparent" />

        {/* Content */}
        <div className="relative z-10 text-center px-4 max-w-4xl mx-auto">
          <h1 className="text-6xl sm:text-7xl md:text-8xl font-black tracking-tighter mb-6">
            <span className="bg-gradient-to-b from-white via-white to-zinc-400 bg-clip-text text-transparent">
              RINGSIDE
            </span>
            <span className="text-amber-400">.</span>
          </h1>

          <p className="text-xl md:text-2xl text-zinc-300 font-light mb-3 tracking-wide">
            40+ years of professional wrestling data
          </p>
          <p className="text-base text-zinc-500 mb-10 max-w-xl mx-auto leading-relaxed">
            Match history, career analytics, and ML-powered outcome predictions
            across WWE, AEW, NXT, WCW, ECW, and TNA.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/predict"
              className="group relative px-8 py-4 font-bold text-black rounded-xl overflow-hidden transition-all hover:scale-105"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-amber-400 to-amber-500 group-hover:from-amber-300 group-hover:to-amber-400 transition-colors" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/10 to-transparent" />
              <span className="relative">Predict a Match</span>
            </Link>
            <Link
              href="/wrestlers"
              className="px-8 py-4 font-bold text-white rounded-xl border border-zinc-700/50 bg-zinc-900/50 hover:bg-zinc-800/50 hover:border-zinc-600 backdrop-blur-sm transition-all hover:scale-105"
            >
              Browse Wrestlers
            </Link>
          </div>
        </div>

        {/* Bottom fade */}
        <div className="absolute bottom-0 inset-x-0 h-32 bg-gradient-to-t from-zinc-950 to-transparent" />
      </section>

      {/* ── Stats Ticker ───────────────────────────────── */}
      <section className="relative bg-zinc-950 px-4">
        <div className="max-w-5xl mx-auto">
          <StatsTicker />
        </div>
      </section>

      {/* ── Prediction Spotlight ───────────────────────── */}
      <section className="relative bg-zinc-950 px-4 py-16 md:py-24">
        <div className="max-w-4xl mx-auto">
          <PredictionSpotlight />
        </div>
      </section>

      {/* ── Feature Cards ──────────────────────────────── */}
      <section className="relative bg-zinc-950 px-4 pb-20">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <FeatureCard
              title="Match Predictions"
              description="Select wrestlers, set the context, and get win probabilities powered by booking pattern analysis."
              href="/predict"
              icon={
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                </svg>
              }
              gradient="from-amber-500/10 to-transparent"
            />
            <FeatureCard
              title="Historical Search"
              description="Browse 200K+ matches across 40+ years. Filter by promotion, match type, wrestler, and era."
              href="/events"
              icon={
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                </svg>
              }
              gradient="from-red-500/10 to-transparent"
            />
            <FeatureCard
              title="Head-to-Head"
              description="Compare any two wrestlers — series record, match history, and trend analysis."
              href="/head-to-head"
              icon={
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                </svg>
              }
              gradient="from-zinc-500/10 to-transparent"
            />
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────── */}
      <footer className="relative bg-zinc-950 border-t border-zinc-800/50">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-zinc-700/50 to-transparent" />
        <div className="max-w-6xl mx-auto px-4 py-12">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div>
              <span className="text-lg font-black tracking-tight text-white">
                RINGSIDE<span className="text-amber-400">.</span>
              </span>
              <p className="text-xs text-zinc-600 mt-1">
                Wrestling analytics powered by data
              </p>
            </div>

            <div className="flex items-center gap-6 text-sm text-zinc-500">
              <Link href="/wrestlers" className="hover:text-zinc-300 transition-colors">Wrestlers</Link>
              <Link href="/events" className="hover:text-zinc-300 transition-colors">Events</Link>
              <Link href="/predict" className="hover:text-zinc-300 transition-colors">Predict</Link>
              <Link href="/head-to-head" className="hover:text-zinc-300 transition-colors">Head-to-Head</Link>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-[10px] px-2 py-1 rounded bg-zinc-800/50 text-zinc-500 border border-zinc-800 font-mono">
                XGBoost
              </span>
              <span className="text-[10px] px-2 py-1 rounded bg-zinc-800/50 text-zinc-500 border border-zinc-800 font-mono">
                525K matches
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({
  title,
  description,
  href,
  icon,
  gradient,
}: {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  gradient: string;
}) {
  return (
    <Link
      href={href}
      className="group relative p-8 rounded-2xl border border-zinc-800/50 bg-zinc-900/30 hover:border-zinc-700/50 transition-all duration-300 overflow-hidden"
    >
      {/* Hover gradient */}
      <div
        className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300`}
      />

      {/* Hover glow */}
      <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-amber-500/0 to-transparent group-hover:from-amber-500/5 transition-all duration-300" />

      <div className="relative">
        <div className="text-zinc-600 group-hover:text-amber-400 transition-colors duration-300 mb-4">
          {icon}
        </div>
        <h3 className="text-lg font-bold mb-2 text-white group-hover:text-amber-400 transition-colors duration-300">
          {title}
        </h3>
        <p className="text-sm text-zinc-500 leading-relaxed">{description}</p>
      </div>
    </Link>
  );
}

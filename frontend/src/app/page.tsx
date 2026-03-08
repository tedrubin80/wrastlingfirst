import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-col items-center">
      {/* Hero */}
      <section className="text-center py-20 max-w-3xl">
        <h1 className="text-5xl font-bold tracking-tight mb-4">
          Ringside<span className="text-amber-400">.</span>
        </h1>
        <p className="text-xl text-zinc-400 mb-2">
          40+ years of professional wrestling data
        </p>
        <p className="text-zinc-500 mb-8">
          Match history, career analytics, and ML-powered outcome predictions
          across WWE, AEW, NXT, WCW, ECW, and TNA.
        </p>

        <div className="flex gap-4 justify-center">
          <Link
            href="/predict"
            className="px-6 py-3 bg-amber-500 text-black font-semibold rounded-lg hover:bg-amber-400 transition-colors"
          >
            Predict a Match
          </Link>
          <Link
            href="/wrestlers"
            className="px-6 py-3 bg-zinc-800 text-white font-semibold rounded-lg hover:bg-zinc-700 transition-colors border border-zinc-700"
          >
            Browse Wrestlers
          </Link>
        </div>
      </section>

      {/* Feature Cards */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mt-8">
        <FeatureCard
          title="Match Predictions"
          description="Select wrestlers, set the context, and get win probabilities powered by booking pattern analysis."
          href="/predict"
        />
        <FeatureCard
          title="Historical Search"
          description="Browse 200K+ matches across 40+ years. Filter by promotion, match type, wrestler, and era."
          href="/events"
        />
        <FeatureCard
          title="Head-to-Head"
          description="Compare any two wrestlers — series record, match history, and trend analysis."
          href="/head-to-head"
        />
      </section>
    </div>
  );
}

function FeatureCard({
  title,
  description,
  href,
}: {
  title: string;
  description: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="p-6 rounded-xl border border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-900 transition-all group"
    >
      <h3 className="text-lg font-semibold mb-2 group-hover:text-amber-400 transition-colors">
        {title}
      </h3>
      <p className="text-sm text-zinc-400">{description}</p>
    </Link>
  );
}

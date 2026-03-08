import Link from "next/link";

const navLinks = [
  { href: "/wrestlers", label: "Wrestlers" },
  { href: "/events", label: "Events" },
  { href: "/predict", label: "Predict" },
  { href: "/head-to-head", label: "Head-to-Head" },
];

export default function Navbar() {
  return (
    <nav className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <Link
            href="/"
            className="text-xl font-bold tracking-tight text-white hover:text-amber-400 transition-colors"
          >
            Ringside<span className="text-amber-400">.</span>
          </Link>

          <div className="flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="px-3 py-2 text-sm font-medium text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-md transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </nav>
  );
}

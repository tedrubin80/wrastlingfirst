import { MetadataRoute } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: SITE_URL, lastModified: new Date(), changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/wrestlers`, lastModified: new Date(), changeFrequency: "daily", priority: 0.9 },
    { url: `${SITE_URL}/events`, lastModified: new Date(), changeFrequency: "daily", priority: 0.8 },
    { url: `${SITE_URL}/predict`, lastModified: new Date(), changeFrequency: "weekly", priority: 0.7 },
    { url: `${SITE_URL}/head-to-head`, lastModified: new Date(), changeFrequency: "weekly", priority: 0.7 },
  ];

  // Fetch wrestler IDs for dynamic routes
  try {
    const res = await fetch(`${API_BASE}/api/wrestlers?limit=1000`, {
      next: { revalidate: 86400 },
    });
    if (res.ok) {
      const json = await res.json();
      const wrestlerRoutes: MetadataRoute.Sitemap = json.data.map(
        (w: { id: number }) => ({
          url: `${SITE_URL}/wrestlers/${w.id}`,
          lastModified: new Date(),
          changeFrequency: "weekly" as const,
          priority: 0.6,
        })
      );
      return [...staticRoutes, ...wrestlerRoutes];
    }
  } catch {
    // API unavailable — return static routes only
  }

  return staticRoutes;
}

type CacheEntry<T> = {
  value: T;
  cachedAt: number;
};

// This cache deliberately lives only in the current browser tab. It makes a
// detail -> list navigation feel instant without persisting another user's
// results to disk or treating cached data as authoritative.
const routeDataCache = new Map<string, CacheEntry<unknown>>();

export const ROUTE_DATA_CACHE_TTL_MS = 2 * 60 * 1000;

export function readRouteData<T>(key: string, maxAgeMs = ROUTE_DATA_CACHE_TTL_MS): T | null {
  const entry = routeDataCache.get(key) as CacheEntry<T> | undefined;
  if (!entry) return null;
  if (Date.now() - entry.cachedAt > maxAgeMs) {
    routeDataCache.delete(key);
    return null;
  }
  return entry.value;
}

export function writeRouteData<T>(key: string, value: T): void {
  routeDataCache.set(key, { value, cachedAt: Date.now() });
}

export function clearRouteDataCache(): void {
  routeDataCache.clear();
}

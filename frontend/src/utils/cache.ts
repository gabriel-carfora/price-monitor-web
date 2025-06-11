// frontend/src/utils/cache.ts

interface CacheItem<T> {
  data: T;
  timestamp: number;
  expiresAt: number;
}

class CacheManager {
  private cache: Map<string, CacheItem<any>> = new Map();
  private defaultTTL = 5 * 60 * 1000; // 5 minutes default

  set<T>(key: string, data: T, ttlMs?: number): void {
    const now = Date.now();
    const ttl = ttlMs || this.defaultTTL;
    
    this.cache.set(key, {
      data,
      timestamp: now,
      expiresAt: now + ttl
    });
  }

  get<T>(key: string): T | null {
    const item = this.cache.get(key);
    
    if (!item) {
      return null;
    }

    // Check if expired
    if (Date.now() > item.expiresAt) {
      this.cache.delete(key);
      return null;
    }

    return item.data as T;
  }

  has(key: string): boolean {
    const item = this.cache.get(key);
    if (!item) return false;
    
    if (Date.now() > item.expiresAt) {
      this.cache.delete(key);
      return false;
    }
    
    return true;
  }

  clear(): void {
    this.cache.clear();
  }

  clearExpired(): void {
    const now = Date.now();
    for (const [key, item] of this.cache.entries()) {
      if (now > item.expiresAt) {
        this.cache.delete(key);
      }
    }
  }

  // Get age of cached item in milliseconds
  getAge(key: string): number | null {
    const item = this.cache.get(key);
    if (!item) return null;
    return Date.now() - item.timestamp;
  }
}

// Export a singleton instance
export const cache = new CacheManager();

// Cache keys generator
export const cacheKeys = {
  productInfo: (urls: string[]): string => `product-info:${urls.sort().join(',')}`,
  productDetails: (url: string): string => `product-details:${url}`,
  watchlist: (username: string): string => `watchlist:${username}`,
  userSettings: (username: string): string => `user-settings:${username}`
};
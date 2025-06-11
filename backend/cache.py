# backend/cache.py
import json
import os
import time
from typing import Optional, Any
from hashlib import md5

CACHE_DIR = "cache"
DEFAULT_TTL = 300  # 5 minutes

class CacheManager:
    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> str:
        """Generate a safe filename from cache key"""
        safe_key = md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if it exists and hasn't expired"""
        cache_path = self._get_cache_path(key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            # Check if expired
            if time.time() > cache_data['expires_at']:
                os.remove(cache_path)
                return None
            
            return cache_data['data']
        except Exception:
            return None
    
    def set(self, key: str, data: Any, ttl: int = DEFAULT_TTL):
        """Cache data with TTL in seconds"""
        cache_path = self._get_cache_path(key)
        
        cache_data = {
            'data': data,
            'timestamp': time.time(),
            'expires_at': time.time() + ttl,
            'key': key
        }
        
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f)
    
    def delete(self, key: str):
        """Delete cached item"""
        cache_path = self._get_cache_path(key)
        if os.path.exists(cache_path):
            os.remove(cache_path)
    
    def clear_expired(self):
        """Clear all expired cache entries"""
        current_time = time.time()
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.cache_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        cache_data = json.load(f)
                    
                    if current_time > cache_data.get('expires_at', 0):
                        os.remove(filepath)
                except Exception:
                    # Remove corrupted cache files
                    os.remove(filepath)

# Global cache instance
cache = CacheManager()
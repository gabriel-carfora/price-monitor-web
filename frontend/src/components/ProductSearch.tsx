// frontend/src/components/ProductSearch.tsx
import { useState } from 'react';
import { Search, Plus, Loader2, ExternalLink } from 'lucide-react';
import API from '../api';
import { useEffect } from 'react';

interface SearchResult {
  title: string;
  url: string;
  offers_count: string;
  slug: string;
}

interface SearchResponse {
  query: string;
  results: SearchResult[];
  total_found: number;
  timestamp: string;
}

interface ProductSearchProps {
  onAddProduct: (url: string) => void;
  isAddingProduct?: boolean;
}

export default function ProductSearch({ onAddProduct, isAddingProduct = false }: ProductSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imageMap, setImageMap] = useState<Record<string, string>>({});
  const [loadingImages, setLoadingImages] = useState<Record<string, boolean>>({});
  const [watchlist, setWatchlist] = useState<string[]>([]);

  useEffect(() => {
  const fetchWatchlist = async () => {
    const username = localStorage.getItem('username');
    if (!username) return;

    try {
      const res = await API.get(`/watchlist/${username}`);
      setWatchlist(res.data);
    } catch (err) {
      console.error("Failed to fetch watchlist", err);
    }
  };

  fetchWatchlist();
}, []);

const fetchThumbnail = async (slug: string) => {
  if (imageMap[slug]) return;

  setLoadingImages((prev) => ({ ...prev, [slug]: true }));

  try {
    const res = await API.post('/product-image', {
      slug,
      size: 'thumb'
    });

    const imageUrl = res.data.image_url;
    if (imageUrl) {
      setImageMap(prev => ({ ...prev, [slug]: imageUrl }));
    }
  } catch (err) {
    console.warn(`No image for ${slug}`);
  } finally {
    setLoadingImages((prev) => ({ ...prev, [slug]: false }));
  }
};
  const handleSearch = async () => {
    if (!query.trim() || query.length < 2) {
      setError('Search query must be at least 2 characters');
      return;
    }

    try {
      setSearching(true);
      setError(null);
      setHasSearched(true);

      console.log('Searching for:', query);

      const response = await API.post('/search', {
        query: query.trim(),
        limit: 20
      });

      const data: SearchResponse = response.data;
      setResults(data.results);
      data.results.forEach(product => {
      fetchThumbnail(product.slug);
      });
      console.log(`Found ${data.total_found} results for "${data.query}"`);

    } catch (err: any) {
      console.error('Search error:', err);
      setError(err.response?.data?.error || 'Search failed');
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

const handleAddProduct = async (url: string) => {
  await onAddProduct(url);
  setWatchlist(prev => [...prev, url]);
};

  const extractProductName = (title: string, offersText: string): string => {
    // Clean up the title if it's just a slug
    if (title.includes('-') && title === title.toLowerCase()) {
      return title.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    return title;
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-4 mb-4">
      <h2 className="font-semibold mb-3 flex items-center">
        <Search className="w-5 h-5 mr-2" />
        Search Products
      </h2>

      {/* Search Input */}
      <div className="flex space-x-2 mb-4">
        <div className="flex-1 relative">
          <input
            type="text"
            placeholder="Search for products..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            className="border border-gray-300 p-2 w-full rounded pr-10"
            disabled={searching}
          />
          {searching && (
            <div className="absolute right-2 top-1/2 transform -translate-y-1/2">
              
            </div>
          )}
        </div>
        <button
          onClick={handleSearch}
          disabled={searching || !query.trim()}
          className={`px-4 py-2 rounded text-white flex items-center space-x-2 ${
            searching || !query.trim() || query.length < 1
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          <Search className="w-4 h-4" />
          <span>{searching ? 'Searching...' : 'Search'}</span>
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {/* Search Results */}
      {hasSearched && (
        <div>
          {searching ? (
            <div className="text-center py-8">
              <Loader2 className="w-8 h-8 text-gray-500 animate-spin mx-auto mb-2" />
              <p className="text-gray-500">Searching for products...</p>
            </div>
          ) : results.length > 0 ? (
            <div>
              <div className="text-sm text-gray-600 mb-3">
                Found {results.length} products for "{query}"
              </div>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {results.map((product, index) => {
  const isInWatchlist = watchlist.includes(product.url); // 👈 You MUST include this line

  return (
    <div
      key={`${product.slug}-${index}`}
      className="border border-gray-200 rounded-lg p-3 hover:bg-gray-50 transition-colors min-h-[96px]"
    >
      <div className="flex items-center justify-between">
        <div className="w-12 h-12 flex items-center justify-center rounded border mr-3 bg-white">
          {loadingImages[product.slug] || !imageMap[product.slug] ? (
            <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
          ) : (
            <img
              src={imageMap[product.slug]}
              alt={product.title}
              className="w-12 h-12 object-contain rounded"
              loading="lazy"
            />
          )}
        </div>

        <div className="flex-1 min-w-0 mr-3">
          <div className="font-medium text-gray-900 mb-1">
            {extractProductName(product.title, product.offers_count)}
          </div>
          <div className="text-sm text-gray-500 mb-2">
            {product.offers_count}
          </div>
        </div>

        <div className="flex space-x-2 flex-shrink-0">
          <button
            onClick={() => handleAddProduct(product.url)}
            disabled={isAddingProduct || isInWatchlist}
            className={`px-3 py-1 rounded text-sm flex items-center space-x-1 ${
              isAddingProduct || isInWatchlist
                ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                : 'bg-green-600 text-white hover:bg-green-700'
            }`}
            title={isInWatchlist ? "Already in watchlist" : "Add to watchlist"}
          >
            <Plus className="w-3 h-3" />
            <span>{isInWatchlist ? 'Added' : 'Add'}</span>
          </button>
        </div>
      </div>
    </div>
  );
})}

              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <Search className="w-12 h-12 text-gray-300 mx-auto mb-2" />
              <p className="text-gray-500">No products found for "{query}"</p>
              <p className="text-gray-400 text-sm mt-1">
                Try different keywords or check your spelling
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
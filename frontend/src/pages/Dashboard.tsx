import { useEffect, useState } from 'react';
import API from '../api';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import ProductCard from '../components/ProductCard';
import { cache, cacheKeys } from '../utils/cache';
import { Loader2 } from 'lucide-react';

interface ProductInfo {
  url: string;
  retailer?: string;
  best_price?: number;
  average_price?: number;
  product_name?: string;
  image_url?: string;
  savings?: number;
  last_updated?: string;
}

export default function Dashboard() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [productInfo, setProductInfo] = useState<Record<string, ProductInfo>>({});
  const [newUrl, setNewUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [addingProduct, setAddingProduct] = useState(false);
  const navigate = useNavigate();

  const username = localStorage.getItem('username');

  useEffect(() => {
    if (!username) {
      navigate('/');
      return;
    }

    // Check cache first
    const cachedWatchlist = cache.get<string[]>(cacheKeys.watchlist(username));
    if (cachedWatchlist) {
      setWatchlist(cachedWatchlist);
      // Still fetch product info for cached watchlist
      if (cachedWatchlist.length > 0) {
        fetchProductInfo(cachedWatchlist);
      }
    }

    // Fetch fresh data from API
    API.get(`/watchlist/${username}`)
      .then((res) => {
        setWatchlist(res.data);
        // Cache the watchlist
        cache.set(cacheKeys.watchlist(username), res.data, 10 * 60 * 1000); // 10 minutes
        
        // Fetch product info for all URLs
        if (res.data.length > 0) {
          fetchProductInfo(res.data);
        }
      })
      .catch((error) => {
        console.error('Failed to fetch watchlist:', error);
        setWatchlist([]);
      });
  }, [username, navigate]);

  const fetchProductInfo = async (urls: string[]) => {
    try {
      setLoading(true);
      console.log('Fetching product info for URLs:', urls);
      
      // Check cache first
      const cacheKey = cacheKeys.productInfo(urls);
      const cachedData = cache.get<ProductInfo[]>(cacheKey);
      
      if (cachedData) {
        console.log('Using cached data:', cachedData);
        const infoMap: Record<string, ProductInfo> = {};
        cachedData.forEach((info: ProductInfo) => {
          infoMap[info.url] = info;
        });
        setProductInfo(infoMap);
        return; // Use cached data
      }

      // If not cached, fetch from API
      const response = await API.post('/product-details', { urls });
      console.log('API response:', response.data);
      
      const infoMap: Record<string, ProductInfo> = {};
      response.data.forEach((info: ProductInfo) => {
        infoMap[info.url] = info;
      });
      setProductInfo(infoMap);
      
      // Cache the response
      cache.set(cacheKey, response.data, 5 * 60 * 1000); // 5 minutes
    } catch (error) {
      console.error('Failed to fetch product info:', error);
    } finally {
      setLoading(false);
    }
  };

  const addUrl = async () => {
    if (!newUrl) return;
    
    try {
      setAddingProduct(true);
      
      // Add to watchlist
      await API.post(`/watchlist/${username}`, { url: newUrl });
      const updatedWatchlist = [...watchlist, newUrl];
      setWatchlist(updatedWatchlist);
      
      // Update cache
      cache.set(cacheKeys.watchlist(username!), updatedWatchlist, 10 * 60 * 1000);
      
      // Trigger price aggregation in the background
      try {
        await API.post('/aggregate-prices');
      } catch (aggError) {
        console.warn('Price aggregation failed:', aggError);
      }
      
      // Fetch updated product details
      try {
        const newProductInfo = await API.post('/product-details', { urls: [newUrl] });
        
        // Update product info state
        setProductInfo(prev => ({
          ...prev,
          [newUrl]: newProductInfo.data[0]
        }));
      } catch (infoError) {
        console.warn('Failed to fetch product info for new URL:', infoError);
      }
      
      // Clear the input
      setNewUrl('');
    } catch (error) {
      console.error('Failed to add product:', error);
    } finally {
      setAddingProduct(false);
    }
  };

  const deleteUrl = async (url: string) => {
    try {
      await API.delete(`/watchlist/${username}`, { data: { url } });
      const updatedWatchlist = watchlist.filter((u) => u !== url);
      setWatchlist(updatedWatchlist);
      
      // Update cache
      cache.set(cacheKeys.watchlist(username!), updatedWatchlist, 10 * 60 * 1000);
      
      // Remove from productInfo
      const newProductInfo = { ...productInfo };
      delete newProductInfo[url];
      setProductInfo(newProductInfo);
    } catch (error) {
      console.error('Failed to delete URL:', error);
    }
  };

  const navigateToProduct = (url: string) => {
    const encodedUrl = encodeURIComponent(url);
    navigate(`/product/${encodedUrl}`);
  };

  const triggerAggregation = async () => {
    try {
      setLoading(true);
      await API.post('/aggregate-prices');
      
      // Clear cache and refresh product info after aggregation
      cache.clear();
      if (watchlist.length > 0) {
        await fetchProductInfo(watchlist);
      }
    } catch (error) {
      console.error('Failed to refresh prices:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <h1 className="text-xl font-bold mb-4 text-center">Your Watchlist</h1>

      <div className="space-y-3">
        <ul className="space-y-2">
          {watchlist.length === 0 ? (
            <p className="text-sm text-gray-500 text-center">No items yet.</p>
          ) : (
            watchlist.map((url) => {
              const info = productInfo[url];
              
              // Debug logging
              console.log(`Product info for ${url}:`, info);
              
              return (
                <ProductCard
                  key={url}
                  url={url}
                  productName={info?.product_name || 'Loading...'}
                  bestPrice={info?.best_price || 0}
                  averagePrice={info?.average_price || 0}
                  retailer={info?.retailer || 'Unknown'}
                  onClick={() => navigateToProduct(url)}
                  onRemove={() => deleteUrl(url)}
                  loading={loading && !info?.best_price}
                />
              );
            })
          )}
        </ul>

        <div className="relative">
          <input
            type="text"
            placeholder="Add BuyWisely URL"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                addUrl();
              }
            }}
            className="border border-gray-300 p-2 w-full rounded pr-10"
          />
          {addingProduct && (
            <div className="absolute right-2 top-1/2 transform -translate-y-1/2">
              <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
            </div>
          )}
        </div>
        
        <button
          onClick={addUrl}
          disabled={addingProduct}
          className={`bg-blue-600 text-white w-full py-2 rounded ${
            addingProduct ? 'opacity-50 cursor-not-allowed' : 'hover:bg-blue-700'
          }`}
        >
          {addingProduct ? 'Adding...' : 'Add'}
        </button>

        <button
          onClick={triggerAggregation}
          disabled={loading}
          className={`text-sm text-gray-500 mt-2 underline block w-full text-center ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Refreshing...' : 'Refresh Prices'}
        </button>
        <button
          onClick={() => navigate('/settings')}
          className="text-sm text-blue-700 mt-2 underline block w-full text-center"
        >
          Go to Settings
        </button>
      </div>
    </Layout>
  );
}
import { useEffect, useState } from 'react';
import API from '../api';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import ProductCard from '../components/ProductCard';
import ProductCardSkeleton from '../components/ProductCardSkeleton';
import { cache, cacheKeys } from '../utils/cache';

interface ProductInfo {
  url: string;
  retailer: string;
  best_price: number;
  average_price: number;
  product_name: string;
}

export default function Dashboard() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [productInfo, setProductInfo] = useState<Record<string, ProductInfo>>({});
  const [newUrl, setNewUrl] = useState('');
  const [loading, setLoading] = useState(false);
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
      .catch(() => setWatchlist([]));
  }, [username, navigate]);

  const fetchProductInfo = async (urls: string[]) => {
    try {
      // Check cache first
      const cacheKey = cacheKeys.productInfo(urls);
      const cachedData = cache.get<ProductInfo[]>(cacheKey);
      
      if (cachedData) {
        const infoMap: Record<string, ProductInfo> = {};
        cachedData.forEach((info: ProductInfo) => {
          infoMap[info.url] = info;
        });
        setProductInfo(infoMap);
        return; // Use cached data
      }

      // If not cached, fetch from API
      setLoading(true);
      const response = await API.post('/product-info', { urls });
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
    
    // Add to watchlist
    await API.post(`/watchlist/${username}`, { url: newUrl });
    const updatedWatchlist = [...watchlist, newUrl];
    setWatchlist(updatedWatchlist);
    
    // Update cache
    cache.set(cacheKeys.watchlist(username!), updatedWatchlist, 10 * 60 * 1000);
    
    // Clear the product info cache to force refresh with new item
    cache.clear();
    
    // Fetch info for all URLs including the new one
    fetchProductInfo(updatedWatchlist);
    
    setNewUrl('');
  };

  const deleteUrl = async (url: string) => {
    await API.delete(`/watchlist/${username}`, { data: { url } });
    const updatedWatchlist = watchlist.filter((u) => u !== url);
    setWatchlist(updatedWatchlist);
    
    // Update cache
    cache.set(cacheKeys.watchlist(username!), updatedWatchlist, 10 * 60 * 1000);
    
    // Remove from productInfo
    const newProductInfo = { ...productInfo };
    delete newProductInfo[url];
    setProductInfo(newProductInfo);
  };

  const navigateToProduct = (url: string) => {
    const encodedUrl = encodeURIComponent(url);
    navigate(`/product/${encodedUrl}`);
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
              
              if (info) {
                return (
                  <ProductCard
                    key={url}
                    url={url}
                    productName={info.product_name}
                    bestPrice={info.best_price}
                    averagePrice={info.average_price}
                    retailer={info.retailer}
                    onClick={() => navigateToProduct(url)}
                    onRemove={() => deleteUrl(url)}
                    loading={loading && !info}
                  />
                );
              } else {
                return (
                  <ProductCardSkeleton
                    key={url}
                    url={url}
                    onClick={() => navigateToProduct(url)}
                    onRemove={() => deleteUrl(url)}
                  />
                );
              }
            })
          )}
        </ul>

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
          className="border border-gray-300 p-2 w-full rounded"
        />
        <button
          onClick={addUrl}
          className="bg-blue-600 text-white w-full py-2 rounded hover:bg-blue-700"
        >
          Add
        </button>

        <button
          onClick={() => {
            cache.clear();
            // Refetch all data
            if (watchlist.length > 0) {
              fetchProductInfo(watchlist);
            }
          }}
          className="text-sm text-gray-500 mt-2 underline block w-full text-center"
        >
          Refresh Prices
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
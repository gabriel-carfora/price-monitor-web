import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ExternalLink, TrendingDown, TrendingUp } from 'lucide-react';
import API from '../api';
import Layout from '../components/Layout';
import { cache, cacheKeys } from '../utils/cache';

interface Retailer {
  name: string;
  price: number;
  url: string;
  avg_price?: number;
  price_count?: number;
}

interface ProductDetails {
  url: string;
  product_name: string;
  image_url: string | null;
  best_price: number;
  average_price: number;
  retailer: string;
  last_updated: string;
  all_retailers: Retailer[];
}

export default function Product() {
  const { productUrl } = useParams<{ productUrl: string }>();
  const navigate = useNavigate();
  const [product, setProduct] = useState<ProductDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedImageUrl, setFetchedImageUrl] = useState<string | null>(null);
  const [imageLoaded, setImageLoaded] = useState(false);

  useEffect(() => {
    if (!productUrl) return;
    if (productUrl) {
      const slug = decodeURIComponent(productUrl).split('/').pop();
      if (slug) {
        API.post('/product-image', { slug, size: 'fullsize' })
          .then(res => {
            if (res.data.image_url) {
              setFetchedImageUrl(res.data.image_url);
            }
          })
          .catch(err => {
            console.warn("❌ Failed to fetch image from API:", err);
          });
    }
}
    fetchProductDetails();
  }, [productUrl]);
  
  const fetchProductDetails = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const decodedUrl = decodeURIComponent(productUrl!);
      const cacheKey = cacheKeys.productDetails(decodedUrl);
      const cachedData = cache.get<ProductDetails>(cacheKey);
      
      if (cachedData) {
        setProduct(cachedData);
        setLoading(false);
        
        // Check if cache is older than 2 minutes, fetch fresh data in background
        const age = cache.getAge(cacheKey);
        if (age && age > 2 * 60 * 1000) {
          // Fetch fresh data in background
          API.post('/product-details', { urls: [decodedUrl] })
            .then(response => {
              if (response.data && response.data.length > 0) {
                const transformedData = transformProductData(response.data[0]);
                setProduct(transformedData);
                cache.set(cacheKey, transformedData, 10 * 60 * 1000);
              }
            })
            .catch(() => {}); // Silently fail, we have cached data
        }
        return;
      }
      
      // No cache, fetch from API
      const response = await API.post('/product-details', { urls: [decodedUrl] });
      
      if (response.data && response.data.length > 0) {
        const transformedData = transformProductData(response.data[0]);
        setProduct(transformedData);
        cache.set(cacheKey, transformedData, 10 * 60 * 1000);
      } else {
        setError('Product not found');
      }
    } catch (err) {
      setError('Failed to load product details');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const transformProductData = (data: any): ProductDetails => {
    return {
      url: data.url,
      product_name: data.product_name,
      image_url: data.image_url,
      best_price: data.best_price,
      average_price: data.average_price,
      retailer: data.retailer,
      last_updated: data.last_updated || new Date().toISOString(),
      all_retailers: data.all_retailers || []
    };
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-AU', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const calculateSavings = (price: number, bestPrice: number) => {
    const savings = price - bestPrice;
    const percentage = ((savings / price) * 100).toFixed(0);
    return { savings, percentage };
  };

  const getBestAndWorstRetailers = (retailers: Retailer[]) => {
    if (!retailers || retailers.length === 0) return { best: [], worst: [] };
    
    // Sort retailers by price (ascending)
    const sortedRetailers = [...retailers].sort((a, b) => a.price - b.price);
    
    // Get best 10 (lowest prices)
    const best = sortedRetailers.slice(0, 10);
    
    // Get worst 10 (highest prices) - reverse order for display
    const worst = sortedRetailers.slice(-10).reverse();
    
    return { best, worst };
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center items-center h-64">
          <div className="text-gray-500">Loading product details...</div>
        </div>
      </Layout>
    );
  }

  if (error || !product) {
    return (
      <Layout>
        <div className="text-center py-8">
          <p className="text-red-600 mb-4">{error || 'Product not found'}</p>
          <button
            onClick={() => navigate('/dashboard')}
            className="text-blue-600 hover:underline"
          >
            Back to Dashboard
          </button>
        </div>
      </Layout>
    );
  }

  const { savings, percentage } = calculateSavings(product.average_price, product.best_price);
  const { best, worst } = getBestAndWorstRetailers(product.all_retailers);

  return (
    <Layout>
      <div className="max-w-4xl mx-auto px-2 sm:px-4">
        {/* Header */}
        <div className="flex items-center mb-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="p-2 hover:bg-gray-100 rounded-full mr-2 flex-shrink-0"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-lg sm:text-xl font-bold flex-1 min-w-0">
            {product.product_name}
          </h1>
        </div>

        {/* Product Image */}
{fetchedImageUrl && (
<div className="flex justify-center items-center mb-6 min-h-[200px] relative">
  {/* Dummy placeholder (shimmer or placeholder image) */}
  {!imageLoaded && (
    <div className="absolute w-full h-full max-w-xs flex justify-center items-center">
      <img
        src="https://via.placeholder.com/300x200?text=Loading"
        alt="Loading placeholder"
        className="rounded-lg shadow-md max-w-xs w-full h-auto object-contain"
      />
    </div>
  )}

  {/* Actual image */}
  {fetchedImageUrl && (
    <img
      src={fetchedImageUrl}
      alt={product.product_name}
      onLoad={() => setImageLoaded(true)}
      onError={() => setImageLoaded(true)} // Treat failure as "loaded" to hide placeholder
      className={`rounded-lg shadow-md max-w-xs w-full h-auto object-contain transition-opacity duration-300 ${
        imageLoaded ? 'opacity-100' : 'opacity-0'
      }`}
    />
  )}
</div>

)}


        {/* Price Summary - Mobile Optimized */}
        <div className="bg-white rounded-lg shadow-sm p-4 mb-4">
          {/* Mobile Layout - Stacked */}
          <div className="block sm:hidden">
            <div className="text-center mb-4">
              <div className="text-3xl font-bold text-green-600 mb-1">
                ${product.best_price.toFixed(2)}
              </div>
              <div className="text-sm text-gray-500">
                Best price at {product.retailer}
              </div>
            </div>
            
            <div className="text-center mb-4">
              <div className="text-sm text-gray-500 mb-1">Average price</div>
              <div className="text-xl font-medium">${product.average_price.toFixed(2)}</div>
              {savings > 0 && (
                <div className="text-sm text-green-600 flex items-center justify-center mt-1">
                  <TrendingDown className="w-3 h-3 mr-1" />
                  Save ${savings.toFixed(2)} ({percentage}%)
                </div>
              )}
            </div>
          </div>

          {/* Desktop Layout - Side by Side */}
          <div className="hidden sm:flex justify-between items-start mb-3">
            <div>
              <div className="text-2xl font-bold text-green-600">
                ${product.best_price.toFixed(2)}
              </div>
              <div className="text-sm text-gray-500">
                Best price at {product.retailer}
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm text-gray-500">Average price</div>
              <div className="text-lg">${product.average_price.toFixed(2)}</div>
              {savings > 0 && (
                <div className="text-sm text-green-600 flex items-center justify-end">
                  <TrendingDown className="w-3 h-3 mr-1" />
                  Save ${savings.toFixed(2)} ({percentage}%)
                </div>
              )}
            </div>
          </div>
          
          {/* Summary stats */}
          <div className="text-sm text-gray-500 text-center border-t pt-3">
            Found prices from {product.all_retailers.length} retailers
          </div>
        </div>

        {/* Best 10 Prices */}
        {best.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm p-4 mb-4">
            <div className="flex items-center mb-3">
              <TrendingDown className="w-5 h-5 text-green-600 mr-2" />
              <h2 className="font-semibold text-green-600">Best Prices (Top {best.length})</h2>
            </div>
            <div className="space-y-2">
              {best.map((retailer, index) => (
                <div
                  key={`best-${retailer.name}-${index}`}
                  className={`flex items-center p-3 rounded ${
                    index === 0 ? 'bg-green-50 border border-green-200' : 'bg-gray-50'
                  }`}
                >
                  {/* Mobile Layout */}
                  <div className="flex-1 min-w-0 pr-2">
                    <div className="font-medium truncate">{retailer.name}</div>
                    <div className="text-xs text-gray-500 truncate">
                      {retailer.url}
                      {retailer.price_count && (
                        <span className="block sm:inline sm:ml-2">({retailer.price_count} price points)</span>
                      )}
                    </div>
                  </div>
                  
                  {/* Price Section */}
                  <div className="text-right flex-shrink-0 mr-3">
                    <div className={`font-semibold ${index === 0 ? 'text-green-600' : ''}`}>
                      ${retailer.price.toFixed(2)}
                    </div>
                    {index > 0 && (
                      <div className="text-xs text-gray-500">
                        +${(retailer.price - product.best_price).toFixed(2)}
                      </div>
                    )}
                    {index === 0 && (
                      <div className="text-xs text-green-600">Best Deal!</div>
                    )}
                  </div>
                  
                  {/* External Link */}
                  <a
                    href={retailer.url.startsWith('http') ? retailer.url : `https://${retailer.url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 hover:bg-gray-200 rounded flex-shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink className="w-4 h-4 text-gray-600" />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Worst 10 Prices */}
        {worst.length > 1 && (
          <div className="bg-white rounded-lg shadow-sm p-4 mb-4">
            <div className="flex items-center mb-3">
              <TrendingUp className="w-5 h-5 text-amber-600 mr-2" />
              <h2 className="font-semibold text-amber-600">Highest Prices (Top {worst.length})</h2>
            </div>
            <div className="space-y-2">
              {worst.map((retailer, index) => (
                <div
                  key={`worst-${retailer.name}-${index}`}
                  className="flex items-center p-3 rounded bg-red-50 border border-red-100"
                >
                  {/* Mobile Layout */}
                  <div className="flex-1 min-w-0 pr-2">
                    <div className="font-medium truncate">{retailer.name}</div>
                    <div className="text-xs text-gray-500 truncate">
                      {retailer.url}
                      {retailer.price_count && (
                        <span className="block sm:inline sm:ml-2">({retailer.price_count} price points)</span>
                      )}
                    </div>
                  </div>
                  
                  {/* Price Section */}
                  <div className="text-right flex-shrink-0 mr-3">
                    <div className="font-semibold text-red-600">
                      ${retailer.price.toFixed(2)}
                    </div>
                    <div className="text-xs text-red-500">
                      +${(retailer.price - product.best_price).toFixed(2)} vs best
                    </div>
                  </div>
                  
                  {/* External Link */}
                  <a
                    href={retailer.url.startsWith('http') ? retailer.url : `https://${retailer.url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 hover:bg-red-200 rounded flex-shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink className="w-4 h-4 text-gray-600" />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* All Retailers Summary */}
        {product.all_retailers.length > 20 && (
          <div className="bg-white rounded-lg shadow-sm p-4 mb-4">
            <h3 className="font-semibold mb-3">Price Range Summary</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-gray-500">Lowest Price</div>
                <div className="font-semibold text-green-600">
                  ${Math.min(...product.all_retailers.map(r => r.price)).toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-gray-500">Highest Price</div>
                <div className="font-semibold text-red-600">
                  ${Math.max(...product.all_retailers.map(r => r.price)).toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-gray-500">Price Spread</div>
                <div className="font-semibold">
                  ${(Math.max(...product.all_retailers.map(r => r.price)) - 
                     Math.min(...product.all_retailers.map(r => r.price))).toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-gray-500">Total Retailers</div>
                <div className="font-semibold">{product.all_retailers.length}</div>
              </div>
            </div>
          </div>
        )}

        {/* Last Updated */}
        <div className="text-center text-sm text-gray-500 mt-4">
          Last updated: {formatDate(product.last_updated)}
        </div>

        {/* Original URL */}
        <div className="text-center mt-2 mb-6">
          <a
            href={product.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:underline inline-flex items-center"
          >
            View on BuyWisely
            <ExternalLink className="w-3 h-3 ml-1" />
          </a>
        </div>
      </div>
    </Layout>
  );
}
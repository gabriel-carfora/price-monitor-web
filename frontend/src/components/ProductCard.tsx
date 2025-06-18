import { useEffect, useState } from 'react';
import { TrendingDown } from 'lucide-react';
import API from '../api';

interface ProductCardProps {
  productName: string;
  bestPrice: number;
  averagePrice: number;
  retailer: string;
  onClick: () => void;
  onRemove: () => void;
  imageUrl?: string;
  slug?: string;
  loading?: boolean;
}

export default function ProductCard({
  productName,
  bestPrice,
  averagePrice,
  retailer,
  onClick,
  onRemove,
  imageUrl,
  slug,
  loading = false,
}: ProductCardProps) {
  const [fetchedImageUrl, setFetchedImageUrl] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(true); // <-- NEW

useEffect(() => {
    const fetchImage = async () => {
      if (imageUrl || !slug) return;

      try {
        const res = await API.post('/product-image', {
          slug,
          size: 'fullsize',
        });

        if (res.data.image_url) {
          setFetchedImageUrl(res.data.image_url);
        }
      } catch (err) {
        console.warn(`❌ Failed to fetch image for slug: ${slug}`);
      }
    };

    fetchImage();
  }, [imageUrl, slug]);

  const finalImage = imageUrl || fetchedImageUrl;
  const savings = averagePrice - bestPrice;
  const savingsPercentage =
    averagePrice > 0 ? ((savings / averagePrice) * 100).toFixed(0) : 0;
  const hasSavings = savings > 0.01;

  if (loading) {
    return (
      <div className="bg-white rounded shadow-sm px-4 py-3 text-sm">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <li
      className="bg-white rounded shadow-sm px-4 py-3 text-sm hover:shadow-md transition-shadow cursor-pointer"
      onClick={onClick}
    >
      <div className="flex space-x-4 items-center">

        <div className="w-20 h-20 rounded flex items-center justify-center bg-gray-100 relative overflow-hidden">
          {finalImage && (
            <img
              src={finalImage}
              alt={productName}
              className={`w-full h-full object-cover transition-opacity duration-300 ${
                imageLoading ? 'opacity-0' : 'opacity-100'
              }`}
              loading="lazy"
              onLoad={() => setImageLoading(false)}
              onError={() => setImageLoading(false)}
            />
          )}
          {imageLoading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-5 h-5 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
            </div>
          )}
        </div>

  <div className="flex-1">
    <div className="font-semibold text-base mb-0.5">{productName}</div>
    <div className="flex items-center space-x-2">
      <div className="text-green-600 font-semibold text-lg">
        ${bestPrice.toFixed(2)}
      </div>
      {hasSavings && (
        <div className="flex items-center text-green-600 text-xs">
          <TrendingDown className="w-3 h-3 mr-1" />
          <span>{savingsPercentage}%</span>
        </div>
      )}
    </div>

<div className="flex items-center space-x-2">
  <span className="text-gray-600 text-xs w-16">Avg Price:</span>
  <span className="text-xs text-yellow-600">
    ${averagePrice.toFixed(2)}
  </span>
</div>

{hasSavings && (
  <div className="flex items-center space-x-2">
    <span className="text-gray-600 text-xs w-16">Saving:</span>
    <span className="text-xs text-green-600">
      ${savings.toFixed(2)}
    </span>
  </div>
)}

    <div className="text-gray-500 text-xs mt-1">Best at {retailer}</div>
  </div>

  <button
    onClick={(e) => {
      e.stopPropagation();
      onRemove();
    }}
    className="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-3 rounded"
  >
    Remove
  </button>
</div>

    </li>
  );
}

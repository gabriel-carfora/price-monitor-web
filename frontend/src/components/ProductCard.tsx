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
<div className="flex space-x-4 items-start">
  {finalImage && (
    <img
      src={finalImage}
      alt={productName}
      className="w-20 h-20 rounded object-cover flex-shrink-0"
      loading="lazy"
    />
  )}

  <div className="flex-1">
    <div className="font-semibold text-base mb-1">{productName}</div>

    <div className="flex items-center space-x-2">
      <div className="text-green-600 font-semibold text-lg">
        ${bestPrice.toFixed(2)}
      </div>
      {hasSavings && (
        <div className="flex items-center text-green-600 text-xs">
          <TrendingDown className="w-3 h-3 mr-1" />
          <span>{savingsPercentage}% less than average</span>
        </div>
      )}
    </div>

    <div className="flex items-center space-x-2 mt-1">
      <span className="text-gray-500 text-xs">Avg:</span>
      <span
        className={`text-xs ${
          hasSavings ? 'line-through text-gray-400' : 'text-gray-600'
        }`}
      >
        ${averagePrice.toFixed(2)}
      </span>
      {hasSavings && (
        <span className="text-xs text-green-600">
          Save ${savings.toFixed(2)}
        </span>
      )}
    </div>

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

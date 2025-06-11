// frontend/src/components/ProductCard.tsx
import { TrendingDown, AlertCircle } from 'lucide-react';

interface ProductCardProps {
  url: string;
  productName: string;
  bestPrice: number;
  averagePrice: number;
  retailer: string;
  onClick: () => void;
  onRemove: () => void;
  loading?: boolean;
}

export default function ProductCard({ 
  url, 
  productName, 
  bestPrice, 
  averagePrice, 
  retailer, 
  onClick, 
  onRemove,
  loading = false 
}: ProductCardProps) {
  const savings = averagePrice - bestPrice;
  const savingsPercentage = averagePrice > 0 ? ((savings / averagePrice) * 100).toFixed(0) : 0;
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
      <div>
        <div className="font-semibold text-base mb-1">
          {productName}
        </div>
        <div className="flex justify-between items-start">
          <div className="flex-1">
            {/* Best Price */}
            <div className="flex items-center space-x-2">
              <div className="text-green-600 font-semibold text-lg">
                ${bestPrice.toFixed(2)}
              </div>
              {hasSavings && (
                <div className="flex items-center text-green-600 text-xs">
                  <TrendingDown className="w-3 h-3 mr-1" />
                  <span>{savingsPercentage}% off</span>
                </div>
              )}
            </div>
            
            {/* Average Price */}
            <div className="flex items-center space-x-2 mt-1">
              <span className="text-gray-500 text-xs">Avg:</span>
              <span className={`text-xs ${hasSavings ? 'line-through text-gray-400' : 'text-gray-600'}`}>
                ${averagePrice.toFixed(2)}
              </span>
              {hasSavings && (
                <span className="text-xs text-green-600">
                  Save ${savings.toFixed(2)}
                </span>
              )}
            </div>
            
            {/* Retailer */}
            <div className="text-gray-500 text-xs mt-1">
              Best at {retailer}
            </div>
            
          </div>
          
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="text-red-600 hover:underline text-xs ml-2 px-2 py-1"
          >
            Remove
          </button>
        </div>
      </div>
    </li>
  );
}
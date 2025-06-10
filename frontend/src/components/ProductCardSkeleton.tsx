interface ProductCardSkeletonProps {
  url: string;
  onClick: () => void;
  onRemove: () => void;
}

export default function ProductCardSkeleton({ url, onClick, onRemove }: ProductCardSkeletonProps) {
  return (
    <li
      className="bg-white rounded shadow-sm px-4 py-3 text-sm hover:shadow-md transition-shadow cursor-pointer"
      onClick={onClick}
    >
      <div className="flex justify-between items-center">
        <span className="break-words flex-1 mr-2 text-gray-500">
          {url}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="text-red-600 hover:underline text-xs"
        >
          Remove
        </button>
      </div>
    </li>
  );
}
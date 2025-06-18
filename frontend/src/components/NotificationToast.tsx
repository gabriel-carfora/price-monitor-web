import { useEffect, useState } from 'react';

interface NotificationToastProps {
  message: string;
  type?: 'success' | 'error' | 'info';
  duration?: number;
  onClose: () => void;
}

export default function NotificationToast({
  message,
  type = 'info',
  duration = 3000,
  onClose,
}: NotificationToastProps) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const fadeTimer = setTimeout(() => {
      setVisible(false); // Start fade-out
    }, duration - 1000); // Start fade 300ms before removal

    const removeTimer = setTimeout(() => {
      onClose();
    }, duration);

    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, [duration, onClose]);

  const typeClasses = {
    success: 'bg-green-600 text-white',
    error: 'bg-red-600 text-white',
    info: 'bg-blue-600 text-white',
  };

  return (
    <div
      className={`fixed bottom-4 right-4 px-4 py-2 rounded shadow-lg z-50 transition-opacity duration-300 ${
        visible ? 'opacity-100' : 'opacity-0'
      } ${typeClasses[type]}`}
    >
      {message}
    </div>
  );
}

import { useNavigate } from 'react-router-dom';
import { Menu } from 'lucide-react';

export default function Header() {
  const navigate = useNavigate();

  return (
    <header className="bg-white shadow-md p-4 flex items-center justify-between">
      {/* Menu icon placeholder for mobile */}
      <button className="sm:hidden p-2" onClick={() => {/* TODO: open drawer */}}>
        <Menu className="w-6 h-6 text-gray-700" />
      </button>

      {/* App Title */}
      <button onClick={() => navigate('/')}
>      <h1 className="text-lg font-semibold text-gray-800 text-center flex-1 sm:text-left">
        💸 PriceWatcher
      </h1>
      </button>

      {/* Desktop nav links */}
    <nav className="hidden sm:flex space-x-4">
    <button className="block px-2 py-1" onClick={() => navigate('/dashboard')}>Dashboard</button>
    <button className="block px-2 py-1" onClick={() => navigate('/settings')}>Settings</button>
    </nav>

    </header>
  );
}
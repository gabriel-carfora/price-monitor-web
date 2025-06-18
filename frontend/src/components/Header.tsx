// frontend/src/components/Header.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu } from 'lucide-react';
import MobileDrawer from './MobileDrawer';

export default function Header() {
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const toggleDrawer = () => {
    setDrawerOpen(!drawerOpen);
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
  };

  return (
    <>
      <header className="bg-white shadow-md p-4 flex items-center justify-between">
        {/* Mobile menu button */}
        <button 
          className="sm:hidden p-2 hover:bg-gray-100 rounded-lg transition-colors" 
          onClick={toggleDrawer}
        >
          <Menu className="w-6 h-6 text-gray-700" />
        </button>

        {/* App Title */}
        <button 
          onClick={() => navigate('/dashboard')}
          className="flex-1 sm:flex-initial"
        >
          <h1 className="text-lg font-semibold text-gray-800 text-center sm:text-left">
            💸 PriceWatch
          </h1>
        </button>

        {/* Desktop nav links */}
        <nav className="hidden sm:flex space-x-4">
          <button 
            className="px-3 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors" 
            onClick={() => navigate('/dashboard')}
          >
            Dashboard
          </button>
          <button 
            className="px-3 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors" 
            onClick={() => navigate('/settings')}
          >
            Settings
          </button>
        </nav>

        {/* Mobile spacer to center title */}
        <div className="sm:hidden w-10"></div>
      </header>

      {/* Mobile Drawer */}
      <MobileDrawer isOpen={drawerOpen} onClose={closeDrawer} />
    </>
  );
}

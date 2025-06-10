import { useEffect, useState } from 'react';
import API from '../api';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';

export default function Dashboard() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [newUrl, setNewUrl] = useState('');
  const navigate = useNavigate();

  const username = localStorage.getItem('username');

  useEffect(() => {
    if (!username) {
      navigate('/');
      return;
    }

    API.get(`/watchlist/${username}`)
      .then((res) => setWatchlist(res.data))
      .catch(() => setWatchlist([]));
  }, [username, navigate]);

  const addUrl = async () => {
    if (!newUrl) return;
    await API.post(`/watchlist/${username}`, { url: newUrl });
    setWatchlist((prev) => [...prev, newUrl]);
    setNewUrl('');
  };

  const deleteUrl = async (url: string) => {
    await API.delete(`/watchlist/${username}`, { data: { url } });
    setWatchlist((prev) => prev.filter((u) => u !== url));
  };

  return (
  <Layout>
    <h1 className="text-xl font-bold mb-4 text-center">Your Watchlist</h1>

    <div className="space-y-3">
      <ul className="space-y-2">
        {watchlist.length === 0 ? (
          <p className="text-sm text-gray-500 text-center">No items yet.</p>
        ) : (
          watchlist.map((url) => (
            <li
              key={url}
              className="bg-white rounded shadow-sm px-4 py-2 flex justify-between items-center text-sm"
            >
              <span className="break-words flex-1 mr-2">{url}</span>
              <button
                onClick={() => deleteUrl(url)}
                className="text-red-600 hover:underline text-xs"
              >
                Remove
              </button>
            </li>
          ))
        )}
      </ul>

      <input
        type="text"
        placeholder="Add BuyWisely URL"
        value={newUrl}
        onChange={(e) => setNewUrl(e.target.value)}
        className="border border-gray-300 p-2 w-full rounded"
      />
      <button
        onClick={addUrl}
        className="bg-blue-600 text-white w-full py-2 rounded hover:bg-blue-700"
      >
        Add
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

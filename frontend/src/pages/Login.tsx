import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { setUser } from '../api';
import Layout from '../components/Layout';

export default function Login() {
  const [username, setUsernameState] = useState('');
  const navigate = useNavigate();

  const handleLogin = () => {
    setUser(username);
    localStorage.setItem('username', username);
    navigate('/dashboard');
  };

  return (
    <Layout>
    <div className="p-4 max-w-sm mx-auto">
      <h1 className="text-xl font-bold mb-4">Login</h1>
      <input
        type="text"
        className="border p-2 w-full mb-4"
        placeholder="Enter username"
        value={username}
        onChange={(e) => setUsernameState(e.target.value)}
      />
      <button className="bg-blue-600 text-white px-4 py-2 w-full" onClick={handleLogin}>
        Continue
      </button>
    </div>
    </Layout>
  );
}

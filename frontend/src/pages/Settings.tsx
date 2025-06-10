import { useEffect, useState } from 'react';
import API from '../api';
import type { UserSettings } from '../types';
import { useNavigate } from 'react-router-dom';

export default function Settings() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const navigate = useNavigate();

  const username = localStorage.getItem('username');

  useEffect(() => {
    if (!username) {
      navigate('/');
      return;
    }

    API.get(`/users/${username}`)
      .then((res) => setSettings(res.data))
      .catch(() => setSettings(null));
  }, [username, navigate]);

  const handleChange = (key: keyof UserSettings, value: string | number) => {
    if (!settings) return;
    setSettings({
      ...settings,
      [key]:
        key === 'price_limit' && value === ''
          ? null
          : key === 'notification_frequency_days'
          ? parseInt(value as string)
          : value,
    });
  };

  const handleExclusions = (value: string) => {
    if (!settings) return;
    setSettings({
      ...settings,
      retailer_exclusions: value.split(',').map((s) => s.trim()).filter(Boolean),
    });
  };

  const handleSave = async () => {
    if (!username || !settings) return;
    setSaving(true);
    await API.put(`/users/${username}`, settings);
    setSaving(false);
  };

  const sendTest = async () => {
    if (!username) return;
    setTesting(true);
    await API.post(`/notify/test/${username}`);
    setTesting(false);
  };

  if (!settings) return <div className="p-4">Loading...</div>;

  return (
    <div className="p-4 max-w-sm mx-auto">
      <h1 className="text-xl font-bold mb-4">Settings</h1>

      <label className="block mb-2">
        <span className="text-sm">Pushover Code</span>
        <input
          className="border p-2 w-full"
          value={settings.pushover_code}
          onChange={(e) => handleChange('pushover_code', e.target.value)}
        />
      </label>

      <label className="block my-2">
        <span className="text-sm">Price Limit ($)</span>
        <input
          className="border p-2 w-full"
          value={settings.price_limit ?? ''}
          onChange={(e) => handleChange('price_limit', e.target.value)}
        />
      </label>

      <label className="block my-2">
        <span className="text-sm">Retailer Exclusions (comma separated)</span>
        <input
          className="border p-2 w-full"
          value={settings.retailer_exclusions.join(', ')}
          onChange={(e) => handleExclusions(e.target.value)}
        />
      </label>

      <label className="block my-2">
        <span className="text-sm">Notification Frequency (days)</span>
        <input
          className="border p-2 w-full"
          type="number"
          value={settings.notification_frequency_days}
          onChange={(e) => handleChange('notification_frequency_days', e.target.value)}
        />
      </label>

      <button
        onClick={handleSave}
        className="bg-blue-600 text-white w-full p-2 my-2"
        disabled={saving}
      >
        {saving ? 'Saving...' : 'Save Settings'}
      </button>

      <button
        onClick={sendTest}
        className="bg-green-600 text-white w-full p-2"
        disabled={testing}
      >
        {testing ? 'Sending...' : 'Send Test Notification'}
      </button>

      <button
        onClick={() => navigate('/dashboard')}
        className="text-sm text-blue-700 mt-4 underline block w-full text-center"
      >
        Back to Dashboard
      </button>
    </div>
  );
}

import { useEffect, useState } from 'react';
import API from '../api';
// Update your frontend/src/types.ts as well:
// export interface UserSettings {
//   pushover_code: string;
//   price_limit: number | null;  // Now percentage (0-100)
//   retailer_exclusions: string[];
//   notification_frequency_days: number;
// }

import type { UserSettings } from '../types';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { Info, TestTube } from 'lucide-react';

export default function Settings() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    
    let processedValue: string | number | null = value;
    
    // Special handling for price_limit percentage
    if (key === 'price_limit') {
      if (value === '') {
        processedValue = null;
      } else {
        const numValue = parseFloat(value as string);
        if (isNaN(numValue) || numValue < 0 || numValue > 100) {
          setError('Price limit must be between 0 and 100 percent');
          return;
        }
        processedValue = numValue;
      }
    } else if (key === 'notification_frequency_days') {
      processedValue = parseInt(value as string);
    }
    
    setError(null);
    setSettings({
      ...settings,
      [key]: processedValue,
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
    setError(null);
    
    try {
      await API.put(`/users/${username}`, settings);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    if (!username) return;
    setTesting(true);
    try {
      await API.post(`/notify/test/${username}`);
    } catch (err) {
      console.error('Test notification failed:', err);
    } finally {
      setTesting(false);
    }
  };

  const triggerManualRefresh = async () => {
    setRefreshing(true);
    try {
      await API.post('/refresh-prices');
    } catch (err) {
      console.error('Manual refresh failed:', err);
    } finally {
      setRefreshing(false);
    }
  };

  if (!settings) return (
    <Layout>
      <div className="p-4">Loading...</div>
    </Layout>
  );

  return (
    <Layout>
      <div className="p-4 max-w-sm mx-auto">
        <h1 className="text-xl font-bold mb-4">Settings</h1>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded mb-4 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* Pushover Code */}
          <label className="block">
            <span className="text-sm font-medium">Pushover Code</span>
            <input
              className="border border-gray-300 p-2 w-full rounded mt-1"
              value={settings.pushover_code}
              onChange={(e) => handleChange('pushover_code', e.target.value)}
              placeholder="Enter your Pushover user key"
            />
          </label>

          {/* Price Limit (Percentage) */}
          <label className="block">
            <div className="flex items-center space-x-2 mb-1">
              <span className="text-sm font-medium">Discount Threshold (%)</span>
              <Info className="w-4 h-4 text-gray-400" />
            </div>
            <input
              className="border border-gray-300 p-2 w-full rounded"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={settings.price_limit ?? ''}
              onChange={(e) => handleChange('price_limit', e.target.value)}
              placeholder="e.g., 15 for 15% off"
            />
            <div className="text-xs text-gray-500 mt-1">
              Only notify when discount is at least this percentage off the average price
            </div>
          </label>

          {/* Retailer Exclusions */}
          <label className="block">
            <span className="text-sm font-medium">Retailer Exclusions</span>
            <input
              className="border border-gray-300 p-2 w-full rounded mt-1"
              value={settings.retailer_exclusions.join(', ')}
              onChange={(e) => handleExclusions(e.target.value)}
              placeholder="e.g., ebay, kmart"
            />
            <div className="text-xs text-gray-500 mt-1">
              Comma-separated list of retailers to exclude from price checks
            </div>
          </label>

          {/* Notification Frequency */}
          <label className="block">
            <span className="text-sm font-medium">Notification Frequency (days)</span>
            <input
              className="border border-gray-300 p-2 w-full rounded mt-1"
              type="number"
              min="1"
              value={settings.notification_frequency_days}
              onChange={(e) => handleChange('notification_frequency_days', e.target.value)}
            />
            <div className="text-xs text-gray-500 mt-1">
              Minimum days between notifications for the same product
            </div>
          </label>

          {/* Save Button */}
          <button
            onClick={handleSave}
            className="bg-blue-600 text-white w-full p-2 rounded hover:bg-blue-700 transition-colors"
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>

          {/* Test Notification */}
          <button
            onClick={sendTest}
            className="bg-green-600 text-white w-full p-2 rounded hover:bg-green-700 transition-colors flex items-center justify-center space-x-2"
            disabled={testing}
          >
            <TestTube className="w-4 h-4" />
            <span>{testing ? 'Sending...' : 'Send Test Notification'}</span>
          </button>

          {/* Manual Refresh */}
          <button
            onClick={triggerManualRefresh}
            className="bg-amber-600 text-white w-full p-2 rounded hover:bg-amber-700 transition-colors"
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Manual Price Refresh'}
          </button>

          {/* Info Section */}
          <div className="bg-blue-50 border border-blue-200 p-3 rounded text-sm">
            <div className="font-medium text-blue-800 mb-2">How notifications work:</div>
            <ul className="text-blue-700 space-y-1 text-xs">
              <li>• Prices are automatically refreshed daily at 6 AM UTC</li>
              <li>• You'll only be notified if the discount is better than before</li>
              <li>• Notifications require a Pushover account (pushover.net)</li>
              <li>• Set your discount threshold to avoid spam notifications</li>
            </ul>
          </div>

          {/* Navigation */}
          <button
            onClick={() => navigate('/dashboard')}
            className="text-sm text-blue-700 mt-4 underline block w-full text-center"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </Layout>
  );
}
export interface UserSettings {
  pushover_code: string;
  price_limit: number | null;
  retailer_exclusions: string[];
  notification_frequency_days: number;
}

export type Watchlist = string[];
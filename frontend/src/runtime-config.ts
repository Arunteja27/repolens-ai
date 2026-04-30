declare global {
  interface Window {
    __REPOLENS_CONFIG__?: {
      apiBaseUrl?: string;
    };
  }
}

export function getRuntimeApiBaseUrl(): string | undefined {
  const value = window.__REPOLENS_CONFIG__?.apiBaseUrl?.trim();
  return value ? value : undefined;
}

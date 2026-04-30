type EventCallback = (data: unknown) => void;

class WSClient {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<EventCallback>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private url: string;

  constructor(url?: string) {
    this.url = url || `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      console.log('[WS] Connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const type = data.type || 'message';
        this.listeners.get(type)?.forEach((cb) => cb(data));
        this.listeners.get('*')?.forEach((cb) => cb(data));
      } catch {
        this.listeners.get('text')?.forEach((cb) => cb(event.data));
      }
    };

    this.ws.onclose = () => {
      console.log('[WS] Disconnected');
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), 2000 * this.reconnectAttempts);
      }
    };

    this.ws.onerror = (err) => console.error('[WS] Error', err);
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }

  on(event: string, callback: EventCallback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  off(event: string, callback: EventCallback) {
    this.listeners.get(event)?.delete(callback);
  }

  send(data: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const ws = new WSClient();

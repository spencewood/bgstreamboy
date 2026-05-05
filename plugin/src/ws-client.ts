/** Reconnecting WebSocket client.
 *
 * Connects to the companion service. On disconnect, retries with exponential
 * backoff up to a cap. Pushes parsed snapshots through `onSnapshot`; signals
 * disconnect transitions through `onConnectionChange`.
 */

import WebSocket from "ws";

import type { Snapshot } from "./snapshot";

export type ConnectionState = "connecting" | "connected" | "disconnected";

export interface WsClientOptions {
  url: string;
  onSnapshot: (snapshot: Snapshot) => void;
  onConnectionChange: (state: ConnectionState) => void;
  log?: (msg: string, ...rest: unknown[]) => void;
}

const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 15000;

export class WsClient {
  private ws: WebSocket | null = null;
  private backoff = INITIAL_BACKOFF_MS;
  private retryTimer: NodeJS.Timeout | null = null;
  private stopped = false;
  private state: ConnectionState = "disconnected";

  constructor(private readonly opts: WsClientOptions) {}

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.ws) {
      this.ws.removeAllListeners();
      this.ws.close();
      this.ws = null;
    }
    this.setState("disconnected");
  }

  private connect(): void {
    if (this.stopped) return;
    this.setState("connecting");
    const ws = new WebSocket(this.opts.url);
    this.ws = ws;

    ws.on("open", () => {
      this.backoff = INITIAL_BACKOFF_MS;
      this.setState("connected");
    });

    ws.on("message", (data) => {
      try {
        const snapshot = JSON.parse(data.toString()) as Snapshot;
        this.opts.onSnapshot(snapshot);
      } catch (err) {
        this.log("failed to parse snapshot", err);
      }
    });

    ws.on("error", (err) => {
      this.log("ws error", err.message);
    });

    ws.on("close", () => {
      this.ws = null;
      this.setState("disconnected");
      if (this.stopped) return;
      this.scheduleReconnect();
    });
  }

  private scheduleReconnect(): void {
    const delay = this.backoff;
    this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS);
    this.retryTimer = setTimeout(() => this.connect(), delay);
  }

  private setState(next: ConnectionState): void {
    if (this.state === next) return;
    this.state = next;
    this.opts.onConnectionChange(next);
  }

  private log(msg: string, ...rest: unknown[]): void {
    this.opts.log?.(msg, ...rest);
  }
}

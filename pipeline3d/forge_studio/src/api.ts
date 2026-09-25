// Thin client for pipeline3d/forge_server.py. Every call except health sends the bearer token.

export type Settings = { serverUrl: string; token: string; geminiKey: string; model: string; speakReplies: boolean };

export type Health = {
  ok: boolean; blender: boolean; godot: boolean; godot_project: string; godot_project_exists: boolean;
  keys: Record<string, boolean>; google_image: boolean;
};

export type AssetSummary = { name: string; status: string; stages: Record<string, string>; previews: string[]; export: string | null };

export type AssetDetail = AssetSummary & {
  instructions: string | null; error: string | null; handoff: string[];
  manifest: Record<string, unknown> | null; log_tail: string; report: Record<string, any>;
};

export const STAGES = ["concept", "generate", "cleanup", "rig", "animate", "export", "godot"];

export class ForgeApi {
  constructor(private s: Settings) {}

  private url(path: string) {
    return this.s.serverUrl.replace(/\/+$/, "") + path;
  }

  private async req<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetch(this.url(path), {
      ...init,
      headers: { Authorization: `Bearer ${this.s.token}`, ...(init.headers || {}) },
    });
    const text = await res.text();
    let data: any;
    try { data = JSON.parse(text); } catch { data = { error: text }; }
    if (!res.ok) throw new Error(data?.error || `HTTP ${res.status}`);
    return data as T;
  }

  health() { return this.req<Health>("/api/health"); }
  examples() { return this.req<Record<string, unknown>>("/api/examples"); }
  assets() { return this.req<AssetSummary[]>("/api/assets"); }
  asset(name: string) { return this.req<AssetDetail>(`/api/assets/${encodeURIComponent(name)}`); }

  forge(manifest: unknown, restart = false) {
    return this.req<{ ok: boolean; name: string; status: string }>("/api/assets", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ manifest, restart }),
    });
  }

  resume(name: string) {
    return this.req<{ ok: boolean }>(`/api/assets/${encodeURIComponent(name)}/resume`, { method: "POST" });
  }

  upload(name: string, slot: string, file: File) {
    const q = `slot=${encodeURIComponent(slot)}&filename=${encodeURIComponent(file.name)}`;
    return this.req<{ ok: boolean; saved_as: string }>(`/api/assets/${encodeURIComponent(name)}/upload?${q}`, {
      method: "POST", body: file,
    });
  }

  /** Files need the auth header, so fetch them as blobs (for <img> and downloads). */
  async fileUrl(name: string, relPath: string): Promise<string> {
    const res = await fetch(this.url(`/api/assets/${encodeURIComponent(name)}/files/${relPath.split("/").map(encodeURIComponent).join("/")}`), {
      headers: { Authorization: `Bearer ${this.s.token}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return URL.createObjectURL(await res.blob());
  }
}

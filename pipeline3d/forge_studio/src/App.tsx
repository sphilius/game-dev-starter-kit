import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ForgeApi, STAGES, type AssetDetail, type AssetSummary, type Health, type Settings } from "./api";
import { askAssistant, type ChatTurn } from "./assistant";
import { speak, speechInputSupported, startDictation } from "./speech";

const SETTINGS_KEY = "forge-studio-settings";
const DEFAULTS: Settings = {
  serverUrl: "http://127.0.0.1:8765",
  token: "",
  geminiKey: (import.meta.env.VITE_GEMINI_API_KEY as string) || "",
  model: "gemini-flash-latest",
  speakReplies: false,
};

function loadSettings(): Settings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") };
  } catch {
    return DEFAULTS;
  }
}

function saveSettings(s: Settings) {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); } catch { /* private mode: keep in memory */ }
}

// ------------------------------------------------------------------ settings

function SettingsPanel({ s, onSave, onClose }: { s: Settings; onSave: (s: Settings) => void; onClose: () => void }) {
  const [draft, setDraft] = useState(s);
  const field = (key: keyof Settings, label: string, type = "text", hint = "") => (
    <label className="field">
      <span>{label}</span>
      <input type={type} value={String(draft[key])} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
      {hint && <small>{hint}</small>}
    </label>
  );
  return (
    <div className="modal" role="dialog" aria-label="Settings">
      <div className="card">
        <h2>Settings</h2>
        {field("serverUrl", "Forge server URL", "url", "Where forge_server.py listens. From a phone: your PC's LAN IP or a tunnel URL.")}
        {field("token", "Forge token", "password", "Printed by forge_server.py at startup (or your FORGE_TOKEN).")}
        {field("geminiKey", "Gemini API key", "password", "From aistudio.google.com/apikey. Stored only in this browser.")}
        {field("model", "Gemini model", "text", "Any Gemini text model id, e.g. gemini-flash-latest.")}
        <label className="check">
          <input type="checkbox" checked={draft.speakReplies} onChange={(e) => setDraft({ ...draft, speakReplies: e.target.checked })} />
          Read replies aloud
        </label>
        <div className="row">
          <button onClick={onClose} className="ghost">Cancel</button>
          <button onClick={() => { onSave(draft); onClose(); }}>Save</button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ asset detail

function AuthImage({ api, name, path, alt }: { api: ForgeApi; name: string; path: string; alt: string }) {
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    let url = "";
    api.fileUrl(name, path).then((u) => { url = u; setSrc(u); }).catch(() => setSrc(undefined));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [api, name, path]);
  return src ? <img src={src} alt={alt} /> : <div className="img-placeholder">loading…</div>;
}

async function download(api: ForgeApi, name: string, path: string) {
  const url = await api.fileUrl(name, path);
  const a = document.createElement("a");
  a.href = url;
  a.download = path.split("/").pop() || "file";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function Uploader({ api, name, slot, label, accept, multiple, onDone }: {
  api: ForgeApi; name: string; slot: string; label: string; accept: string; multiple?: boolean; onDone: (msg: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <label className={`upload ${busy ? "busy" : ""}`}>
      <span>{busy ? "Uploading…" : label}</span>
      <input type="file" accept={accept} multiple={multiple} disabled={busy} onChange={async (e) => {
        const files = Array.from(e.target.files || []);
        if (!files.length) return;
        setBusy(true);
        try {
          for (const f of files) await api.upload(name, slot, f);
          onDone(`Uploaded ${files.map((f) => f.name).join(", ")}`);
        } catch (err) {
          onDone(`Upload failed: ${(err as Error).message}`);
        } finally {
          setBusy(false);
          e.target.value = "";
        }
      }} />
    </label>
  );
}

function AssetPanel({ api, detail, onChanged }: { api: ForgeApi; detail: AssetDetail; onChanged: (msg?: string) => void }) {
  const waitingStage = Object.entries(detail.stages).find(([, v]) => v === "waiting")?.[0];
  return (
    <section className="asset" aria-label={`Asset ${detail.name}`}>
      <header>
        <h3>{detail.name}</h3>
        <span className={`badge ${detail.status}`}>{detail.status}</span>
      </header>
      <ol className="stages">
        {STAGES.map((s) => <li key={s} className={detail.stages[s] || "pending"}>{s}</li>)}
      </ol>

      {detail.status === "waiting" && (
        <div className="callout">
          <strong>Your turn{waitingStage ? `: ${waitingStage}` : ""}</strong>
          <pre>{detail.instructions}</pre>
          <div className="uploads">
            {waitingStage === "concept" && <Uploader api={api} name={detail.name} slot="concept" label="Upload reference image (PNG)" accept="image/png" onDone={onChanged} />}
            {waitingStage === "rig" && (
              <>
                {detail.handoff.map((h) => (
                  <button key={h} className="ghost" onClick={() => download(api, detail.name, h)}>Download {h.split("/").pop()}</button>
                ))}
                <Uploader api={api} name={detail.name} slot="rigged" label="Upload rigged FBX" accept=".fbx" onDone={onChanged} />
              </>
            )}
            {waitingStage === "animate" && <Uploader api={api} name={detail.name} slot="clip" label="Upload clip FBX files" accept=".fbx,.glb" multiple onDone={onChanged} />}
            <button onClick={async () => { await api.resume(detail.name); onChanged("Resumed"); }}>Resume</button>
          </div>
        </div>
      )}

      {detail.status === "error" && <div className="callout error"><strong>Stopped with an error</strong><pre>{detail.error}</pre>
        <button onClick={async () => { await api.resume(detail.name); onChanged("Retrying"); }}>Retry</button></div>}

      {detail.previews.length > 0 && (
        <div className="previews">
          {detail.previews.map((p) => <AuthImage key={p} api={api} name={detail.name} path={p} alt={p} />)}
        </div>
      )}
      {detail.export && <button onClick={() => download(api, detail.name, detail.export!)}>Download {detail.name}.glb</button>}
      <details>
        <summary>Log</summary>
        <pre className="log">{detail.log_tail || "(empty)"}</pre>
      </details>
    </section>
  );
}

// ------------------------------------------------------------------ app

export default function App() {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [showSettings, setShowSettings] = useState(!loadSettings().token);
  const api = useMemo(() => new ForgeApi(settings), [settings]);
  const [health, setHealth] = useState<Health | null>(null);
  const [serverError, setServerError] = useState("");
  const [examples, setExamples] = useState<Record<string, unknown>>({});
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [chat, setChat] = useState<ChatTurn[]>([
    { role: "model", text: "Describe the model you want: what it is, how big, the style (realistic, stylized, low-poly), and whether it needs to move. Type or tap the mic." },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [listening, setListening] = useState(false);
  const stopListening = useRef<() => void>(() => {});
  const [manifestText, setManifestText] = useState("");
  const [restart, setRestart] = useState(false);
  const [toast, setToast] = useState("");
  const chatEnd = useRef<HTMLDivElement>(null);

  const manifestError = useMemo(() => {
    if (!manifestText.trim()) return "empty";
    try { JSON.parse(manifestText); return ""; } catch (e) { return (e as Error).message; }
  }, [manifestText]);

  const refresh = useCallback(async () => {
    try {
      setHealth(await api.health());
      setAssets(await api.assets());
      setServerError("");
      if (selected) setDetail(await api.asset(selected));
    } catch (e) {
      setServerError((e as Error).message);
    }
  }, [api, selected]);

  useEffect(() => { api.examples().then(setExamples).catch(() => {}); }, [api]);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [chat, thinking]);
  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(""), 4000); return () => clearTimeout(t); } }, [toast]);

  async function send(text: string) {
    const t = text.trim();
    if (!t || thinking) return;
    if (!settings.geminiKey) { setShowSettings(true); setToast("Add your Gemini API key first"); return; }
    const history: ChatTurn[] = [...chat, { role: "user", text: t }];
    setChat(history);
    setInput("");
    setThinking(true);
    try {
      const r = await askAssistant({
        apiKey: settings.geminiKey, model: settings.model, history: history.slice(1), health, examples,
        current: manifestText, selected: detail,
      });
      setChat([...history, { role: "model", text: r.reply }]);
      if (r.manifest) setManifestText(JSON.stringify(r.manifest, null, 2));
      if (settings.speakReplies) speak(r.reply);
    } catch (e) {
      setChat([...history, { role: "model", text: `Gemini error: ${(e as Error).message}` }]);
    } finally {
      setThinking(false);
    }
  }

  // Dictation callbacks outlive this render; always call the latest send()
  const sendRef = useRef(send);
  sendRef.current = send;

  function toggleMic() {
    if (listening) { stopListening.current(); return; }
    setListening(true);
    stopListening.current = startDictation(
      (text, final) => { setInput(text); if (final && text) sendRef.current(text); },
      () => setListening(false),
      (msg) => { setToast(msg); setListening(false); },
    );
  }

  async function forgeIt() {
    try {
      const m = JSON.parse(manifestText);
      const r = await api.forge(m, restart);
      setSelected(r.name);
      setToast(`Queued ${r.name}`);
      refresh();
    } catch (e) {
      setToast(`Not forged: ${(e as Error).message}`);
    }
  }

  const connected = Boolean(health) && !serverError;

  return (
    <div className="app">
      <header className="top">
        <h1>Forge Studio</h1>
        <span className={`dot ${connected ? "on" : "off"}`} title={serverError || "connected"} />
        <span className="muted small">
          {connected
            ? `Blender ${health!.blender ? "✓" : "✗"} · Godot ${health!.godot ? "✓" : "✗"} · keys: ${Object.entries(health!.keys).filter(([, v]) => v).map(([k]) => k).join(", ") || "none"}`
            : `server offline${serverError ? `: ${serverError}` : ""}`}
        </span>
        <button className="ghost" onClick={() => setShowSettings(true)}>Settings</button>
      </header>

      <main className="grid">
        <section className="panel chat" aria-label="Assistant">
          <h2>Describe it</h2>
          <div className="messages">
            {chat.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
            {thinking && <div className="msg model muted">thinking…</div>}
            <div ref={chatEnd} />
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <textarea value={input} placeholder="e.g. a low-poly dire boar, about 1.1 m tall, needs walk and attack"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} />
            <div className="row">
              {speechInputSupported() && (
                <button type="button" className={listening ? "rec" : "ghost"} onClick={toggleMic} aria-pressed={listening}>
                  {listening ? "● Stop" : "🎤 Speak"}
                </button>
              )}
              <button type="submit" disabled={thinking || !input.trim()}>Send</button>
            </div>
          </form>
        </section>

        <section className="panel manifest" aria-label="Manifest">
          <h2>Manifest</h2>
          <textarea className="code" spellCheck={false} value={manifestText} onChange={(e) => setManifestText(e.target.value)}
            placeholder='The assistant fills this in. You can edit it, or paste one from pipeline3d/manifests/.' />
          <div className="row">
            <span className={`small ${manifestError && manifestError !== "empty" ? "err" : "muted"}`}>
              {manifestError === "empty" ? "" : manifestError ? `JSON error: ${manifestError}` : "valid JSON"}
            </span>
            <label className="check small"><input type="checkbox" checked={restart} onChange={(e) => setRestart(e.target.checked)} /> start over</label>
            <Uploader api={api} name={(() => { try { return JSON.parse(manifestText).name || "upload"; } catch { return "upload"; } })()}
              slot="model" label="Upload a model" accept=".glb,.fbx,.obj" onDone={setToast} />
            <button onClick={forgeIt} disabled={!!manifestError || !connected}>Forge it</button>
          </div>
        </section>

        <section className="panel assets" aria-label="Assets">
          <h2>Assets</h2>
          <ul className="asset-list">
            {assets.map((a) => (
              <li key={a.name}>
                <button className={`asset-btn ${selected === a.name ? "sel" : ""}`} onClick={() => setSelected(a.name)}>
                  <span>{a.name}</span><span className={`badge ${a.status}`}>{a.status}</span>
                </button>
              </li>
            ))}
            {!assets.length && <li className="muted small">Nothing forged yet.</li>}
          </ul>
          {detail && selected === detail.name && <AssetPanel api={api} detail={detail} onChanged={(m) => { if (m) setToast(m); refresh(); }} />}
        </section>
      </main>

      {showSettings && <SettingsPanel s={settings} onClose={() => setShowSettings(false)}
        onSave={(s) => { setSettings(s); saveSettings(s); }} />}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}

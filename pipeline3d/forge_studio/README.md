# Forge Studio

Describe a model by typing or speaking. Gemini turns the conversation into a forge
manifest, and **Forge it** builds it on your PC (Blender → Godot) through `forge_server.py`.
The app shows every stage, walks you through manual steps (upload the reference image,
the Mixamo rig, the clips), and shows previews and a GLB download when it's done.

```
Forge Studio (browser, phone, or AI Studio)  ──HTTPS/HTTP + token──►  forge_server.py (your PC)
   Gemini: chat → manifest                                              forge.py → Blender → Godot
   Web Speech API: voice in, voice out                                  previews, GLB, manual-step uploads
```

## Run it (≈ 10 min)

1. **Start the forge server** on the PC with Blender and Godot:
   ```powershell
   $env:BLENDER = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
   $env:GODOT   = "C:\Tools\Godot_v4.4.1-stable_win64.exe"
   $env:FORGE_TOKEN = "pick-a-long-random-string"
   python pipeline3d\forge_server.py            # add --host 0.0.0.0 to reach it from your phone on Wi-Fi
   ```
2. **Start the app**:
   ```bash
   cd pipeline3d/forge_studio
   npm install
   npm run dev          # http://localhost:5173
   ```
3. **Settings** (opens on first run): server URL `http://127.0.0.1:8765`, the token, and a
   Gemini API key from https://aistudio.google.com/apikey (free tier works; stored only in your browser).
4. Say "a low-poly bear about a metre tall that walks and attacks", check the manifest,
   and press **Forge it**.

**From your phone**: run the server with `--host 0.0.0.0`, open the app on the PC's LAN address
(`npm run dev -- --host`), and set the server URL to `http://<PC-LAN-IP>:8765`. Away from home, put
the server behind a tunnel (Cloudflare Tunnel, Tailscale Funnel or ngrok). **Keep the token secret**:
anyone with it can queue Blender jobs on your PC. Voice input works in Chrome, Edge and Android
Chrome; on iOS Safari it depends on the version.

## In Google AI Studio

AI Studio's **Build** mode makes and hosts React apps with Gemini wired in. You can recreate this
app there by pasting [`AI_STUDIO_PROMPT.md`](AI_STUDIO_PROMPT.md) into Build, then copying
`src/assistant.ts` (the system rules) and `src/api.ts` (the server client) into the generated
project. Two differences from running it locally:

* An AI Studio app runs on an **https** origin and your server is on your PC. Browsers only let
  https pages call `http://localhost` in some cases, so use a tunnel with https in front of
  `forge_server.py` (the server already sends the CORS and Private-Network headers).
* In AI Studio the Gemini key comes from the platform (`process.env.GEMINI_API_KEY` / `API_KEY`),
  so the key field in Settings can stay empty there.

I haven't run the AI Studio version myself; the local version is tested (see Testing).

## Testing

`tests/e2e.mjs` drives the built app in Chromium against a real `forge_server.py`, with Gemini
mocked at the network layer. It checks that chat fills the manifest, **Forge it** runs all seven
stages, previews load, and the phone layout has no sideways scroll.

```bash
npm run build && npx vite preview --port 4173 &
FORGE_TOKEN=... node tests/e2e.mjs
```

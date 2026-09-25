# Prompt for Google AI Studio → Build

Paste everything below the line into AI Studio's Build mode. Then replace the generated
Gemini call's system instruction with the `RULES` text from `src/assistant.ts`, and the
server calls with `src/api.ts`, so both apps behave the same.

---

Build a React + TypeScript web app called **Forge Studio** that works on desktop and phones.

Purpose: I describe a 3D game asset (creature, character, weapon, prop) by typing or speaking.
Gemini turns the conversation into a JSON "forge manifest". A button sends the manifest to my own
HTTP server ("forge server") running on my PC, which builds the model in Blender and imports it
into Godot. The app then tracks progress and shows previews.

Layout: three panels side by side on desktop, stacked on mobile, with a light/dark theme that
follows the system.
1. **Describe it**: chat with the assistant. A text box plus a microphone button using the browser
   Web Speech API (SpeechRecognition, continuous, interim results shown in the text box); when
   dictation ends, send the text. Optional "read replies aloud" with speechSynthesis.
2. **Manifest**: a monospace editor holding the latest manifest JSON with a live "valid JSON"
   indicator, a "start over" checkbox, an "Upload a model" file picker (.glb/.gltf/.fbx/.obj), and a
   **Forge it** button.
3. **Assets**: the list of assets from the server with status badges (new, queued, running,
   waiting, done, error). Selecting one shows seven stage chips (concept, generate, cleanup, rig,
   animate, export, godot), and:
   - when waiting: the server's instructions text, the right upload control for the waiting stage
     (reference PNG for concept; download the hand-off FBX and upload the rigged FBX for rig;
     upload clip FBX files for animate), and a Resume button;
   - when error: the error and a Retry button;
   - preview images, a "Download <name>.glb" button, and a collapsible log.
   Poll the selected asset every 3 seconds.

Gemini: use @google/genai `models.generateContent` with JSON output (responseMimeType
application/json) and this schema: `{reply: string, manifest_json: string, ready: boolean}`.
Send the whole conversation, plus context: the server's /api/health result, the example manifests
from /api/examples, the manifest currently in the editor, and the selected asset's status. Put
`reply` in the chat and, if `manifest_json` parses, put it in the editor, pretty-printed.

Forge server API (every call sends `Authorization: Bearer <token>` except health):
- GET /api/health → {blender, godot, keys:{tripo,meshy,rodin}, godot_project}
- GET /api/examples → {name: manifest}
- GET /api/assets → [{name, status, stages, previews, export}]
- POST /api/assets {manifest, restart} → 202 {name, status}
- GET /api/assets/<name> → {status, stages, instructions, error, previews[], export, handoff[], log_tail, manifest}
- POST /api/assets/<name>/resume
- POST /api/assets/<name>/upload?slot=concept|model|rigged|clip&filename=<file> with the raw file as the body
- GET /api/assets/<name>/files/<previews|export|handoff>/<file>. Fetch with the auth header and
  show images through object URLs (plain <img src> can't send the header).

Settings dialog (open on first run, saved in localStorage): forge server URL (default
http://127.0.0.1:8765), token, and Gemini model id (default gemini-flash-latest).
Show a green/red dot in the header for server reachability and whether Blender, Godot and each
provider key are available.

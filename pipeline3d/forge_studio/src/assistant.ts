// Gemini turns a conversation about a model into a forge manifest.
import { GoogleGenAI, Type } from "@google/genai";
import type { AssetDetail, Health } from "./api";

export type ChatTurn = { role: "user" | "model"; text: string };
export type AssistantReply = { reply: string; manifest: Record<string, unknown> | null; ready: boolean };

const RULES = `
You are the asset director for a Blender -> Godot 4 game pipeline called forge.
The user describes a 3D model for a game or animation (by typing or speaking; expect speech-to-text slips).
Your job: ask at most one or two short questions when something important is missing, then produce a
forge manifest. Keep replies short and concrete (2-5 sentences), friendly, no filler.

MANIFEST FIELDS (only these; the server rejects anything else):
- name: lowercase snake_case, starts with a letter, max 40 chars.
- kind: character | quadruped | prop | weapon | environment.
- concept: {tool: "banana" | "manual", prompt}  reference-image prompt. Omit for procedural or uploaded models.
    Prompt rules: one subject, full body, side view for quadrupeds / front A-pose (arms 45 deg down, hands open)
    for humanoids, limbs clearly separated, flat even studio light, no cast shadows, plain light-grey background,
    orthographic, no weapon in a body image, no text, no artist or franchise names.
- generate, exactly one of:
    {provider: "tripo"|"meshy"|"rodin", mode: "image"|"text", prompt?, options?}   (image mode uses the concept image)
    {procedural: "build_karambit.py", config: {blade_sweep_deg, ring_minor_r, handle_length, ...}}
    {procedural: "build_lowpoly_creature.py", config: {preset: "wolf"|"boar"|"bear"|"deer"|"cat", target_tris: 600-1500, height_m}}
      (free faceted low-poly animal, no keys; pair with rig "quadruped" and cleanup false. Offer it whenever the
       user wants low-poly/stylized animals, has no API key, or wants zero cost.)
    {file: "<name of a model the user uploaded>"}
  Tripo options: {"face_limit": N, "quad": true, "texture": true|false}. Meshy: {"topology": "quad", "target_polycount": N}.
- cleanup: {target_tris, target_height_m (real-world metres), origin: "FEET"|"CENTER"|"KEEP", remove_floaters_below: 0.02}
    or false for procedural models. Budgets: hero character 12000-20000, creature 6000-10000, prop 500-3000,
    weapon 300-1500. Low-poly/stylized looks: roughly a third of those numbers.
- rig: {method}. humanoid -> "mixamo" (best free, one manual upload) or "meshy" (hands-off, Meshy key);
    four-legged animal -> "quadruped" with clip_prefix like "wolf_"; props/weapons -> "none".
    Birds, snakes, spiders and other body plans are NOT supported yet: say so and suggest a static prop or a quadruped approximation.
- animations: quadruped -> {method: "procedural"} (idle, walk, attack, death).
    mixamo -> {method: "clips_dir", expect: [...], rename: {"standing_idle": "idle", "walking": "walk"}}.
    none for props.
- export: {collision: null | "convex" | "trimesh"}. Props and pickups: "convex". Held weapons and characters: null.

PROVIDER CHOICE: prefer a provider whose key is available (see SERVER). If no key is available, use
{file: ...} and tell the user to generate the model in the Tripo/Meshy/Hunyuan3D web app, download the GLB
and upload it in the asset panel, or use a procedural script when one fits.

Set ready=true only when the manifest is complete and you have no open questions. Put the manifest as a
JSON string in manifest_json ("" when you have no manifest yet). When the user asks about a running or
stopped asset, explain its status from ASSET STATUS in plain words and what to do next.
`;

const SCHEMA = {
  type: Type.OBJECT,
  properties: {
    reply: { type: Type.STRING, description: "What to say to the user" },
    manifest_json: { type: Type.STRING, description: "Complete forge manifest as a JSON string, or empty" },
    ready: { type: Type.BOOLEAN, description: "True when the manifest can be forged now" },
  },
  required: ["reply", "manifest_json", "ready"],
  propertyOrdering: ["reply", "manifest_json", "ready"],
};

export async function askAssistant(opts: {
  apiKey: string; model: string; history: ChatTurn[]; health: Health | null;
  examples: Record<string, unknown>; current: string; selected: AssetDetail | null;
}): Promise<AssistantReply> {
  const ai = new GoogleGenAI({ apiKey: opts.apiKey });
  const context = [
    `SERVER: ${JSON.stringify(opts.health ?? "not connected")}`,
    `EXAMPLE MANIFESTS: ${JSON.stringify(opts.examples)}`,
    `MANIFEST IN THE EDITOR: ${opts.current || "(empty)"}`,
    opts.selected
      ? `ASSET STATUS (${opts.selected.name}): ${JSON.stringify({
          status: opts.selected.status, stages: opts.selected.stages,
          instructions: opts.selected.instructions, error: opts.selected.error,
        })}`
      : "ASSET STATUS: none selected",
  ].join("\n");
  const res = await ai.models.generateContent({
    model: opts.model,
    contents: opts.history.map((t) => ({ role: t.role, parts: [{ text: t.text }] })),
    config: {
      systemInstruction: RULES + "\n" + context,
      responseMimeType: "application/json",
      responseSchema: SCHEMA,
      temperature: 0.4,
    },
  });
  const data = JSON.parse(res.text ?? "{}");
  let manifest: Record<string, unknown> | null = null;
  if (data.manifest_json) {
    try { manifest = JSON.parse(data.manifest_json); } catch { manifest = null; }
  }
  return { reply: data.reply ?? "", manifest, ready: Boolean(data.ready && manifest) };
}

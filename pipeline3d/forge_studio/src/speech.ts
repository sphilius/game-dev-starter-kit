// Voice in (Web Speech API: Chrome, Edge, Android Chrome, Safari) and voice out (speechSynthesis).
// Free and on-device where the browser supports it; no extra API key.

type Recognition = {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: any) => void) | null; onend: (() => void) | null; onerror: ((e: any) => void) | null;
  start(): void; stop(): void;
};

export function speechInputSupported(): boolean {
  const w = window as any;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function startDictation(onText: (text: string, final: boolean) => void, onEnd: () => void, onError: (msg: string) => void) {
  const w = window as any;
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!Ctor) {
    onError("This browser has no speech recognition. Try Chrome or Edge.");
    return () => {};
  }
  const rec: Recognition = new Ctor();
  rec.lang = navigator.language || "en-US";
  rec.interimResults = true;
  rec.continuous = true;
  let finalText = "";
  rec.onresult = (e: any) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalText += r[0].transcript + " ";
      else interim += r[0].transcript;
    }
    onText((finalText + interim).trim(), false);
  };
  rec.onerror = (e: any) => onError(e?.error === "not-allowed" ? "Microphone permission was denied." : `Speech error: ${e?.error}`);
  rec.onend = () => { onText(finalText.trim(), true); onEnd(); };
  rec.start();
  return () => rec.stop();
}

export function speak(text: string) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  window.speechSynthesis.speak(u);
}

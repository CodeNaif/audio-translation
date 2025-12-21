import { useEffect, useRef, useState } from "react";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:9100";

type LoadingState = "process" | "recording" | null;

function App() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [targetLang, setTargetLang] = useState("Arabic");
  const [translation, setTranslation] = useState("");
  const [loading, setLoading] = useState<LoadingState>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<string>("");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => () => mediaRecorderRef.current?.stream.getTracks().forEach((t) => t.stop()), []);

  useEffect(() => {
    if (audioFile && loading === null) {
      setTranslation("");
      processAudio(audioFile);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetLang]);

  const processAudio = async (file: File | null = audioFile) => {
    if (!file) return setError("Record something first.");
    setError("");
    setTranslation("");
    setStatus("Translating...");
    setLoading("process");
    try {
      const form = new FormData();
      form.append("audio", file);
      const transcribeRes = await fetch(`${API_URL}/transcribe`, { method: "POST", body: form });
      const transcribeText = await transcribeRes.text();
      if (!transcribeRes.ok) throw new Error(transcribeText || `Transcribe ${transcribeRes.status}`);
      const { text } = JSON.parse(transcribeText);

      const translateForm = new FormData();
      translateForm.append("text", text || "");
      translateForm.append("target_language", targetLang);
      const translateRes = await fetch(`${API_URL}/translate`, { method: "POST", body: translateForm });
      if (!translateRes.ok) {
        const errText = await translateRes.text();
        throw new Error(errText || `Translate ${translateRes.status}`);
      }

      const reader = translateRes.body?.getReader();
      if (!reader) {
        const fallbackText = await translateRes.text();
        setTranslation(fallbackText || "");
        setStatus("");
        return;
      }

      const decoder = new TextDecoder();
      setTranslation("");
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value) {
          const chunk = decoder.decode(value, { stream: true });
          setTranslation((prev) => prev + chunk);
        }
      }
      setStatus("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(null);
      setStatus("");
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        const ext = mimeType.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const file = new File([blob], `recording.${ext}`, { type: mimeType });
        setAudioFile(file);
        processAudio(file);
      };
      recorder.start();
      setError("");
      setLoading("recording");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Mic error: ${msg}`);
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current?.stream.getTracks().forEach((t) => t.stop());
    setLoading(null);
  };

  const handleUpload = (file: File | null | undefined) => {
    if (!file) return;
    setError("");
    setTranslation("");
    setAudioFile(file);
    processAudio(file);
  };

  return (
    <div className="page full">
      <div className="content">
        <header className="bar">
          <div>
            <h1>Audio Translation</h1>
          </div>
        </header>

        <section className="panel glass">
          <div className="panel-head">
            <label className="upload-mini">
              <input
                type="file"
                accept="audio/*"
                onChange={(e) => {
                  handleUpload(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
              <span>Upload audio</span>
            </label>
          </div>

          <div className="record-area">
            <div className="record-wrap">
              <div className="record-circle">
                <button
                  className={`record-main ${loading === "recording" ? "active" : ""}`}
                  onClick={loading === "recording" ? stopRecording : startRecording}
                  aria-label={loading === "recording" ? "Stop recording" : "Start recording"}
                >
                  {loading === "recording" ? "Stop" : "Record"}
                </button>
                {loading === "recording" && <div className="pulse pulse1" />}
                {loading === "recording" && <div className="pulse pulse2" />}
              </div>
              <div className="record-hint">
                {loading === "recording" ? "Recording... tap to stop" : "Tap to record and auto-translate"}
              </div>
            </div>

            <div className="lang-select">
              <label className="field">
                <span>Target language</span>
                <select value={targetLang} onChange={(e) => setTargetLang(e.target.value)}>
                  <option value="English">English</option>
                  <option value="Arabic">Arabic</option>
                </select>
              </label>
            </div>
          </div>

          {translation && (
            <div className="translation-box show">
              <div className="translation-label">Translation</div>
              <div className="translation-content">{translation}</div>
            </div>
          )}

          {error && <p className="error">{error}</p>}
          {status && <p className="status-note">{status}</p>}
        </section>
      </div>
    </div>
  );
}

export default App;

import { useEffect, useRef, useState } from "react";
import "./App.css";

const fallbackHost = typeof window !== "undefined" ? window.location.hostname : "localhost";
const fallbackProtocol = typeof window !== "undefined" ? window.location.protocol : "http:";
const API_URL = import.meta.env.VITE_API_URL || `${fallbackProtocol}//${fallbackHost}:9100`;

type LoadingState = "process" | "recording" | null;

const buildWsUrl = (baseUrl: string) => {
  try {
    const url = new URL(baseUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/ws/stream";
    return url.toString();
  } catch {
    return "ws://localhost:9100/ws/stream";
  }
};

const floatTo16BitPCM = (input: Float32Array) => {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
};

const encodeBase64 = (input: Int16Array) => {
  const bytes = new Uint8Array(input.buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
};

function App() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [targetLang, setTargetLang] = useState("Arabic");
  const [transcript, setTranscript] = useState("");
  const [translation, setTranslation] = useState("");
  const [loading, setLoading] = useState<LoadingState>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<string>("");
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
      audioContextRef.current?.close();
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

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
    setTranscript("");
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
      setError("");
      setStatus("Connecting...");
      setTranscript("");
      setTranslation("");
      setAudioFile(null);
      setLoading("recording");
      const wsUrl = buildWsUrl(API_URL);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "transcript_delta") {
            setTranscript((prev) => prev + payload.text);
          } else if (payload.type === "translation_delta") {
            setTranslation((prev) => prev + payload.text);
          } else if (payload.type === "status") {
            setStatus(payload.message || "");
          } else if (payload.type === "error") {
            setError(payload.message || "Streaming error.");
          }
        } catch (err) {
          console.error("Bad message", err);
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection failed.");
        stopRecording();
      };

      ws.onclose = () => {
        stopRecording();
      };

      ws.onopen = async () => {
        try {
          ws.send(JSON.stringify({ type: "start", target_language: targetLang }));
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          mediaStreamRef.current = stream;
          const audioContext = new AudioContext({ sampleRate: 16000 });
          audioContextRef.current = audioContext;
          if (audioContext.sampleRate !== 16000) {
            setStatus(`Using ${audioContext.sampleRate}Hz input (expected 16000Hz).`);
          } else {
            setStatus("Listening...");
          }
          const source = audioContext.createMediaStreamSource(stream);
          sourceRef.current = source;
          const processor = audioContext.createScriptProcessor(4096, 1, 1);
          processorRef.current = processor;
          processor.onaudioprocess = (event) => {
            if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
            const input = event.inputBuffer.getChannelData(0);
            const pcm16 = floatTo16BitPCM(input);
            const base64 = encodeBase64(pcm16);
            wsRef.current.send(JSON.stringify({ type: "audio", data: base64 }));
          };
          source.connect(processor);
          processor.connect(audioContext.destination);
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(`Mic error: ${msg}`);
          stopRecording();
        }
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Mic error: ${msg}`);
      stopRecording();
    }
  };

  const stopRecording = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "stop" }));
    }
    wsRef.current?.close();
    wsRef.current = null;
    processorRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    audioContextRef.current?.close();
    audioContextRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    setLoading(null);
    setStatus("");
  };

  const handleUpload = (file: File | null | undefined) => {
    if (!file) return;
    setError("");
    setTranscript("");
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
                {loading === "recording" ? "Recording... tap to stop" : "Tap to record and stream translation"}
              </div>
            </div>

            <div className="lang-select">
              <label className="field">
                <span>Target language</span>
                <select
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                  disabled={loading === "recording"}
                >
                  <option value="English">English</option>
                  <option value="Arabic">Arabic</option>
                </select>
              </label>
            </div>
          </div>

          {transcript && (
            <div className="translation-box show">
              <div className="translation-label">Transcript</div>
              <div className="translation-content">{transcript}</div>
            </div>
          )}

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

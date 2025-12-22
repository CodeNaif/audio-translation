# Audio Translation UI

Vite + React frontend for the audio translation service.

## Setup
1. Install dependencies:
   ```bash
   npm install
   ```
2. Configure the backend URL (optional):
   ```bash
   export VITE_API_URL="http://localhost:9100"
   ```
3. Start the dev server:
   ```bash
   npm run dev
   ```

Recording uses the backend WebSocket at `/ws/stream`, so make sure the backend points to a realtime transcription server (local or OpenAI).

## Build
```bash
npm run build
```

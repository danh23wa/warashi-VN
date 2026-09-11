# Warashi Desktop

Electron shell for running Warashi as a transparent, always-on-top desktop companion.

## Run

From the repository root:

```bash
cd desktop
npm install
npm start
```

The shell starts the existing Python backend when port `12393` is unavailable, waits for it to become ready, then loads the existing Live2D frontend in a frameless transparent window.

Gemini, MCP, memory, audio, and Live2D remain owned by the existing Warashi backend. This folder only owns the desktop window behavior.

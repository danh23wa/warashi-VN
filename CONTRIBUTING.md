# Contributing to Warashi

Thanks for being here. Warashi is a small project and every PR genuinely moves it.

**Read this file, not upstream's.** Warashi is built on [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber), but it has different goals, a different audience, and its own scope. Contributions go here, and issues about Warashi belong in this repo.

---

## The fastest way in

Warashi has five pluggable subsystems, and they all use the same shape: **one new file + one branch in a factory**. If you have never touched this codebase, start here — you can ship a working PR in an afternoon.

| Subsystem | Where implementations live | Factory to register in |
|---|---|---|
| Speech recognition (ASR) | `src/open_llm_vtuber/asr/` | `asr/asr_factory.py` |
| Text to speech (TTS) | `src/open_llm_vtuber/tts/` | `tts/tts_factory.py` |
| Translation | `src/open_llm_vtuber/translate/` | `translate/translate_factory.py` |
| Voice activity detection | `src/open_llm_vtuber/vad/` | `vad/vad_factory.py` |
| LLM backends | `src/open_llm_vtuber/agent/` | `agent/stateless_llm_factory.py` |

There are already 20 TTS engines and 8 ASR engines in the tree. **Pick the one closest to what you want to add and copy its shape.** That is the intended way to work here, not a shortcut.

### Recipe: add a speech recognition engine

1. Create `src/open_llm_vtuber/asr/<yourengine>_asr.py`.
2. Define a class named `VoiceRecognition` that subclasses `ASRInterface` (from `.asr_interface`).
3. Implement the one abstract method:
   ```python
   def transcribe_np(self, audio: np.ndarray) -> str:
   ```
   Audio arrives as float32, mono, 16 kHz (`SAMPLE_RATE`, `NUM_CHANNELS`, `SAMPLE_WIDTH` on the interface). Return plain text.
   If your engine has a real async API, also override `async_transcribe_np`; otherwise the base class runs your sync method in a thread for you.
4. Register it in `asr/asr_factory.py` — add an `elif system_name == "<yourengine>":` branch. **Import inside the branch, not at the top of the file.** Every engine is lazily imported so that a missing optional dependency cannot stop the app from starting.
5. Add the config block to `config_templates/` so the setup wizard can offer it.

### Recipe: add a TTS engine or a translation provider

Same shape. `tts/tts_interface.py` and `translate/translate_interface.py` define what you must implement, and the existing files next to yours show a working example each.

---

## Rules that are not negotiable

These come from bugs that already shipped and hurt real users. They are short, so please read them.

**1. An optional component failing must never stop the app from starting.**

A previous release set the ASR engine to one that was not bundled. The import failed, startup called `sys.exit(1)`, and the app simply would not open — for users who had never touched that setting. Anything optional goes in a `try/except` with a fallback, and the app opens with that feature disabled rather than not opening at all.

**2. "We bundle X" does not mean every tool from X is present.**

Warashi bundles ffmpeg. It does not bundle `ffprobe`. A library that quietly called `ffprobe` to inspect audio meant Windows users got no sound at all, with no error anyone could see. If you depend on an external binary, check it exists and degrade gracefully when it does not.

**3. Changing a backend option means changing the frontend too.**

The frontend bundle has hardcoded preset lists. Adding a value to a backend allow-list without rebuilding the frontend produces a dropdown that cannot select the thing you just added. Either rebuild the frontend in the same PR, or keep the backend tolerant of the old values.

**4. Never break someone's existing `conf.yaml`.**

Users edit this file by hand. New options need defaults that preserve current behaviour. If you must migrate, handle the old shape too.

---

## Scope: what will be turned down

Please check this before building something large. Turning down a finished PR is the worst outcome for everyone, and these are settled decisions rather than open questions.

- **No mobile version.** Desktop only, macOS and Windows.
- **No paid tier, no paywall, no telemetry.** Free and open source, optional donations.
- **No model marketplace, no bundled copyrighted characters.** This avoids the Live2D commercial-licensing trap. Warashi ships neutral free defaults; users bring their own character, voice, and LLM.

Anything that makes the "download → double-click → chat" path harder for a non-technical user is also likely to be turned down, even if it is technically better. That path is the entire point of this fork.

If you are unsure whether something is in scope, **open an issue before you write the code**. A one-paragraph question costs you five minutes; a rejected PR costs you a weekend.

---

## Sending a PR

1. Fork, branch off `main`.
2. Keep it to one thing. A PR that adds a TTS engine and also refactors the config loader will sit unreviewed for a long time.
3. Run the linter — CI runs `ruff`, so `ruff check .` locally saves a round trip.
4. Say in the description **what you actually tested on**. "Tested on macOS 15, Apple Silicon, with the bundled sherpa ASR" is worth more than a paragraph of prose. Platform-specific bugs are the most common kind here.
5. If your change touches audio, say whether you tested on Windows. Most audio bugs in this project have been Windows-only.

Small PRs get merged. Nothing here needs to be perfect on the first push.

---

## Reporting a bug

Use the issue templates. The two things that matter most:

- **Your platform and how you installed** (release zip, or from source).
- **The backend log.** Most reports are unactionable without it.

Please strip API keys out of any config or log you paste.

---

## Questions

If something in this file is wrong or unclear, that is a bug too — open an issue. Documentation PRs are as welcome as code.

---
name: ai-music
description: "AI music generation, songwriting craft, Suno prompting, HeartMuLa setup, and audio visualization — one umbrella for creating and analyzing music with AI."
tags: [music, audio, generation, songwriting, suno, heartmula, spectrogram, lyrics, ai-music, creative]
related_skills: [songwriting-and-ai-music, heartmula, songsee]
---

# AI Music — Generation, Songwriting & Audio Analysis

This umbrella skill covers the full spectrum of AI-assisted music creation and audio analysis. Three main domains:

---

## 1. Songwriting Craft & Suno Prompts

*(Absorbed from `songwriting-and-ai-music`)*

### Song Structure

Common skeletons — mix, modify, or throw out:
- **ABABCB** — Verse/Chorus/Verse/Chorus/Bridge/Chorus (pop/rock)
- **AABA** — Verse/Verse/Bridge/Verse (jazz standards, ballads)
- **ABAB** — Verse/Chorus alternating (simple, direct)
- **AAA** — Verse/Verse/Verse (folk, storytelling)

Building blocks: Intro, Verse, Pre-Chorus, Chorus, Bridge, Outro.

### Rhyme & Meter

Rhyme types (tight to loose): Perfect → Family → Assonance → Consonance → Near/slant.
Mix them. All perfect rhymes = nursery rhyme. All slant = lazy.

**Internal rhyme:** Rhyming within a line, not just at ends.
**Meter:** Stressed syllables matter more than total count. Say it out loud.

### Emotional Arc

Energy map: Intro 2-3 → Verse 5-6 → Pre-Chorus 7 → Chorus 8-9 → Bridge varies → Final Chorus 9-10.

**Contrast is king:** Whisper before a scream. Sparse before dense. Low before high.

### Lyric Craft

- **Show, don't tell:** "Your hoodie's still on the hook by the door" > "I was sad"
- **The hook:** Title or core phrase, placed where it lands hardest
- **Prosody:** Stable feelings + settled melodies + perfect rhymes. Unstable feelings + wandering melodies + near-rhymes.

### Suno AI Prompt Engineering

**Style formula:** Genre + Mood + Era + Instruments + Vocal Style + Production + Dynamics

```
BAD:  "sad rock song"
GOOD: "Cinematic orchestral spy thriller, 1960s Cold War era, smoky
       sultry female vocalist, big band jazz, brass section with
       trumpets and french horns, sweeping strings, minor key,
       vintage analog warmth"
```

**Describe the journey, not just the genre:**
```
"Begins as a haunting whisper over sparse piano. Gradually layers
 in muted brass. Builds through the chorus with full orchestra.
 Outro strips back to a lone piano and a fragile whisper fading to silence."
```

**Metatags** (place in [brackets] inside lyrics):
- Structure: `[Verse]` `[Chorus]` `[Bridge]` `[Outro]`
- Vocal: `[Whispered]` `[Belted]` `[Falsetto]` `[Soulful]` `[Raspy]`
- Dynamics: `[High Energy]` `[Building Energy]` `[Emotional Climax]`

**Phonetic tricks:** Spell words as they sound ("through" → "thru"), ALL CAPS = louder, hyphens guide syllables ("lo-o-o-ove").

### Parody & Adaptation

1. Map the original structure (syllables, rhyme scheme, stress positions)
2. Match stressed syllables to same beats
3. On long held notes, match the vowel sound
4. Monosyllabic swaps keep rhythm intact

---

## 2. HeartMuLa — Open-Source Music Generation

*(Absorbed from `heartmula`)*

HeartMuLa is a family of Apache-2.0 music foundation models that generates songs from lyrics + tags. Includes HeartCodec (12.5Hz codec), HeartTranscriptor (lyrics transcription), HeartCLAP (audio-text alignment).

### Hardware

- Minimum: 8GB VRAM with `--lazy_load true`
- Recommended: 16GB+ VRAM
- Multi-GPU: `--mula_device cuda:0 --codec_device cuda:1`

### Installation

```bash
git clone https://github.com/HeartMuLa/heartlib.git
cd heartlib
uv venv --python 3.10 .venv
. .venv/bin/activate
uv pip install -e .
uv pip install --upgrade datasets transformers
```

### Required Patches (for transformers 5.x)

**Patch 1 — RoPE cache fix** in `src/heartlib/heartmula/modeling_heartmula.py`:
Add RoPE reinitialization after `reset_caches` block:
```python
from torchtune.models.llama3_1._position_embeddings import Llama3ScaledRoPE
for module in self.modules():
    if isinstance(module, Llama3ScaledRoPE) and not module.is_cache_built:
        module.rope_init()
        module.to(device)
```

**Patch 2 — HeartCodec loading fix** in `src/heartlib/pipelines/music_generation.py`:
Add `ignore_mismatched_sizes=True` to ALL `HeartCodec.from_pretrained()` calls.

### Model Download

```bash
cd heartlib
hf download --local-dir './ckpt' 'HeartMuLa/HeartMuLaGen'
hf download --local-dir './ckpt/HeartMuLa-oss-3B' 'HeartMuLa/HeartMuLa-oss-3B-happy-new-year'
hf download --local-dir './ckpt/HeartCodec-oss' 'HeartMuLa/HeartCodec-oss-20260123'
```

### Generation

```bash
cd heartlib && . .venv/bin/activate
python ./examples/run_music_generation.py \
  --model_path=./ckpt --version="3B" \
  --lyrics="./assets/lyrics.txt" --tags="./assets/tags.txt" \
  --save_path="./assets/output.mp3" --lazy_load true
```

**Key params:** `--max_audio_length_ms` (240000), `--topk` (50), `--temperature` (1.0), `--cfg_scale` (1.5).

### Pitfalls
1. Do NOT use bf16 for HeartCodec — use fp32
2. Tags may be ignored by the model; lyrics dominate
3. RTF ≈ 1.0 (4-min song takes ~4 min to generate)
4. Linux/CUDA only for GPU acceleration (no macOS Triton)

---

## 3. Audio Spectrograms & Visualization (songsee)

*(Absorbed from `songsee`)*

Generate spectrograms and multi-panel audio feature visualizations from audio files using the `songsee` CLI.

### Prerequisites

```bash
go install github.com/steipete/songsee/cmd/songsee@latest
```

Optional: `ffmpeg` for formats beyond WAV/MP3.

### Quick Start

```bash
# Basic spectrogram
songsee track.mp3

# Multi-panel visualization grid
songsee track.mp3 --viz spectrogram,mel,chroma,hpss,selfsim,loudness,tempogram,mfcc,flux

# Time slice (start at 12.5s, 8s duration)
songsee track.mp3 --start 12.5 --duration 8 -o slice.jpg
```

### Visualization Types

| Type | Description |
|------|-------------|
| `spectrogram` | Standard frequency spectrogram |
| `mel` | Mel-scaled spectrogram |
| `chroma` | Pitch class distribution |
| `hpss` | Harmonic/percussive separation |
| `selfsim` | Self-similarity matrix |
| `loudness` | Loudness over time |
| `tempogram` | Tempo estimation |
| `mfcc` | Mel-frequency cepstral coefficients |
| `flux` | Spectral flux (onset detection) |

### Key Flags

| Flag | Description |
|------|-------------|
| `--viz` | Visualization types (comma-separated) |
| `--style` | Color palette: `classic`, `magma`, `inferno`, `viridis`, `gray` |
| `--width` / `--height` | Output image dimensions |
| `--window` / `--hop` | FFT window and hop size |
| `--start` / `--duration` | Time slice |
| `--format` | Output format: `jpg` or `png` |

### Notes
- WAV and MP3 decoded natively; other formats need ffmpeg
- Output images can be inspected with `vision_analyze`

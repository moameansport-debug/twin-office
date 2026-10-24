"""Generate original background beats (no copyrighted music) for the reels.

python template/music.py   -> writes template/assets/music/beat1.m4a .. beat3.m4a
"""
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent / "assets" / "music"

# (name, bpm, root midi note, chord degrees as semitone offsets from root)
TRACKS = [
    ("beat1", 120, 57, [(0, 3, 7), (-4, 0, 3), (-9, -5, -2), (-2, 2, 5)]),   # Am F C G
    ("beat2", 128, 61, [(0, 3, 7), (-2, 2, 5), (-4, 0, 3), (-5, -1, 2)]),    # C#m B A G#
    ("beat3", 110, 53, [(0, 3, 7), (-4, 0, 3), (-7, -3, 0), (-5, -2, 2)]),   # Fm Db Bbm C
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def saw(f, n, detune=0.0):
    t = np.arange(n) / SR
    return sum(2 * ((t * f * (1 + d)) % 1) - 1 for d in (-detune, 0, detune)) / 3


def add(buf, start, sig):
    end = min(len(buf), start + len(sig))
    if start < end:
        buf[start:end] += sig[: end - start]


def make(name, bpm, root, chords, seconds=24):
    n = int(SR * seconds)
    beat = 60 / bpm
    L, R = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(len(name) + bpm)
    bars = int(seconds / (beat * 4)) + 1

    kick_n = int(.35 * SR)
    t = np.arange(kick_n) / SR
    kick = np.sin(2 * np.pi * (45 * t + 90 * (1 - np.exp(-t * 30)) / 30)) * np.exp(-t * 9)
    snare_n = int(.25 * SR)
    snare = (rng.uniform(-1, 1, snare_n) * .7 + np.sin(2 * np.pi * 190 * np.arange(snare_n) / SR) * .3) * env(snare_n, .001, .07)
    hat_n = int(.06 * SR)
    hat = np.diff(rng.uniform(-1, 1, hat_n + 1)) * env(hat_n, .001, .015)

    for bar in range(bars):
        chord = chords[bar % len(chords)]
        b0 = bar * 4 * beat
        # pad
        pad_n = int(4 * beat * SR)
        pad = sum(saw(hz(root + 12 + s), pad_n, .004) for s in chord) / 3
        pad = lowpass(pad, 900 + 500 * np.sin(bar)) * env(pad_n, .4, 6) * .22
        add(L, int(b0 * SR), pad * .9); add(R, int(b0 * SR), pad)
        for step in range(16):
            ts = int((b0 + step * beat / 4) * SR)
            if step in (0, 6, 10) or (bar % 2 and step == 14):
                add(L, ts, kick * .9); add(R, ts, kick * .9)
            if step in (4, 12):
                add(L, ts, snare * .45); add(R, ts, snare * .45)
            if step % 2 == 0 or rng.random() < .3:
                pan = .5 + .3 * np.sin(step)
                add(L, ts, hat * .18 * (1 - pan)); add(R, ts, hat * .18 * pan)
            # sub bass on the kick pattern
            if step in (0, 6, 10):
                bn = int(beat * .9 * SR)
                bass = np.sin(2 * np.pi * hz(root - 12 + chord[0]) * np.arange(bn) / SR) * env(bn, .005, .5) * .5
                add(L, ts, bass); add(R, ts, bass)
            # pluck arpeggio
            note = root + 24 + chord[[0, 1, 2, 1][step % 4]] + (12 if step % 8 == 7 else 0)
            pn = int(beat / 4 * 1.6 * SR)
            pl = lowpass(saw(hz(note), pn, .002), 2600) * env(pn, .002, .12) * .16
            add(L, ts, pl * (.7 if step % 2 else 1)); add(R, ts, pl * (1 if step % 2 else .7))

    mix = np.stack([L, R], 1)
    mix /= np.max(np.abs(mix)) * 1.12
    mix = np.tanh(mix * 1.3) / np.tanh(1.3)
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32000).astype("<i2").tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(OUT / f"{name}.wav"), "-c:a", "aac", "-b:a", "160k",
                    str(OUT / f"{name}.m4a")], check=True)
    (OUT / f"{name}.wav").unlink()


if __name__ == "__main__":
    for track in TRACKS:
        make(*track)
        print("wrote", track[0])

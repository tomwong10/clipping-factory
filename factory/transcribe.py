"""Speech to text with word timings, using faster-whisper on the CPU."""
from pathlib import Path

from .log import log

_model = None
_model_name = None


def _get_model(name: str):
    global _model, _model_name
    if _model is None or _model_name != name:
        from faster_whisper import WhisperModel
        log.info("Loading Whisper model '%s' (first time downloads it)", name)
        _model = WhisperModel(name, device="cpu", compute_type="int8")
        _model_name = name
    return _model


def transcribe(path: Path, model_name: str = "small", language: str = "en") -> list:
    """Returns a list of segments: {start, end, text, words: [{start, end, word}]}."""
    model = _get_model(model_name)
    log.info("Transcribing %s", path.name)
    segments, _info = model.transcribe(
        str(path),
        language=language or None,
        word_timestamps=True,
        vad_filter=True,
    )
    out = []
    for s in segments:
        words = [
            {"start": float(w.start), "end": float(w.end), "word": w.word.strip()}
            for w in (s.words or [])
            if w.word and w.word.strip()
        ]
        out.append({"start": float(s.start), "end": float(s.end), "text": s.text.strip(), "words": words})
    log.info("Transcribed %d segments", len(out))
    return out

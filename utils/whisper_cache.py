"""
Wrapper para faster-whisper com cache de modelo e int8 por padrão.
Retorna segmentos no mesmo formato de dict que o openai-whisper usa, para
manter compatibilidade com o resto do código.
"""
import os
from faster_whisper import WhisperModel

_cache: dict = {}

DEVICE = "cpu"  # força CPU


def _compute_type():
    # lê a cada chamada para pegar mudanças via settings sem reiniciar
    return os.environ.get("WHISPER_COMPUTE_TYPE", "int8")


def get_model(model_name: str):
    """Retorna WhisperModel cacheado por (nome, compute_type). Sempre CPU."""
    ct = _compute_type()
    key = (model_name, ct)
    if key not in _cache:
        try:
            print(f"[Whisper] Carregando '{model_name}' (cpu, {ct})...")
            _cache[key] = WhisperModel(model_name, device=DEVICE, compute_type=ct)
        except ValueError as e:
            if ct != "int8":
                print(f"[Whisper] {ct} não suportado ({e}). Fallback int8.")
                _cache[key] = WhisperModel(model_name, device=DEVICE, compute_type="int8")
            else:
                raise
    else:
        print(f"[Whisper] Reusando '{model_name}' (cpu, {ct}) do cache.")
    return _cache[key]


def transcribe(video_path: str, model_name: str = "small", language: str = "pt",
               word_timestamps: bool = True, verbose: bool = False) -> list[dict]:
    """
    Transcreve e retorna segmentos no formato:
    [{"start": float, "end": float, "text": str, "no_speech_prob": float,
      "words": [{"start": float, "end": float, "word": str, "probability": float}, ...]}, ...]
    """
    model = get_model(model_name)
    segments_gen, info = model.transcribe(
        video_path,
        language=language,
        word_timestamps=word_timestamps,
        vad_filter=False,
    )

    segments = []
    for seg in segments_gen:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "start": w.start,
                    "end": w.end,
                    "word": w.word,
                    "probability": w.probability,
                })
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "no_speech_prob": getattr(seg, "no_speech_prob", 0.0),
            "words": words,
        })
        if verbose:
            print(f"[{seg.start:.2f}-{seg.end:.2f}] {seg.text}")
    return segments


def clear_cache():
    _cache.clear()

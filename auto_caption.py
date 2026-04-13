#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
import re

import pysubs2

from utils.whisper_cache import transcribe as _transcribe
from correction import corrigir_palavras


def transcrever(video_path: str, model_name: str = "small", language: str = "pt"):
    print(f"[1/3] Transcrevendo {video_path} com Whisper ({model_name})...")
    return _transcribe(video_path, model_name=model_name, language=language,
                       word_timestamps=True, verbose=True)


def gerar_ass_capcut(segments, ass_path: str):
    """
    Gera um arquivo .ass com legendas dinâmicas:
    - Fonte: Prohibition (ou Montserrat/Arial fallback)
    - Tamanho: 12 (solicitado pelo usuário)
    - Estilo: Máximo 3-4 palavras por linha. Palavra atual em VERMELHO.
    """
    print(f"[3/3] Gerando arquivo de legenda ASS em {ass_path}...")

    subs = pysubs2.SSAFile()

    # Estilo Base (Branco com borda preta para contraste)
    style = pysubs2.SSAStyle()
    style.fontname = "Prohibition"  # Fonte solicitada
    style.fontsize = 10             # Tamanho reduzido
    style.bold = True
    style.primarycolor = pysubs2.Color(255, 255, 255)  # Branco
    style.outlinecolor = pysubs2.Color(0, 0, 0)        # Borda preta
    style.outline = 1.0
    style.shadow = 0
    style.alignment = 2   # centro inferior
    # O sistema de legendas usa uma altura virtual de 288 pixels por padrão.
    # 30 era baixo. 350 joga para fora da tela.
    # Para o Instagram (limpar UI), usamos ~30-35% da altura (aprox 85-95).
    style.marginv = 95

    subs.styles["Default"] = style

    def sec_to_ms(t):
        return int(t * 1000)

    # CORES E ESTILOS (Ajuste Fino)
    # Laranja Avermelhado (estilo CapCut): RGB(255, 69, 0) -> BGR(&H0045FF&)
    HIGHLIGHT_COLOR = "&H0045FF&" 
    BLACK_COLOR = "&H000000&"
    WHITE_COLOR = "&HFFFFFF&"
    
    BORDER_NORMAL = 1.5
    # Borda reduzida para 5.0 (antes 8.0) para ficar mais ajustada
    BORDER_HIGHLIGHT = 5.0
    BLUR_HIGHLIGHT = 2.0
    
    # Tag Destaque: 
    # \bord8 \blur3 -> Cria um "borrão" sólido laranja atrás da letra, simulando a caixa (pill)
    HIGHLIGHT_TAG = rf"{{\1c{WHITE_COLOR}}}{{\3c{HIGHLIGHT_COLOR}}}{{\bord{BORDER_HIGHLIGHT}}}{{\blur{BLUR_HIGHLIGHT}}}"
    
    # Tag Normal:
    NORMAL_TAG = rf"{{\1c{WHITE_COLOR}}}{{\3c{BLACK_COLOR}}}{{\bord{BORDER_NORMAL}}}{{\blur0}}"

    # 1. Achatar todas as palavras de todos os segmentos
    all_words = []
    for seg in segments:
        seg_words = seg.get("words", [])
        if seg_words:
            all_words.extend(seg_words)
        else:
            # Fallback se não houver palavras
            all_words.append({
                "word": seg["text"],
                "start": seg["start"],
                "end": seg["end"]
            })

    if not all_words:
        print("Nenhuma palavra encontrada na transcrição.")
        return

    # 2. Processar em blocos de N palavras
    MAX_WORDS_PER_LINE = 4
    
    # Iterar em chunks
    for i in range(0, len(all_words), MAX_WORDS_PER_LINE):
        chunk = all_words[i : i + MAX_WORDS_PER_LINE]
        
        if not chunk:
            continue

        # Texto base do chunk (tudo maiúsculo e limpo)
        chunk_texts = [w["word"].strip().upper() for w in chunk]
        
        # Para cada palavra NO chunk, geramos eventos de destaque
        for j, word_obj in enumerate(chunk):
            w_start = sec_to_ms(word_obj["start"])
            w_end = sec_to_ms(word_obj["end"])
            
            # Monta o texto visual
            display_parts = []
            for k, text_part in enumerate(chunk_texts):
                if k == j:
                    display_parts.append(f"{HIGHLIGHT_TAG}{text_part}{NORMAL_TAG}")
                else:
                    display_parts.append(text_part)
            
            final_text = " ".join(display_parts)

            # Ajuste fino de tempo
            abs_idx = i + j
            if abs_idx < len(all_words) - 1:
                next_start = sec_to_ms(all_words[abs_idx + 1]["start"])
                if next_start - w_end < 500: # Tolerância de silêncio
                    w_end = next_start

            event = pysubs2.SSAEvent(start=w_start, end=w_end, text=final_text, style="Default")
            subs.events.append(event)

    subs.save(ass_path)
    print("Legenda .ass criada.")


def queimar_legenda(video_path: str, ass_path: str, output_path: str):
    print(f"Renderizando vídeo final com ffmpeg → {output_path}")

    ass_norm = os.path.abspath(ass_path).replace("\\", "/")
    
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"subtitles='{ass_norm}'",
        "-c:a", "copy",
        output_path,
    ]

    print("Comando:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "").strip().splitlines()[-10:]
        raise RuntimeError("Erro ffmpeg ao queimar legenda:\n" + "\n".join(stderr_tail)) from e

def processar_legenda_completo(video_path, output_path, model_name="small", language="pt", gemini_key=None):
    """
    Pipeline completo: Transcrever -> (Corrigir IA) -> Gerar ASS -> Queimar
    """
    base, ext = os.path.splitext(video_path)
    ass_path = f"{base}.ass"

    # 1. Transcrever
    segments = transcrever(video_path, model_name=model_name, language=language)
    
    # 2. Corrigir com IA se o LLM estiver configurado
    from llm import is_configured as _llm_ok
    if gemini_key or _llm_ok():
        print("\n[Auto Caption] Aplicando correção com IA...")
        all_words = []
        for seg in segments:
            if "words" in seg:
                all_words.extend(seg["words"])

        if all_words:
            try:
                corrected_words = corrigir_palavras(all_words, gemini_key)
                if corrected_words:
                    segments = [{
                        "start": corrected_words[0]["start"],
                        "end": corrected_words[-1]["end"],
                        "text": " ".join([w["word"] for w in corrected_words]),
                        "words": corrected_words,
                    }]
            except Exception as e:
                print(f"❌ Falha na correção IA: {e}. Usando original.")

    # 3. Gerar ASS
    gerar_ass_capcut(segments, ass_path)
    
    # 4. Queimar
    queimar_legenda(video_path, ass_path, output_path)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Gera legenda estilo CapCut automaticamente com Whisper e queima no vídeo."
    )
    parser.add_argument("video", help="Caminho do arquivo de vídeo de entrada")
    parser.add_argument(
        "--model",
        default="small",
        help="Modelo Whisper (tiny, base, small, medium, large). Padrão: small",
    )
    parser.add_argument(
        "--language",
        default="pt",
        help="Código do idioma da fala (ex: pt, en, es). Padrão: pt",
    )
    parser.add_argument(
        "--output",
        help="Nome do vídeo de saída (opcional). Se não passar, cria <nome>_legendado.mp4",
    )
    parser.add_argument(
        "--gemini-key",
        help="API Key do Google Gemini para correção de texto.",
    )

    args = parser.parse_args()

    video_path = args.video
    if not os.path.isfile(video_path):
        print(f"Arquivo não encontrado: {video_path}")
        sys.exit(1)

    base, ext = os.path.splitext(video_path)
    output_path = args.output or f"{base}_legendado.mp4"

    processar_legenda_completo(
        video_path, 
        output_path, 
        model_name=args.model, 
        language=args.language,
        gemini_key=args.gemini_key
    )

    print("\n✅ Pronto!")
    print(f"Vídeo legendado salvo em: {output_path}")


if __name__ == "__main__":
    main()

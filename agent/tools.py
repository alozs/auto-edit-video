# This file patches whisper to avoid importing numba if it's missing.
# Numba is used for JIT compilation, but whisper works without it (just slower).
import sys
import types
import traceback
import json
import subprocess

if 'numba' not in sys.modules:
    try:
        import numba
    except ImportError:
        # Create a mock numba module
        numba = types.ModuleType('numba')
        
        # Mock jit decorator
        def jit(*args, **kwargs):
            def decorator(func):
                return func
            return decorator
            
        numba.jit = jit
        sys.modules['numba'] = numba

# Now we can import the rest of the tools
try:
    from remove_silence import remover_silencio
    from auto_caption import processar_legenda_completo, transcrever
except ImportError:
    # Fallback to sys.path hack if running from agent subdir
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        
    try:
        from remove_silence import remover_silencio
        from auto_caption import processar_legenda_completo, transcrever
    except ImportError as e:
        print(f"CRITICAL ERROR importing video scripts: {e}")
        traceback.print_exc()

from llm import generate as llm_generate, is_configured as llm_is_configured

def list_videos():
    import glob
    import os
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    extensoes = ['*.mp4', '*.MP4', '*.mov', '*.MOV', '*.mkv', '*.MKV', '*.avi']
    arquivos = []
    
    old_cwd = os.getcwd()
    try:
        os.chdir(parent_dir)
        for ext in extensoes:
            arquivos.extend(glob.glob(ext))
    finally:
        os.chdir(old_cwd)
        
    return sorted(list(set(arquivos)))

def remove_silence_tool(video_path: str, method: str = "speech") -> str:
    import os
    
    if os.path.isabs(video_path):
        full_path = video_path
    else:
        full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), video_path)
    
    if not os.path.exists(full_path):
        return f"Erro: Arquivo não encontrado: {full_path}"
    
    base, ext = os.path.splitext(full_path)
    output_path = f"{base}_cut{ext}"
    
    try:
        success = remover_silencio(full_path, output_path, method=method)
        if success:
            return f"Sucesso! Vídeo cortado salvo em: {os.path.basename(output_path)}"
        else:
            return "Erro: Não foi possível remover o silêncio."
    except Exception as e:
        return f"Erro técnico ao remover silêncio: {str(e)}"

def add_subtitles_tool(video_path: str, model: str = "small") -> str:
    import os
    
    if os.path.isabs(video_path):
        full_path = video_path
    else:
        full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), video_path)

    if not os.path.exists(full_path):
        return f"Erro: Arquivo não encontrado: {video_path}"
        
    base, ext = os.path.splitext(full_path)
    output_path = f"{base}_legendado{ext}"
    
    try:
        gemini_key = os.environ.get("GEMINI_API_KEY")

        final_path = processar_legenda_completo(
            full_path,
            output_path,
            model_name=model,
            language="pt",
            gemini_key=gemini_key
        )
        return f"Sucesso! Vídeo legendado salvo em: {os.path.basename(final_path)}"
    except Exception as e:
        return f"Erro ao adicionar legendas: {str(e)}"

def analyze_takes_tool(video_path: str) -> str:
    """
    Analisa a transcrição do vídeo para encontrar takes repetidos ou errados.
    Retorna uma análise em texto sugerindo intervalos para remover.
    """
    import os
    if os.path.isabs(video_path):
        full_path = video_path
    else:
        full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), video_path)

    if not os.path.exists(full_path):
        return f"Erro: Arquivo não encontrado: {full_path}"
        
    print(f"[Analyze] Transcrevendo {os.path.basename(full_path)}...")
    try:
        segments = transcrever(full_path, model_name="base", language="pt")
    except Exception as e:
        return f"Erro na transcrição: {e}"

    # Monta texto para o LLM
    transcript_text = ""
    for seg in segments:
        start = seg['start']
        end = seg['end']
        text = seg['text'].strip()
        transcript_text += f"[{start:.2f} - {end:.2f}] {text}\n"

    print(f"[Analyze] Enviando para análise (Gemini)...")
    
    prompt = f"""
    Analise a seguinte transcrição de um vídeo bruto.
    Identifique e marque para REMOÇÃO os seguintes tipos de trecho:

    1. Takes ruins / tentativas falhas: o orador erra uma frase e a repete/corrige logo em seguida (remova a tentativa errada, mantenha a boa).
    2. Gaguejadas e auto-correções ("eu-eu-eu acho", "a gente vai... a gente vai fazer").
    3. Vícios de linguagem e muletas quando isoladas ou em excesso: "é...", "éh", "ãh", "hum", "tipo", "tipo assim", "tipo que", "né", "então...", "aí...", "sabe?", "meio que", "tipo, né". Use bom senso: NÃO remova quando fazem parte natural da frase (ex: "tipo de coisa", "aí eu fui").
    4. Grandes pausas ou silêncios inferidos pelos timestamps (gap entre end de um segmento e start do próximo).

    Transcrição:
    {transcript_text}

    Retorne APENAS um JSON com a lista de intervalos para REMOVER.
    Seja cirúrgico nos vícios: corte só o intervalo da muleta, preservando o contexto ao redor.
    Em caso de dúvida entre cortar ou manter, MANTENHA.
    
    Formato:
    {{
        "remove_intervals": [
            {{"start": 10.5, "end": 15.2, "reason": "Errou a frase e repetiu"}},
            ...
        ]
    }}
    Se não houver nada para remover, retorne lista vazia.
    """
    
    if not llm_is_configured():
        return "Erro: LLM não configurado. Vá em Configurações e salve a API Key."

    try:
        text_resp = llm_generate(prompt).strip()
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:-3]
        elif text_resp.startswith("```"):
            text_resp = text_resp[3:-3]
        return text_resp
    except Exception as e:
        return f"Erro na análise da IA: {e}"

def cut_segments_tool(video_path: str, remove_intervals_json: str) -> str:
    """
    Corta segmentos específicos do vídeo.
    remove_intervals_json deve ser uma string JSON com lista de objetos {start, end}.
    """
    import os
    if os.path.isabs(video_path):
        full_path = video_path
    else:
        full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), video_path)

    if not os.path.exists(full_path):
        return f"Erro: Arquivo não encontrado: {full_path}"
        
    try:
        data = json.loads(remove_intervals_json)
        if isinstance(data, list):
            # Fallback: se a IA retornou uma lista diretamente
            intervals_to_remove = data
        else:
            intervals_to_remove = data.get("remove_intervals", [])
    except json.JSONDecodeError:
        return "Erro: JSON de intervalos inválido."
        
    if not intervals_to_remove:
        return "Nenhum intervalo para remover."

    # Calcula duração total
    duration_cmd = ["ffmpeg", "-i", full_path]
    dur_res = subprocess.run(duration_cmd, capture_output=True, text=True, encoding='utf-8')
    import re
    dur_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", dur_res.stderr)
    if not dur_match:
         return "Erro ao obter duração do vídeo."
    h, m, s = dur_match.groups()
    total_duration = float(h)*3600 + float(m)*60 + float(s)

    # Inverte lógica: Remover -> Manter
    keep_intervals = []
    current_time = 0.0
    
    # Ordena intervalos de remoção
    intervals_to_remove.sort(key=lambda x: x["start"])
    
    for interval in intervals_to_remove:
        start_remove = float(interval["start"])
        end_remove = float(interval["end"])
        
        # Ajuste de segurança: Buffer de 0.2s para evitar cortar fala abruptamente
        start_remove = max(0, start_remove - 0.2)
        end_remove = min(total_duration, end_remove + 0.2)
        
        if start_remove > current_time:
            # Mantém do tempo atual até o início do corte
            if start_remove - current_time > 0.5: # Ignora pedaços muito curtos (<0.5s)
                keep_intervals.append((current_time, start_remove))
        
        current_time = max(current_time, end_remove)
        
    if current_time < total_duration:
        keep_intervals.append((current_time, total_duration))
        
    # Aplica cortes usando ffmpeg filter_complex (mesma lógica do remove_silence)
    filter_str = ""
    concat_str = ""
    
    for i, (start, end) in enumerate(keep_intervals):
        filter_str += f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
        filter_str += f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];"
        concat_str += f"[v{i}][a{i}]"
        
    concat_str += f"concat=n={len(keep_intervals)}:v=1:a=1[outv][outa]"
    full_filter = filter_str + concat_str
    
    base, ext = os.path.splitext(full_path)
    output_path = f"{base}_clean{ext}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", full_path,
        "-filter_complex", full_filter,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", 
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return f"Vídeo limpo salvo em: {os.path.basename(output_path)}"
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "").strip().splitlines()[-10:]
        return "Erro ao renderizar cortes:\n" + "\n".join(stderr_tail)

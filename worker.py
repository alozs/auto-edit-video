"""
Worker executado em processo separado (multiprocessing).
Cada job roda isolado — pode ser terminado com SIGTERM pra cancelar forçado.
Comunicação com o main via Queue.
"""
import os
import shutil
import traceback
from pathlib import Path


def run_job(job_id: str, job_dir: str, input_path: str, options: dict,
            env_vars: dict, q):
    """Entry point do processo filho."""

    # Aplica snapshot de env (API keys, LLM provider, compute type, whisper model)
    for k, v in env_vars.items():
        if v is not None:
            os.environ[k] = str(v)

    # Imports pesados dentro do processo filho
    from remove_silence import remover_silencio
    from auto_caption import processar_legenda_completo
    from agent.tools import analyze_takes_tool, cut_segments_tool

    def emit(**msg):
        try:
            q.put(msg)
        except Exception:
            pass

    def log(line: str):
        print(f"[job {job_id[:8]}] {line}")
        emit(type="log", line=line)

    def update(**fields):
        emit(type="update", **fields)

    try:
        update(status="processing", progress=5, progress_text="Iniciando...")
        log(f"Processando com opções: {options}")

        current = input_path
        job_dir_p = Path(job_dir)
        step = 0
        total_steps = sum([
            options.get("remove_silence", False),
            options.get("remove_fillers", False),
            options.get("captions", False),
        ]) or 1

        def bump(text):
            nonlocal step
            step += 1
            pct = 5 + int(90 * step / total_steps)
            update(progress=pct, progress_text=text)
            log(text)

        # 1) remover silêncio
        if options.get("remove_silence"):
            bump("Removendo pausas...")
            out = str(job_dir_p / f"step{step}_silence.mp4")
            method = options.get("silence_method", "speech")
            ok = remover_silencio(current, out, method=method)
            if not ok:
                raise RuntimeError("Falha ao remover silêncio")
            current = out

        # 2) limpar fala / vícios
        if options.get("remove_fillers"):
            bump("Analisando vícios de fala...")
            intervals_json = analyze_takes_tool(current)
            if intervals_json and not intervals_json.startswith("Erro"):
                out = str(job_dir_p / f"step{step}_clean.mp4")
                import json as _json
                try:
                    parsed = _json.loads(intervals_json)
                    has_intervals = bool(parsed.get("remove_intervals", []) if isinstance(parsed, dict) else parsed)
                except Exception:
                    has_intervals = False
                if has_intervals:
                    result = cut_segments_tool(current, intervals_json)
                    base, ext = os.path.splitext(current)
                    produced = f"{base}_clean{ext}"
                    if os.path.exists(produced):
                        shutil.move(produced, out)
                        current = out
                    else:
                        log(f"cut_segments_tool: {result}")
                else:
                    log("Nenhum vício/take detectado.")
            else:
                log(f"Análise sem retorno: {intervals_json}")

        # 3) legendas
        if options.get("captions"):
            bump("Gerando legendas...")
            out = str(job_dir_p / f"step{step}_captioned.mp4")
            processar_legenda_completo(
                current,
                out,
                model_name=options.get("model", "small"),
                language=options.get("language", "pt"),
                gemini_key=None,
            )
            current = out

        # Output final
        final_path = str(job_dir_p / "output.mp4")
        if current != final_path:
            if current == input_path:
                shutil.copyfile(current, final_path)
            else:
                shutil.move(current, final_path)

        update(status="done", progress=100, progress_text="Concluído", output_path=final_path)
        log("✅ Pronto")
        emit(type="final")
    except Exception as e:
        tb = traceback.format_exc()
        log(f"❌ Erro: {e}\n{tb}")
        update(status="error", error=str(e), progress_text=f"Erro: {e}")
        emit(type="final")

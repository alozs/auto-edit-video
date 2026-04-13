from llm import generate, is_configured

SYSTEM_PROMPT = """
Você é um revisor de legendas ortográfico e gramatical EXPERT.
Sua missão é corrigir erros de português em uma lista de palavras, mantendo ESTRITAMENTE a estrutura.

REGRAS DE OURO:
1. Você receberá palavras separadas por ' | '.
2. Você deve retornar as palavras corrigidas separadas por ' | '.
3. A quantidade de palavras na saída DEVE SER IDÊNTICA à entrada.
4. NÃO mude a ordem das palavras.
5. Corrija apenas: erros de digitação, acentuação (ex: 'eh' -> 'é', 'voce' -> 'você') e gramática óbvia.
6. Não mude o estilo (gírias podem ser mantidas se estiverem grafadas corretamente, ex: 'tá' é aceitável, mas 'ta' deve virar 'tá').
7. Se não houver erro, repita a palavra original.
"""


def corrigir_palavras(words_list: list, api_key: str = None, batch_size: int = 100):
    """Corrige ortografia preservando timestamps e ordem."""
    if api_key:
        # compat: se chamado com chave explícita, setar no env conforme provider
        import os
        if os.environ.get("LLM_PROVIDER", "google") == "openrouter":
            os.environ["OPENROUTER_API_KEY"] = api_key
        else:
            os.environ["GEMINI_API_KEY"] = api_key

    if not is_configured():
        print("⚠️  LLM não configurado. Pulando correção.")
        return words_list

    print(f"[IA] Corrigindo {len(words_list)} palavras...")

    all_texts = [w["word"].strip() for w in words_list]
    corrected = []

    for i in range(0, len(all_texts), batch_size):
        batch = all_texts[i : i + batch_size]
        batch_str = " | ".join(batch)
        try:
            text = generate(f"Corrija esta lista:\n{batch_str}", system=SYSTEM_PROMPT).strip()
            parts = [p.strip() for p in text.split("|")]
            if len(parts) != len(batch):
                print(f"⚠️  Lote {i // batch_size} com tamanho divergente. Mantendo original.")
                corrected.extend(batch)
            else:
                corrected.extend(parts)
        except Exception as e:
            print(f"❌ Erro no lote {i // batch_size}: {e}")
            corrected.extend(batch)

    result = []
    for original, new_text in zip(words_list, corrected):
        obj = original.copy()
        obj["word"] = new_text
        result.append(obj)

    print("[IA] Correção concluída.")
    return result

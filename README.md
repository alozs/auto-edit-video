# 🎬 Auto Video Editor

Ferramenta simples de edição automática de vídeo com IA:

- 🔇 Remove silêncio (Whisper)
- ✂️ Corta vícios de linguagem e takes ruins (Gemini)
- 📝 Gera legendas estilo CapCut (Whisper + Gemini)

**Fluxo:** envie o vídeo → escolha as opções → baixe o resultado → descarte. Sem histórico, sem gerenciador de arquivos. Arquivos temporários são apagados após 1h.

## Stack

- **Backend:** Flask + Socket.IO + OpenAI Whisper + Google Gemini + FFmpeg
- **Frontend:** SvelteKit + Tailwind CSS v4 + componentes próprios (inspirados em shadcn)

## Pré-requisitos

- Python 3.8+
- Node 20+ e pnpm
- FFmpeg (`brew install ffmpeg` / `apt install ffmpeg`)
- (opcional) Chave do Google Gemini para correção e corte de vícios — https://aistudio.google.com/apikey

## Setup

```bash
# Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend
pnpm install
```

Configure `.env` (opcional):

```env
GEMINI_API_KEY=sua_chave_aqui
# Para expor na internet, protege com senha:
ACCESS_PASSWORD=sua_senha
```

## Rodando

Dois processos em paralelo:

```bash
# Terminal 1 — API
.venv/bin/python web_app.py

# Terminal 2 — UI
cd frontend && pnpm run dev
```

Acesse **http://localhost:5173**. O Vite faz proxy para `http://localhost:3001` (API).

## Linha de comando

```bash
# Remover silêncio + legendar (pipeline completo)
python edit_video.py "video.mp4" --output "final.mp4"

# Só silêncio
python remove_silence.py "video.mp4" --method speech

# Só legendas
python auto_caption.py "video.mp4"
```

## API (REST)

| Método | Rota                          | Descrição                          |
|--------|-------------------------------|------------------------------------|
| POST   | `/api/jobs`                   | Upload + opções (multipart)        |
| GET    | `/api/jobs/:id`               | Status + log                       |
| GET    | `/api/jobs/:id/download`      | Baixa o resultado                  |
| DELETE | `/api/jobs/:id`               | Apaga o job e seus arquivos        |
| —      | Socket.IO `job_update`/`job_log` | Progresso em tempo real         |

## Licença

MIT.

# Guia de Migração — Código Antigo → Pipeline Refatorado

## O que mudou e onde foi parar cada parte

### Autenticação do Drive
**Antes:** `auth.authenticate_user()` repetido em 8 células  
**Depois:** `DriveClient.get()` — autentica uma vez, reutiliza em tudo  

```python
# Antes (célula 2, 3, 4, 5, 6, 7, 8, 9...)
from google.colab import auth
auth.authenticate_user()
from googleapiclient.discovery import build
service = build('drive', 'v3')

# Depois (uma vez na Inicialização)
from drive_utils import DriveClient
drive = DriveClient.get()  # autentica lazy na primeira chamada real
```

---

### Geração de áudio (Edge TTS)
**Antes:** Célula 1 com `asyncio.get_event_loop().run_until_complete(...)`  
**Depois:** `pipeline.fase1_gerar_audio()` → `audio_utils` / `video_pipeline.fase1_*`

---

### Transcrição Whisper
**Antes:** Célula 2, variável `result_whisper` global  
**Depois:** `pipeline.fase2_transcrever_whisper()` → salva `pai_nosso_pt_edge.srt`

---

### Correção PT com Groq
**Antes:** Células A/C com funções `corrigir_texto_groq()` inline  
**Depois:** `pipeline.fase3_corrigir_pt()` → `groq_client.corrigir_texto_pt()`

---

### Redistribuição EN/ES/FR
**Antes:** Células 5.5 / 5.6 fora de ordem  
**Depois:** `pipeline.fase4_traduzir()` → `groq_client.redistribuir_traducoes()` + `revisar_vocabulario_liturgico()`

---

### Classificação morfológica
**Antes:** Prompt enorme inline, sem cache, sem validação  
**Depois:** `pipeline.fase5_classificar()` → `classification.Classifier`  
- Cache automático em `classificacao_pai_nosso_pt.json` (mesmo nome de arquivo)
- Se JSON existe e é válido → não chama o Groq
- `pipeline._clf.invalidar_cache('pt')` para forçar reclassificação

---

### Download e corte de clipes
**Antes:** Loop serial com `yt-dlp` e `subprocess`  
**Depois:** `pipeline.fase6_baixar_clipes()` — download HTTP direto + `ThreadPoolExecutor` (3 threads paralelas)

---

### Montagem do vídeo (crédito, logo, áudio, trilha)
**Antes:** Células separadas para cada etapa  
**Depois:** `pipeline.fase7_criar_video_base()` — tudo em sequência: crédito → concat → áudio → trilha

---

### Legendas (drawtext → ASS)
**Antes:** Centenas de filtros `-vf drawtext=...` concatenados — lento  
**Depois:** `gerar_ass()` cria um único `legendas_pai_nosso.ass` com todos os 4 idiomas; `queimar_legendas_ass()` aplica em 1 passe

**Por que é mais rápido:** O FFmpeg processa cada filtro drawtext como um passe de encode separado internamente. Com ASS, todos os textos são renderizados em um único passe.

---

## Nomes de arquivo: compatibilidade garantida

| Arquivo | Antes | Depois |
|---------|-------|--------|
| Áudio | `pai_nosso_completo.wav` | `pai_nosso_audio.wav` |
| SRT PT bruto | `pai_nosso_pt_edge.srt` | `pai_nosso_pt_edge.srt` ✅ |
| SRT PT corrigido | `pai_nosso_pt.srt` | `pai_nosso_pt.srt` ✅ |
| SRT EN/ES/FR | `pai_nosso_en.srt` etc. | `pai_nosso_en.srt` ✅ |
| JSON classificação | `classificacao_pai_nosso_pt.json` | `classificacao_pai_nosso_pt.json` ✅ |
| Vídeo base | `pai_nosso_base.mp4` | `pai_nosso_base.mp4` ✅ |
| Vídeo final | `pai_nosso_final.mp4` | `pai_nosso_final.mp4` ✅ |

> Único arquivo renomeado: o áudio (`_completo` → `_audio`). Ajuste o ID da pasta no Drive se já tiver o arquivo antigo.

---

## Retomada de fases (checkpoint)

Se o Colab desconectar no meio do processo:

```python
# Ver onde parou
from checkpoint import Checkpoint
print(Checkpoint().resumo())

# Continuar de onde parou
pipeline.run()

# Ou reiniciar a partir de uma fase específica
pipeline.run(from_phase='clipes_cortados')
```

---

## Trocar a oração (Ave Maria, Credo, etc.)

Basta alterar 3 campos no `PipelineConfig`:

```python
config = PipelineConfig(
    NOME_ORACAO  = 'ave_maria',
    TEXTO_ORACAO = 'Ave Maria, cheia de graça...',
    VOZ_EDGE     = 'pt-BR-FranciscaNeural',
)
pipeline = VideoPipeline(config, groq)
pipeline.run()
```

Todos os nomes de arquivo (`ave_maria_pt.srt`, `ave_maria_final.mp4`, etc.) são derivados automaticamente.

---

## Estrutura de arquivos no Drive (sem mudança)

```
MyDrive/
├── pipeline/           ← módulos .py (novos)
├── áudio/              ← pai_nosso_audio.wav
├── legendas/           ← pai_nosso_pt.srt, pai_nosso_en.srt...
├── classificacao/      ← classificacao_pai_nosso_pt.json...
├── logo/               ← globo_cruz_logo.png
├── musica/             ← trilha.mp3
├── videos/             ← pai_nosso_base.mp4, pai_nosso_final.mp4
└── cookies/            ← cookies.txt
```

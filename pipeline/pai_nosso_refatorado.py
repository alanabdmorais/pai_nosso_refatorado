# -*- coding: utf-8 -*-
"""pai_nosso_refatorado.ipynb

# 🎬 Pipeline Multilíngue — Orações com Legendas Morfológicas

**Estratégia de classificação intermediária:**
O Groq classifica → você revisa com uma IA → pipeline continua com os JSONs corrigidos.

---

### Fluxo completo

| # | Fase | O que faz | Ação |
|---|------|-----------|------|
| 0 | Setup | Instala deps, monta Drive, importa módulos | Automático |
| Init | — | Cria config, groq e pipeline | Automático |
| B0 | YouTube | Baixa legendas de referência (opcional) | Manual |
| 1 | Áudio | Edge TTS → .wav no Drive | Automático |
| 2 | Whisper | Transcrição → SRT bruto (só se não tiver YouTube) | Opcional |
| 3 | Correção PT | YouTube → re-segmenta em frases completas | Automático |
| 4 | Traduções | Groq gera EN/ES/FR | Automático |
| **5A** | **Classificação** | **Groq/Mistral classifica + gera pacote de revisão** | **Automático → pausa** |
| **5B** | **Revisão** | **Você corrige JSONs com IA externa** | **👤 Manual** |
| **5C** | **Recarregar** | **Pipeline carrega JSONs corrigidos** | **Automático** |
| 6 | Clipes | Baixa e corta vídeos do Pixabay | Automático |
| 7 | Vídeo base | Crédito + narração + trilha | Automático |
| 8 | Legendas ASS | Queima legendas coloridas no vídeo | Automático |

> **Estrutura do Drive:** `MyDrive/pai_nosso_refatorado/pipeline/`
> **Retomar de uma fase:** `pipeline.run(from_phase='nome_da_fase')`
"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CÉLULA 0 — Setup (rode uma vez por sessão)                    ║
# ╚══════════════════════════════════════════════════════════════════╝

# Sistema
!apt-get -qq -y install ffmpeg espeak-ng > /dev/null 2>&1
print('✅ ffmpeg + espeak-ng')

# Python
!pip install -q edge-tts openai-whisper openai pandas gdown yt-dlp nest_asyncio
print('✅ pacotes Python')

# Drive
from google.colab import drive, userdata
try:
    drive.flush_and_unmount()
except:
    pass
drive.mount('/content/drive', force_remount=True)
print('✅ Drive montado')

# Copiar módulos
import shutil, os, sys, logging
from pathlib import Path

PASTA_MODULOS = '/content/drive/MyDrive/pai_nosso_refatorado/pipeline/modulos'
if not os.path.exists(PASTA_MODULOS):
    FALLBACK = '/content/drive/MyDrive/pipeline/modulos'
    if os.path.exists(FALLBACK):
        PASTA_MODULOS = FALLBACK
        print(f'⚠️ Usando fallback: {PASTA_MODULOS}')

DESTINO = '/content/pipeline'
if os.path.exists(DESTINO):
    shutil.rmtree(DESTINO)

if os.path.exists(PASTA_MODULOS):
    shutil.copytree(PASTA_MODULOS, DESTINO)
    print(f'✅ Módulos copiados → {DESTINO}')
    for f in sorted(Path(DESTINO).glob('*.py')):
        print(f'   📄 {f.name}')
else:
    print(f'❌ Pasta não encontrada: {PASTA_MODULOS}')

if DESTINO not in sys.path:
    sys.path.insert(0, DESTINO)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(name)-22s  %(levelname)s  %(message)s',
    datefmt='%H:%M:%S',
)
os.chdir('/content')
print('\n✅ Setup concluído!')

# ╔══════════════════════════════════════════════════════════════════╗
# ║  INICIALIZAÇÃO — rode após o Setup                             ║
# ╚══════════════════════════════════════════════════════════════════╝

import nest_asyncio
nest_asyncio.apply()

from config import PipelineConfig
from groq_client import GroqClient
from video_pipeline import VideoPipeline
from checkpoint import Checkpoint
from google.colab import userdata

config = PipelineConfig(
    NOME_ORACAO = 'pai_nosso',
    # Para outra oração:
    # NOME_ORACAO  = 'ave_maria',
    # TEXTO_ORACAO = 'Ave Maria, cheia de graça...',
    # VOZ_EDGE     = 'pt-BR-FranciscaNeural',
)

groq     = GroqClient(api_key=userdata.get('GROQ_KEY'), nome_oracao=config.NOME_ORACAO)
pipeline = VideoPipeline(config, groq)
cp       = Checkpoint()

print(config.resumo())
print()
print(cp.resumo())
print(f'\n▶  Próxima fase: {cp.proxima_fase_pendente() or "(tudo concluído)"}')

# ╔══════════════════════════════════════════════════════════════════╗
# ║  🔍 VERIFICAÇÃO DA ESTRUTURA DO DRIVE                          ║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path

print("═" * 60)
print("📁 VERIFICANDO ESTRUTURA DO DRIVE")
print("═" * 60)

BASE = Path('/content/drive/MyDrive/pai_nosso_refatorado/pipeline')
pastas = {
    'modulos':   BASE / 'modulos',
    'correcoes': BASE / f'correcoes/{config.NOME_ORACAO}',
    'brutos':    BASE / f'brutos/{config.NOME_ORACAO}',
}

for rotulo, pasta in pastas.items():
    print(f"\n📁 {pasta}")
    if pasta.exists():
        arquivos = sorted(pasta.iterdir())
        if arquivos:
            for f in arquivos:
                print(f"   ✅ {f.name}  ({f.stat().st_size/1024:.1f} KB)")
        else:
            print("   (pasta vazia)")
    else:
        print("   ⚠️  Ainda não criada")

print("═" * 60)

# ╔══════════════════════════════════════════════════════════════════╗
# ║  🧹 LIMPEZA SELETIVA                                           ║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path
import shutil, sys

BASE_DRIVE   = Path('/content/drive/MyDrive/pai_nosso_refatorado/pipeline')
PASTA_BRUTOS = BASE_DRIVE / 'brutos'
PASTA_COR    = BASE_DRIVE / 'correcoes'

def limpeza_seletiva():
    print("═" * 65)
    print("🧹 LIMPEZA SELETIVA")
    print("═" * 65)
    print("Escolha (números separados por vírgula, ex: 1,3):")
    print("  1  🎵 Áudios (.wav)")
    print("  2  📝 Legendas (.srt, .ass) [mantém yt_ref]")
    print("  3  🎬 Vídeos gerados")
    print("  4  📊 JSONs brutos (Drive/brutos/)")
    print("  5  ✅ JSONs corrigidos (Drive/correcoes/)")
    print("  6  📌 Checkpoint")
    print("  7  📁 Pastas temporárias")
    print("  8  📦 Cache Python")
    print("  9  🗑️ Cache FASE 3 (fase3_cache.json)")
    print(" 10  🗑️ Cache classificação (cache_classificacao/)")
    print(" 11  🔥 TUDO local (1–3, 6–10)")
    print(" 12  🔥🔥 TUDO local + Drive (1–10)")
    print("  0  Sair")
    print("═" * 65)

    opcoes = input("\nEscolha: ").strip()
    if opcoes == '0':
        return
    selecionados = [int(x) for x in opcoes.split(',')]
    cont = 0

    def rm(f):
        nonlocal cont
        f.unlink()
        cont += 1
        print(f"   🗑️ {f.name}")

    def rmdir(d):
        nonlocal cont
        shutil.rmtree(d)
        cont += 1
        print(f"   🗑️ {d.name}/")

    if any(x in selecionados for x in [1, 11, 12]):
        print("\n🎵 Áudios...")
        for f in Path('.').glob('*_audio.wav'): rm(f)

    if any(x in selecionados for x in [2, 11, 12]):
        print("\n📝 Legendas...")
        for f in Path('.').glob('*.srt'):
            if 'yt_ref' not in f.name: rm(f)
        for f in Path('.').glob('*.ass'): rm(f)

    if any(x in selecionados for x in [3, 11, 12]):
        print("\n🎬 Vídeos...")
        for pat in ['*_base.mp4', '*_final.mp4', 'clipe_*.mp4', 'temp_*.mp4']:
            for f in Path('.').glob(pat): rm(f)

    if any(x in selecionados for x in [4, 12]):
        print("\n📊 JSONs brutos...")
        if PASTA_BRUTOS.exists():
            for d in PASTA_BRUTOS.iterdir():
                for f in d.glob('classificacao_*.json'): rm(f)

    if any(x in selecionados for x in [5, 12]):
        print("\n✅ JSONs corrigidos...")
        if PASTA_COR.exists():
            for d in PASTA_COR.iterdir():
                for f in d.glob('classificacao_*.json'): rm(f)

    if any(x in selecionados for x in [6, 11, 12]):
        print("\n📌 Checkpoint...")
        cp = Path('checkpoint.json')
        if cp.exists(): rm(cp)

    if any(x in selecionados for x in [7, 11, 12]):
        print("\n📁 Pastas temporárias...")
        for p in ['clipes_cortados', 'clipes_prontos', 'temp_raw', '__pycache__']:
            pp = Path(p)
            if pp.exists(): rmdir(pp)

    if any(x in selecionados for x in [8, 11, 12]):
        print("\n📦 Cache Python...")
        mods = ['groq_client','video_pipeline','config','classification',
                'checkpoint','drive_utils','ffmpeg_utils','srt_utils','models','constants']
        for m in mods:
            if m in sys.modules:
                del sys.modules[m]; cont += 1; print(f"   🗑️ {m}")

    if any(x in selecionados for x in [9, 11, 12]):
        f = Path('/content/fase3_cache.json')
        if f.exists(): rm(f)

    if any(x in selecionados for x in [10, 11, 12]):
        d = Path('/content/cache_classificacao')
        if d.exists(): rmdir(d)

    print(f"\n✅ {cont} item(ns) removido(s)")

limpeza_seletiva()

"""### 🔵 Célula B0 — Opcional: baixar legendas do YouTube
Execute **antes** das fases 1–8. Se pular, Groq traduz a partir do PT e Whisper transcreve.
"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CÉLULA B0 — Baixar legendas do YouTube                        ║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path
import subprocess, shutil
from drive_utils import DriveClient
from srt_utils import ler_srt

cfg   = config
drive_client = DriveClient.get()
drive_client.download_se_ausente(cfg.ID_PASTA_COOKIES, cfg.NOME_COOKIES, Path(cfg.NOME_COOKIES))
cookies_flag = ['--cookies', cfg.NOME_COOKIES] if Path(cfg.NOME_COOKIES).exists() else []

print("═" * 60)
print("📺 BAIXANDO LEGENDAS DO YOUTUBE")
print("═" * 60)

# ── Coloque as URLs com legenda abaixo ───────────────────────────────────────
URLS = {
    'pt': 'https://www.youtube.com/watch?v=p5Vg7Vn2KeM',
    'en': 'https://www.youtube.com/watch?v=p5Vg7Vn2KeM',
    'es': 'https://www.youtube.com/watch?v=p5Vg7Vn2KeM',
    'fr': 'https://www.youtube.com/watch?v=p5Vg7Vn2KeM',
}

for lang, url in URLS.items():
    nome_srt = cfg.nome_srt(lang)
    print(f'\n⬇️  {lang.upper()}: {url[:60]}')
    cmd = [
        'yt-dlp', '--write-sub', '--sub-lang', lang, '--write-auto-sub',
        '--skip-download', '--sub-format', 'srt', '--convert-subs', 'srt',
        '--output', f'{cfg.NOME_ORACAO}_{lang}', *cookies_flag, url
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    encontrado = False
    for c in Path('.').glob(f'{cfg.NOME_ORACAO}_{lang}*.srt'):
        if c.name != nome_srt:
            c.rename(nome_srt)
        print(f'   ✅ {nome_srt}')
        encontrado = True
        break
    if not encontrado:
        print(f'   ⚠️  Não disponível nesse vídeo')

print("\n" + "═" * 60)

"""### ▶ Fases 1–4 — Automáticas"""

# ── FASE 1: Áudio com Edge TTS ───────────────────────────────────────────────
audio = pipeline.fase1_gerar_audio()
print(f'✅ {audio}  ({audio.stat().st_size/1024:.0f} KB)')

# ╔══════════════════════════════════════════════════════════════════╗
# ║  FASE 2 — Whisper (opcional, só se não tiver YouTube)          ║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path

srt_youtube = Path(config.nome_srt('pt'))
if srt_youtube.exists():
    print("ℹ️  YouTube disponível — Whisper não é necessário.")
    print(f"   {srt_youtube.name} já existe, FASE 3 vai re-segmentá-lo.")
else:
    print("⚠️  YouTube não encontrado — rodando Whisper como fallback...")
    srt_bruto = pipeline.fase2_transcrever_whisper()
    print(f"✅ Transcrição: {srt_bruto}")

# ╔══════════════════════════════════════════════════════════════════╗
# ║  FASE 3 — Correção PT (YouTube → re-segmenta, Whisper fallback)║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path
from srt_utils import ler_srt, resegmentar_por_frase, eliminar_gaps, salvar_srt

print("═" * 70)
print("📝 FASE 3 — PRODUZINDO SRT PT DEFINITIVO")
print("═" * 70)

srt_youtube = Path(config.nome_srt('pt'))

if srt_youtube.exists():
    print(f"📺 YouTube encontrado: {srt_youtube.name}")
    legendas_raw = ler_srt(srt_youtube)
    print(f"   Segmentos brutos: {len(legendas_raw)}")

    print("\n📋 Antes (YouTube bruto):")
    for leg in legendas_raw:
        print(f"  [{leg.id:02d}]  {leg.inicio_str} → {leg.fim_str}  |  {leg.texto}")

    legendas = resegmentar_por_frase(legendas_raw)
    legendas = eliminar_gaps(legendas)

    print(f"\n✅ Depois ({len(legendas)} frases completas):")
    for leg in legendas:
        print(f"  [{leg.id:02d}]  {leg.inicio_str} → {leg.fim_str}  |  {leg.texto}")

    fonte = "youtube_resegmentado"

else:
    print("⚠️  YouTube não encontrado — usando Whisper + Groq como fallback")
    srt_edge = Path(config.NOME_SRT_PT_EDGE)
    if not srt_edge.exists():
        raise FileNotFoundError(
            f"Nenhum SRT encontrado. Execute a Célula B0 (YouTube) "
            f"ou a Fase 2 (Whisper). Esperado: {srt_edge}"
        )
    legendas_raw = ler_srt(srt_edge)
    print(f"   Whisper: {len(legendas_raw)} segmentos — corrigindo via Groq...")
    legendas = pipeline.fase3_corrigir_pt()
    fonte = "whisper_groq"

srt_pt = Path(config.NOME_SRT_PT)
salvar_srt(legendas, srt_pt)

print("\n" + "═" * 70)
print(f"✅ FASE 3 CONCLUÍDA! | Fonte: {fonte} | {len(legendas)} legendas")
print("═" * 70)

# ── FASE 4: Traduções EN/ES/FR ───────────────────────────────────────────────
from srt_utils import ler_srt

legendas_pt = ler_srt(config.NOME_SRT_PT)
pipeline.legendas_idiomas = pipeline.fase4_traduzir(legendas_pt)

print('Primeiras 2 legendas por idioma:')
for i in range(min(2, len(legendas_pt))):
    for lang in config.IDIOMAS:
        legs = pipeline.legendas_idiomas.get(lang, [])
        if i < len(legs):
            print(f'  {lang.upper()}: {legs[i].texto}')
    print()

"""### ▶ Fase 5A — Classificação morfológica (Groq → Mistral) + Pacote de revisão"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  FASE 5A — Classificação Morfológica + Pacote de Revisão       ║
# ║  Groq → Mistral | Delay: 8s/legenda | 15s/idioma              ║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path
import time, json, re
from datetime import datetime
from google.colab import userdata
from openai import OpenAI
from srt_utils import ler_srt
from models import Palavra

print("═" * 70)
print("🤖 FASE 5A — CLASSIFICAÇÃO MORFOLÓGICA")
print("═" * 70)

DELAY_LEGENDAS  = 8
DELAY_IDIOMAS   = 15
DELAY_RATELIMIT = 60

CACHE_DIR = Path('/content/cache_classificacao')
CACHE_DIR.mkdir(exist_ok=True)

APIS_CONFIG = [
    {'nome': 'Groq',    'secret_name': 'GROQ_KEY',
     'base_url': 'https://api.groq.com/openai/v1',  'modelo': 'llama-3.3-70b-versatile'},
    {'nome': 'Mistral', 'secret_name': 'MISTRAL_KEY',
     'base_url': 'https://api.mistral.ai/v1',        'modelo': 'mistral-small-latest'},
]

def limpar_json(texto):
    if not texto: return None
    match = re.search(r'\{.*\}', texto, re.DOTALL)
    if not match: return None
    j = match.group()
    j = re.sub(r"'", '"', j)
    j = re.sub(r',\s*([}\]])', r'\1', j)
    j = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', j)
    try: return json.loads(j)
    except:
        palavras = re.findall(r'"texto"\s*:\s*"([^"]+)"\s*,\s*"classe"\s*:\s*"([^"]+)"', j)
        if palavras: return {"palavras": [{"texto": p[0], "classe": p[1]} for p in palavras]}
    return None

class APIRotativa:
    def __init__(self, configs):
        self.apis = []
        for cfg in configs:
            try:
                key = userdata.get(cfg['secret_name'])
                if key:
                    self.apis.append({'nome': cfg['nome'],
                                      'client': OpenAI(api_key=key, base_url=cfg['base_url']),
                                      'modelo': cfg['modelo']})
                    print(f"   ✅ {cfg['nome']}")
                else:
                    print(f"   ⚠️ {cfg['nome']} — chave não encontrada")
            except Exception as e:
                print(f"   ❌ {cfg['nome']} — {e}")
        self.idx   = 0
        self.stats = {a['nome']: {'t': 0, 's': 0} for a in self.apis}
        print(f"\n📊 {len(self.apis)} API(s) disponíveis")

    def classificar(self, texto, lang):
        prompt = f"""Idioma: {lang}
Texto: "{texto}"

Classifique cada palavra. Use apenas classes válidas:
- substantivo_masculino_singular, substantivo_feminino_singular
- substantivo_masculino_plural, substantivo_feminino_plural
- pronome_relativo, pronome_possessivo_singular, pronome_possessivo_plural, pronome_pessoal, pronome_demonstrativo
- verbo_presente, verbo_passado, verbo_imperativo, verbo_subjuntivo
- adjetivo_normal, advérbio_normal
- preposicao, artigo_definido, artigo_indefinido, artigo_partitivo, conjuncao, interjeicao

REGRAS: 'que'/'qui' = pronome_relativo | 'thy' EN = pronome_possessivo_singular | 'soit' FR = verbo_subjuntivo

Responda APENAS com JSON válido:
{{"palavras": [{{"texto": "Pai", "classe": "substantivo_masculino_singular"}}]}}"""

        for _ in range(len(self.apis) * 3):
            api = self.apis[self.idx]
            self.stats[api['nome']]['t'] += 1
            print(f"   🔄 {api['nome']}...")
            try:
                r = api['client'].chat.completions.create(
                    model=api['modelo'],
                    messages=[
                        {"role": "system", "content": "Especialista em linguística. Responda apenas JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2, max_tokens=800,
                )
                dados = limpar_json(r.choices[0].message.content.strip())
                if dados and 'palavras' in dados:
                    self.stats[api['nome']]['s'] += 1
                    print(f"   ✅ {api['nome']}")
                    self.idx = 0
                    return [Palavra(texto=p['texto'],
                                   classe=p.get('classe', 'substantivo_masculino_singular'))
                            for p in dados['palavras'] if p.get('texto')]
                print(f"   ⚠️ JSON inválido")
            except Exception as e:
                err = str(e).lower()
                if '429' in err or 'rate limit' in err:
                    print(f"   ⚠️ Rate limit — aguardando {DELAY_RATELIMIT}s...")
                    time.sleep(DELAY_RATELIMIT)
                else:
                    print(f"   ⚠️ {str(e)[:60]}")
            self.idx = (self.idx + 1) % len(self.apis)
            time.sleep(5)

        print("   ❌ Todas as APIs falharam — fallback genérico")
        return [Palavra(texto=t, classe='substantivo_masculino_singular') for t in texto.split()]

    def resumo(self):
        print("\n📊 ESTATÍSTICAS:")
        for nome, s in self.stats.items():
            if s['t']: print(f"   {nome}: {s['s']}/{s['t']} ({s['s']/s['t']*100:.0f}%)")

# Cache helpers
def cache_path(lang, lid): return CACHE_DIR / f'{config.NOME_ORACAO}_{lang}_leg{lid}.json'
def do_cache(lang, leg):
    p = cache_path(lang, leg.id)
    p.write_text(json.dumps([{'texto': w.texto, 'classe': w.classe} for w in leg.palavras],
                            indent=2, ensure_ascii=False), encoding='utf-8')
def load_cache(lang, legendas):
    n = 0
    for leg in legendas:
        p = cache_path(lang, leg.id)
        if p.exists():
            try:
                data = json.loads(p.read_text())
                leg.palavras = [Palavra(texto=d['texto'], classe=d['classe']) for d in data]
                n += 1
            except: pass
    return n

# Carregar SRT corrigido
srt_corrigido = Path(config.NOME_SRT_PT)
if not srt_corrigido.exists():
    raise FileNotFoundError("SRT PT não encontrado — execute a FASE 3 primeiro")
legendas_pt = ler_srt(srt_corrigido)
print(f"📖 {len(legendas_pt)} legendas PT carregadas do SRT corrigido")

if not pipeline.legendas_idiomas:
    pipeline.legendas_idiomas = pipeline._carregar_todos_srts(legendas_pt)

cliente = APIRotativa(APIS_CONFIG)
inicio  = datetime.now()

for i, lang in enumerate(config.IDIOMAS):
    legendas = pipeline.legendas_idiomas[lang]
    print(f"\n{'='*60}\n🔤 {lang.upper()} — {len(legendas)} legendas\n{'='*60}")

    n_cache = load_cache(lang, legendas)
    if n_cache: print(f"📁 Cache: {n_cache}/{len(legendas)} já classificadas")

    for j, leg in enumerate(legendas):
        if cache_path(lang, leg.id).exists() and leg.palavras:
            print(f"  [{j+1}/{len(legendas)}] ⏭️ cache — {leg.texto[:45]}")
            continue

        print(f"\n  [{j+1}/{len(legendas)}] {leg.texto[:55]}")
        palavras = cliente.classificar(leg.texto, lang)
        if palavras:
            leg.palavras = palavras
            do_cache(lang, leg)
            print(f"  ✅ {len(palavras)} palavras")

        if j < len(legendas) - 1:
            for s in range(DELAY_LEGENDAS, 0, -2):
                print(f"  ⏳ {s}s...", end='\r')
                time.sleep(2)
            print()

    if i < len(config.IDIOMAS) - 1:
        print(f"\n⏳ Próximo idioma em {DELAY_IDIOMAS}s...")
        for s in range(DELAY_IDIOMAS, 0, -5):
            print(f"  ⏰ {s}s...", end='\r')
            time.sleep(5)
        print()

# Salvar JSONs locais
print("\n📦 Salvando JSONs...")
for lang in config.IDIOMAS:
    dados = {str(leg.id): {
        'inicio': leg.inicio_str, 'fim': leg.fim_str,
        'texto_original': leg.texto,
        'palavras': [{'texto': p.texto, 'classe': p.classe} for p in leg.palavras]
    } for leg in pipeline.legendas_idiomas[lang]}
    p = Path(f'classificacao_{config.NOME_ORACAO}_{lang}.json')
    p.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"   ✅ {p.name}")

tempo = (datetime.now() - inicio).seconds
print(f"\n✅ FASE 5A CONCLUÍDA! {tempo//60}min {tempo%60}s")
cliente.resumo()
print("\n▶ Execute a célula PACOTE DE REVISÃO abaixo")

# ╔══════════════════════════════════════════════════════════════════╗
# ║  📦 PACOTE DE REVISÃO — gera guias + ZIP para download         ║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path
import shutil, zipfile
from datetime import datetime
from google.colab import files

NOME = config.NOME_ORACAO
CORR_ROOT = Path('/content/drive/MyDrive/pai_nosso_refatorado/pipeline/correcoes')
CORR_ORACAO = CORR_ROOT / NOME

print("═" * 65)
print("📦 GERANDO PACOTE DE REVISÃO")
print("═" * 65)

# Gera prompt_revisao.md e relatorio_classificacoes.csv no Drive
pasta_json = pipeline._clf.exportar_pacote_revisao(pipeline.legendas_idiomas)

print(f"\n📁 JSONs: {pasta_json}")
print(f"📁 Guias: {CORR_ROOT}")

print("\n🔍 Verificando arquivos gerados:")
for arq in ['prompt_revisao.md', 'relatorio_classificacoes.csv']:
    f = CORR_ROOT / arq
    if f.exists():
        print(f"   ✅ {arq} ({f.stat().st_size/1024:.1f} KB)")
    else:
        print(f"   ❌ {arq} — não gerado")

# Criar ZIP para download
temp = Path('/content/download_pacote')
temp.mkdir(exist_ok=True)

for arq in ['prompt_revisao.md', 'relatorio_classificacoes.csv']:
    src = CORR_ROOT / arq
    if src.exists(): shutil.copy(src, temp / arq)

for lang in ['pt', 'en', 'es', 'fr']:
    src = Path(f'/content/classificacao_{NOME}_{lang}.json')
    if src.exists():
        shutil.copy(src, temp / src.name)
        print(f"   ✅ {src.name}")

readme = f"""# PACOTE DE REVISÃO — {NOME.upper()}
Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## INSTRUÇÕES:
1. Abra prompt_revisao.md e copie o conteúdo
2. Cole numa IA (Claude, GPT, etc.) junto com os 4 JSONs
3. A IA retorna os JSONs corrigidos
4. Salve em: MyDrive/pai_nosso_refatorado/pipeline/correcoes/{NOME}/
5. Execute a FASE 5C no notebook
"""
(temp / 'LEIA-ME.txt').write_text(readme, encoding='utf-8')

zip_path = Path(f'/content/pacote_revisao_{NOME}.zip')
with zipfile.ZipFile(zip_path, 'w') as z:
    for f in temp.iterdir():
        z.write(f, f.name)

shutil.rmtree(temp)
files.download(str(zip_path))
print(f"\n✅ Download: pacote_revisao_{NOME}.zip")

"""### ⏸️ Fase 5B — Revisão manual ← **você faz isso**

1. Abra o ZIP baixado
2. Copie o conteúdo de `prompt_revisao.md`
3. Cole numa IA junto com os 4 JSONs
4. Salve os JSONs corrigidos em `MyDrive/pai_nosso_refatorado/pipeline/correcoes/pai_nosso/`
5. Execute a Fase 5C abaixo

### ▶ Fase 5C — Recarregar classificações corrigidas
"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  FASE 5C — Recarregar do Drive após revisão                   ║
# ╚══════════════════════════════════════════════════════════════════╝

from pathlib import Path

print("═" * 65)
print("📥 FASE 5C — RECARREGANDO CLASSIFICAÇÕES CORRIGIDAS")
print("═" * 65)

pasta_correcoes = Path(
    f'/content/drive/MyDrive/pai_nosso_refatorado/pipeline/correcoes/{config.NOME_ORACAO}'
)

if not pasta_correcoes.exists():
    print(f"❌ Pasta não encontrada: {pasta_correcoes}")
else:
    ok, falta = [], []
    for lang in config.IDIOMAS:
        p = pasta_correcoes / f'classificacao_{config.NOME_ORACAO}_{lang}.json'
        (ok if p.exists() else falta).append(lang.upper())
        print(f"  {'✅' if p.exists() else '❌'} {p.name}")

    if len(ok) == 4:
        print("\n✅ Todos os 4 JSONs encontrados! Carregando...")
        pipeline.legendas_idiomas = pipeline.fase5b_recarregar()

        print("\n📋 Preview:")
        from constants import CORES_HTML
        for lang in config.IDIOMAS:
            legs = pipeline.legendas_idiomas.get(lang, [])
            if legs and legs[0].palavras:
                leg = legs[0]
                print(f'\n  {lang.upper()} — "{leg.texto[:50]}"')
                for p in leg.palavras[:4]:
                    sinal = '✅' if p.classe in CORES_HTML else '❌'
                    print(f'    {sinal} {p.texto:<18} {p.classe}')

        print("\n" + "═" * 65)
        print("🎬 Pronto — execute as Fases 6, 7 e 8")
        print("═" * 65)
    else:
        print(f"\n⚠️  Faltam: {', '.join(falta)}")
        print(f"   Coloque os JSONs corrigidos em: {pasta_correcoes}")

"""### ▶ Fases 6–8 — Vídeo final"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  FASES 6, 7 e 8 — Vídeo final                                 ║
# ╚══════════════════════════════════════════════════════════════════╝

video_final = pipeline.continuar()

if video_final:
    from IPython.display import Video, display
    print(f'\n🎬 Vídeo final: {video_final}')
    print(f'   Tamanho: {video_final.stat().st_size / 1_048_576:.1f} MB')
    display(Video(str(video_final), embed=True, width=800))

"""### 🚀 RUN ALL — Pipeline completo"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  RUN ALL                                                       ║
# ╚══════════════════════════════════════════════════════════════════╝

from video_pipeline import ClassificacaoPendenteError

resultado = pipeline.run(
    # from_phase='clipes_cortados'  # descomente para retomar de uma fase
)

if resultado is None:
    print('\n⏸️  Pausado na Fase 5A — execute o PACOTE DE REVISÃO, depois a FASE 5C.')
else:
    print(f'\n🎉 Vídeo final: {resultado}')
    print(pipeline._cp.resumo())

"""### 🔧 Utilitários"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  UTILITÁRIOS                                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

from checkpoint import Checkpoint
cp = Checkpoint()
print(cp.resumo())
pipeline._clf.imprimir_status()

# ── Checkpoint ─────────────────────────────────────────────────────────────
# cp.resetar_tudo()
# cp.reiniciar_de('classificacoes_feitas')

# ── Classificações ──────────────────────────────────────────────────────────
# pipeline._clf.imprimir_status()
# pipeline._clf.classificar_idioma(pipeline.legendas_idiomas['en'], 'en', forcar=True)

# ── Pacote manual (sem reclassificar) ───────────────────────────────────────
# pasta = pipeline._clf.exportar_pacote_revisao(pipeline.legendas_idiomas)
# print(f"📦 {pasta}")

# ── Verificar classes inválidas ─────────────────────────────────────────────
# from constants import CORES_HTML
# for lang, legs in pipeline.legendas_idiomas.items():
#     for leg in legs:
#         for p in leg.palavras:
#             if p.classe not in CORES_HTML:
#                 print(f'  [{lang.upper()} leg.{leg.id}] "{p.texto}" → {p.classe} ❌')

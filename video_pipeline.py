# -*- coding: utf-8 -*-
"""
video_pipeline.py — Orquestrador principal do pipeline.

Executa as 8 fases em sequência, salvando checkpoint após cada uma.
Pode ser retomado de qualquer fase com run(from_phase="nome_da_fase").

Uso rápido:
    from pipeline.config import PipelineConfig
    from pipeline.groq_client import GroqClient
    from pipeline.video_pipeline import VideoPipeline
    from google.colab import userdata

    config   = PipelineConfig()
    groq     = GroqClient(api_key=userdata.get("GROQ_KEY"))
    pipeline = VideoPipeline(config, groq)

    video_final = pipeline.run()
    # ou retomando de uma fase específica:
    video_final = pipeline.run(from_phase="clipes_cortados")
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from checkpoint import Checkpoint
from classification import Classifier
from config import PipelineConfig
from constants import IDIOMAS, FASES_PIPELINE
from drive_utils import DriveClient
from ffmpeg_utils import (
    FFmpegError,
    adicionar_audio,
    adicionar_credito_e_logo,
    adicionar_trilha_fundo,
    concatenar_videos,
    cortar_video,
    gerar_ass,
    obter_duracao,
    queimar_legendas_ass,
)
from groq_client import GroqClient
from models import Clipe, Legenda
from srt_utils import (
    eliminar_gaps,
    extrair_texto_unico,
    ler_srt,
    salvar_srt,
    sincronizar_timestamps,
)

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Erro geral do pipeline."""


class VideoPipeline:
    """
    Orquestrador do pipeline de vídeo com legendas morfológicas multilíngues.
    """

    def __init__(self, config: PipelineConfig, groq: GroqClient) -> None:
        config.validate()
        self._cfg   = config
        self._groq  = groq
        self._drive = DriveClient.get()
        self._cp    = Checkpoint()
        self._clf   = Classifier(config, groq)

    # ── Ponto de entrada ──────────────────────────────────────────────────────

    def run(self, from_phase: Optional[str] = None) -> Path:
        """
        Executa o pipeline completo (ou a partir de uma fase).

        Args:
            from_phase: Nome da fase a partir da qual executar.
                        Invalida essa fase e todas as posteriores no checkpoint.
                        Ex: "clipes_cortados"

        Returns:
            Path do vídeo final gerado.
        """
        if from_phase:
            logger.info("🔄 Reiniciando a partir de: %s", from_phase)
            self._cp.reiniciar_de(from_phase)

        logger.info("=" * 60)
        logger.info("▶  PIPELINE — %s", self._cfg.NOME_ORACAO.upper())
        logger.info("=" * 60)
        logger.info(self._cp.resumo())

        legendas_pt:     list[Legenda]              = []
        legendas_idiomas: dict[str, list[Legenda]]  = {}
        clipes:          list[Clipe]                = []

        # ── Fase 1: Áudio ─────────────────────────────────────────────────────
        if not self._cp.fase_concluida("audio_gerado"):
            self.fase1_gerar_audio()
        else:
            logger.info("⏭️  Fase 1 (áudio) já concluída — pulando")

        # ── Fase 2: SRT PT bruto ──────────────────────────────────────────────
        if not self._cp.fase_concluida("srt_pt_bruto"):
            self.fase2_transcrever_whisper()
        else:
            logger.info("⏭️  Fase 2 (Whisper) já concluída — pulando")

        # ── Fase 3: SRT PT corrigido ──────────────────────────────────────────
        if not self._cp.fase_concluida("srt_pt_corrigido"):
            legendas_pt = self.fase3_corrigir_pt()
        else:
            logger.info("⏭️  Fase 3 (correção PT) já concluída — carregando SRT")
            legendas_pt = ler_srt(self._cfg.NOME_SRT_PT)

        # ── Fase 4: Traduções EN/ES/FR ────────────────────────────────────────
        if not self._cp.fase_concluida("srt_traduzidos"):
            legendas_idiomas = self.fase4_traduzir(legendas_pt)
        else:
            logger.info("⏭️  Fase 4 (traduções) já concluída — carregando SRTs")
            legendas_idiomas = self._carregar_todos_srts(legendas_pt)

        # ── Fase 5: Classificação morfológica ─────────────────────────────────
        if not self._cp.fase_concluida("classificacoes_feitas"):
            legendas_idiomas = self.fase5_classificar(legendas_idiomas)
        else:
            logger.info("⏭️  Fase 5 (classificação) já concluída — carregando JSONs")
            legendas_idiomas = self._carregar_classificacoes(legendas_idiomas)

        # ── Fase 6: Clipes ────────────────────────────────────────────────────
        if not self._cp.fase_concluida("clipes_cortados"):
            clipes = self.fase6_baixar_clipes(legendas_pt)
        else:
            logger.info("⏭️  Fase 6 (clipes) já concluída — usando metadados")
            clipes = self._clipes_do_checkpoint()

        # ── Fase 7: Vídeo base ────────────────────────────────────────────────
        if not self._cp.fase_concluida("video_base_criado"):
            self.fase7_criar_video_base(clipes)
        else:
            logger.info("⏭️  Fase 7 (vídeo base) já concluída — pulando")

        # ── Fase 8: Queimar legendas ──────────────────────────────────────────
        if not self._cp.fase_concluida("legendas_queimadas"):
            video_final = self.fase8_queimar_legendas(legendas_idiomas)
        else:
            logger.info("⏭️  Fase 8 (legendas) já concluída")
            video_final = Path(self._cfg.NOME_VIDEO_FINAL)

        logger.info("=" * 60)
        logger.info("🎉 PIPELINE CONCLUÍDO: %s", video_final)
        logger.info("=" * 60)
        return video_final

    # ── Fase 1: Gerar áudio ───────────────────────────────────────────────────

    def fase1_gerar_audio(self) -> Path:
        """Gera áudio com Edge TTS e salva no Drive."""
        import edge_tts

        logger.info("── Fase 1: Gerando áudio com Edge TTS")
        audio_path = Path(self._cfg.NOME_AUDIO)

        async def _gerar():
            for tentativa in range(1, 4):
                try:
                    comm = edge_tts.Communicate(self._cfg.TEXTO_ORACAO, self._cfg.VOZ_EDGE)
                    await comm.save(str(audio_path))
                    return
                except Exception as exc:
                    logger.warning("Edge TTS tentativa %d/3: %s", tentativa, exc)
                    await asyncio.sleep(2)
            raise PipelineError("Edge TTS falhou após 3 tentativas")

        asyncio.get_event_loop().run_until_complete(_gerar())

        tamanho_mb = audio_path.stat().st_size / 1_048_576
        logger.info("✅ Áudio gerado: %s (%.2f MB)", audio_path.name, tamanho_mb)

        self._drive.upload(audio_path, self._cfg.ID_PASTA_AUDIO, "audio/wav")
        self._cp.salvar("audio_gerado", {"arquivo": str(audio_path)})
        return audio_path

    # ── Fase 2: Transcrever com Whisper ───────────────────────────────────────

    def fase2_transcrever_whisper(self) -> Path:
        """Transcreve o áudio com Whisper e salva o SRT bruto."""
        import whisper

        logger.info("── Fase 2: Transcrevendo com Whisper")
        audio_path = Path(self._cfg.NOME_AUDIO)

        if not audio_path.exists():
            self._drive.download(self._cfg.ID_PASTA_AUDIO, self._cfg.NOME_AUDIO, audio_path)

        model    = whisper.load_model("base")
        resultado = model.transcribe(str(audio_path), language="pt", word_timestamps=True)

        # constrói legendas a partir dos segmentos do Whisper
        legendas: list[Legenda] = []
        for seg in resultado["segments"]:
            legendas.append(Legenda(
                id        = len(legendas) + 1,
                inicio_ms = int(seg["start"] * 1000),
                fim_ms    = int(seg["end"]   * 1000),
                texto     = seg["text"].strip(),
            ))

        srt_edge = Path(self._cfg.NOME_SRT_PT_EDGE)
        salvar_srt(legendas, srt_edge)
        logger.info("✅ SRT bruto: %s (%d segmentos)", srt_edge.name, len(legendas))

        self._cp.salvar("srt_pt_bruto", {"segmentos": len(legendas)})
        return srt_edge

    # ── Fase 3: Corrigir PT ───────────────────────────────────────────────────

    def fase3_corrigir_pt(self) -> list[Legenda]:
        """Corrige o SRT bruto com Groq e elimina gaps."""
        logger.info("── Fase 3: Corrigindo texto PT com Groq")
        srt_edge = Path(self._cfg.NOME_SRT_PT_EDGE)

        if not srt_edge.exists():
            raise PipelineError(f"SRT bruto não encontrado: {srt_edge}")

        legendas = ler_srt(srt_edge)
        legendas = self._groq.corrigir_texto_pt(legendas)
        legendas = eliminar_gaps(legendas)

        srt_pt = Path(self._cfg.NOME_SRT_PT)
        salvar_srt(legendas, srt_pt)
        self._drive.upload(srt_pt, self._cfg.ID_PASTA_LEGENDAS, "text/plain")
        logger.info("✅ SRT PT corrigido: %s (%d legendas)", srt_pt.name, len(legendas))

        self._cp.salvar("srt_pt_corrigido", {"legendas": len(legendas)})
        return legendas

    # ── Fase 4: Traduzir EN/ES/FR ─────────────────────────────────────────────

    def fase4_traduzir(
        self, legendas_pt: list[Legenda]
    ) -> dict[str, list[Legenda]]:
        """Redistribui e revisa vocabulário litúrgico para EN, ES e FR."""
        logger.info("── Fase 4: Traduzindo EN/ES/FR com Groq")
        idiomas_traduzir = [lang for lang in self._cfg.IDIOMAS if lang != "pt"]
        legendas_idiomas: dict[str, list[Legenda]] = {"pt": legendas_pt}

        for lang in idiomas_traduzir:
            logger.info("   📝 %s...", lang.upper())

            # tenta carregar SRT do YouTube (célula B0 opcional)
            srt_yt = Path(self._cfg.nome_srt(lang))
            if srt_yt.exists():
                legendas_yt  = ler_srt(srt_yt)
                texto_corrido = extrair_texto_unico(legendas_yt)
            else:
                # sem referência do YouTube — Groq traduz do zero
                texto_corrido = " ".join(leg.texto for leg in legendas_pt)
                logger.warning("   ⚠️  SRT YouTube não encontrado para %s — usando PT como base", lang)

            segmentos = self._groq.redistribuir_traducoes(
                texto_corrido, legendas_pt, lang
            )
            segmentos = self._groq.revisar_vocabulario_liturgico(segmentos, lang)

            legendas_lang: list[Legenda] = []
            for i, (leg_pt, texto) in enumerate(zip(legendas_pt, segmentos)):
                legendas_lang.append(Legenda(
                    id        = i + 1,
                    inicio_ms = leg_pt.inicio_ms,
                    fim_ms    = leg_pt.fim_ms,
                    texto     = texto,
                ))

            legendas_idiomas[lang] = legendas_lang
            srt_out = Path(self._cfg.nome_srt(lang))
            salvar_srt(legendas_lang, srt_out)
            self._drive.upload(srt_out, self._cfg.ID_PASTA_LEGENDAS, "text/plain")
            logger.info("   ✅ %s: %d legendas", lang.upper(), len(legendas_lang))

        self._cp.salvar("srt_traduzidos", {
            "idiomas": list(legendas_idiomas.keys())
        })
        return legendas_idiomas

    # ── Fase 5: Classificar morfologicamente ─────────────────────────────────

    def fase5_classificar(
        self, legendas_idiomas: dict[str, list[Legenda]]
    ) -> dict[str, list[Legenda]]:
        """Classifica morfologicamente cada idioma (com cache local)."""
        logger.info("── Fase 5: Classificação morfológica")

        for lang, legendas in legendas_idiomas.items():
            logger.info("   🏷️  %s...", lang.upper())
            legendas_idiomas[lang] = self._clf.classificar_idioma(legendas, lang)
            # upload do JSON para o Drive
            json_path = Path(self._cfg.nome_classificacao(lang))
            self._drive.upload(json_path, self._cfg.ID_PASTA_CLASSIFICACAO, "application/json")

        self._cp.salvar("classificacoes_feitas", {
            "idiomas": list(legendas_idiomas.keys())
        })
        return legendas_idiomas

    # ── Fase 6: Baixar e cortar clipes ────────────────────────────────────────

    def fase6_baixar_clipes(self, legendas_pt: list[Legenda]) -> list[Clipe]:
        """Baixa clipes da planilha Google Sheets e corta para DURACAO_CLIPE segundos."""
        logger.info("── Fase 6: Baixando e cortando clipes")

        duracao_total = max(leg.fim_seg for leg in legendas_pt)
        num_clipes    = max(1, int(duracao_total / self._cfg.DURACAO_CLIPE) + 1)

        logger.info("   Duração total: %.1fs → %d clipes necessários", duracao_total, num_clipes)

        url_csv = (
            f"https://docs.google.com/spreadsheets/d/"
            f"{self._cfg.ID_PLANILHA_DRIVE}/export?format=csv"
        )
        df = pd.read_csv(url_csv)

        if len(df) < num_clipes:
            raise PipelineError(
                f"Planilha tem {len(df)} clipes, precisamos de {num_clipes}"
            )

        df_sel = df.head(num_clipes)
        clipes = [
            Clipe(
                url    = str(row["url"]),
                autor  = str(row.get("Autor", "Pixabay")),
                indice = idx,
            )
            for idx, (_, row) in enumerate(df_sel.iterrows())
        ]

        Path("clipes_cortados").mkdir(exist_ok=True)
        Path("temp_raw").mkdir(exist_ok=True)

        # processa em paralelo com ThreadPoolExecutor
        processados: list[Clipe] = []
        with ThreadPoolExecutor(max_workers=self._cfg.FFMPEG_NUM_THREADS) as executor:
            futures = {
                executor.submit(self._processar_clipe, clipe): clipe
                for clipe in clipes
            }
            for future in as_completed(futures):
                clipe = futures[future]
                try:
                    result = future.result()
                    if result:
                        processados.append(result)
                        logger.info(
                            "   ✅ [%d/%d] %s",
                            len(processados), num_clipes, clipe.autor,
                        )
                except Exception as exc:
                    logger.warning("   ❌ Clipe %d falhou: %s", clipe.indice, exc)

        if not processados:
            raise PipelineError("Nenhum clipe processado com sucesso")

        self._cp.salvar("clipes_cortados", {
            "total": len(processados),
            "clipes": [
                {"indice": c.indice, "arquivo": c.arquivo_pronto, "autor": c.autor}
                for c in processados
            ],
        })
        return processados

    def _processar_clipe(self, clipe: Clipe) -> Optional[Clipe]:
        """Baixa e corta um único clipe (executado em thread)."""
        raw   = Path(f"temp_raw/raw_{clipe.indice}.mp4")
        saida = Path(f"clipes_cortados/clipe_{clipe.indice:03d}.mp4")

        # download HTTP
        try:
            r = requests.get(
                clipe.url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self._cfg.DOWNLOAD_TIMEOUT,
                stream=True,
            )
            r.raise_for_status()
            with open(raw, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
        except Exception as exc:
            logger.debug("Download falhou para clipe %d: %s", clipe.indice, exc)
            return None

        if not raw.exists() or raw.stat().st_size < 1000:
            return None

        try:
            cortar_video(raw, saida, self._cfg.DURACAO_CLIPE)
        except FFmpegError as exc:
            logger.debug("Corte falhou para clipe %d: %s", clipe.indice, exc)
            raw.unlink(missing_ok=True)
            return None

        raw.unlink(missing_ok=True)

        if saida.exists() and saida.stat().st_size > 1000:
            clipe.arquivo_local  = str(saida)
            clipe.arquivo_pronto = str(saida)  # ainda sem crédito; é adicionado na fase 7
            return clipe
        return None

    # ── Fase 7: Criar vídeo base ──────────────────────────────────────────────

    def fase7_criar_video_base(self, clipes: list[Clipe]) -> Path:
        """Adiciona crédito/logo, concatena, adiciona narração e trilha."""
        logger.info("── Fase 7: Criando vídeo base")

        logo_path = Path("logo_baixada.png")
        self._drive.download_se_ausente(
            self._cfg.ID_PASTA_LOGO, self._cfg.NOME_ARQUIVO_LOGO, logo_path
        )
        if not logo_path.exists():
            logo_path = None  # type: ignore

        # 7a: adicionar crédito e logo a cada clipe
        Path("clipes_prontos").mkdir(exist_ok=True)
        arquivos_prontos: list[Path] = []

        for clipe in sorted(clipes, key=lambda c: c.indice):
            entrada = Path(clipe.arquivo_pronto)
            saida   = Path(f"clipes_prontos/clipe_{clipe.indice:03d}.mp4")
            adicionar_credito_e_logo(
                entrada, saida,
                f"Pixabay / {clipe.autor}",
                logo_path,
                self._cfg.TAMANHO_LOGO,
            )
            arquivos_prontos.append(saida)

        # 7b: concatenar
        video_sem_audio = Path("video_sem_audio.mp4")
        concatenar_videos(arquivos_prontos, video_sem_audio)

        # 7c: baixar áudio do Drive e adicionar
        audio_path = Path(self._cfg.NOME_AUDIO)
        self._drive.download_se_ausente(
            self._cfg.ID_PASTA_AUDIO, self._cfg.NOME_AUDIO, audio_path
        )
        video_com_audio = Path("video_com_audio.mp4")
        adicionar_audio(video_sem_audio, audio_path, video_com_audio)
        video_sem_audio.unlink(missing_ok=True)

        # 7d: baixar trilha e mixar
        musica_path = Path(self._cfg.NOME_ARQUIVO_MUSICA)
        self._drive.download_se_ausente(
            self._cfg.ID_PASTA_MUSICA, self._cfg.NOME_ARQUIVO_MUSICA, musica_path
        )
        video_base = Path(self._cfg.NOME_VIDEO_BASE)
        if musica_path.exists():
            adicionar_trilha_fundo(video_com_audio, musica_path, video_base, self._cfg.VOLUME_MUSICA)
            video_com_audio.unlink(missing_ok=True)
        else:
            video_com_audio.rename(video_base)
            logger.warning("Trilha não encontrada — vídeo base sem música de fundo")

        # upload do vídeo base
        self._drive.upload(video_base, self._cfg.ID_PASTA_VIDEOS, "video/mp4")
        logger.info("✅ Vídeo base: %s (%.2f MB)", video_base.name, video_base.stat().st_size / 1_048_576)

        self._cp.salvar("video_base_criado", {"arquivo": str(video_base)})
        return video_base

    # ── Fase 8: Queimar legendas ASS ──────────────────────────────────────────

    def fase8_queimar_legendas(
        self, legendas_idiomas: dict[str, list[Legenda]]
    ) -> Path:
        """Gera o arquivo ASS e queima as legendas coloridas no vídeo final."""
        logger.info("── Fase 8: Queimando legendas ASS")

        video_base = Path(self._cfg.NOME_VIDEO_BASE)
        if not video_base.exists():
            raise PipelineError(f"Vídeo base não encontrado: {video_base}")

        # garante que os timestamps de todos os idiomas estão sincronizados com o PT
        legendas_pt = legendas_idiomas.get("pt", [])
        for lang, legendas in legendas_idiomas.items():
            if lang != "pt" and legendas_pt:
                sincronizar_timestamps(legendas, legendas_pt)

        # gera arquivo ASS único com todos os idiomas
        ass_path = gerar_ass(
            legendas_idiomas,
            self._cfg,
            caminho_saida=Path(f"legendas_{self._cfg.NOME_ORACAO}.ass"),
        )
        logger.info("   ASS gerado: %s", ass_path.name)

        # render final
        video_final = Path(self._cfg.NOME_VIDEO_FINAL)
        queimar_legendas_ass(video_base, ass_path, video_final)

        tamanho_mb = video_final.stat().st_size / 1_048_576
        logger.info("✅ Vídeo final: %s (%.2f MB)", video_final.name, tamanho_mb)

        self._drive.upload(video_final, self._cfg.ID_PASTA_VIDEOS, "video/mp4")
        self._cp.salvar("legendas_queimadas", {"arquivo": str(video_final)})
        return video_final

    # ── Helpers de carregamento ───────────────────────────────────────────────

    def _carregar_todos_srts(
        self, legendas_pt: list[Legenda]
    ) -> dict[str, list[Legenda]]:
        """Carrega todos os SRTs do disco (fallback quando fase 4 já concluída)."""
        resultado: dict[str, list[Legenda]] = {"pt": legendas_pt}
        for lang in self._cfg.IDIOMAS:
            if lang == "pt":
                continue
            srt_path = Path(self._cfg.nome_srt(lang))
            if srt_path.exists():
                resultado[lang] = ler_srt(srt_path)
            else:
                # tenta baixar do Drive
                self._drive.download(self._cfg.ID_PASTA_LEGENDAS, srt_path.name, srt_path)
                if srt_path.exists():
                    resultado[lang] = ler_srt(srt_path)
                else:
                    logger.warning("SRT não encontrado para %s — usando PT como fallback", lang)
                    resultado[lang] = legendas_pt
        return resultado

    def _carregar_classificacoes(
        self, legendas_idiomas: dict[str, list[Legenda]]
    ) -> dict[str, list[Legenda]]:
        """Carrega JSONs de classificação do disco (fallback quando fase 5 já concluída)."""
        for lang, legendas in legendas_idiomas.items():
            json_path = Path(self._cfg.nome_classificacao(lang))
            if not json_path.exists():
                self._drive.download(
                    self._cfg.ID_PASTA_CLASSIFICACAO, json_path.name, json_path
                )
            if json_path.exists():
                self._clf._carregar_cache(json_path, legendas)
            else:
                logger.warning("JSON de classificação não encontrado para %s", lang)
        return legendas_idiomas

    def _clipes_do_checkpoint(self) -> list[Clipe]:
        """Reconstrói a lista de Clipe a partir dos metadados do checkpoint."""
        meta   = self._cp.metadados("clipes_cortados")
        clipes = []
        for item in meta.get("clipes", []):
            c = Clipe(
                url              = "",
                autor            = item.get("autor", "Pixabay"),
                indice           = item.get("indice", 0),
                arquivo_pronto   = item.get("arquivo"),
            )
            clipes.append(c)
        return clipes

    # ── Limpeza ───────────────────────────────────────────────────────────────

    def limpar_temporarios(self) -> None:
        """Remove pastas e arquivos temporários do workspace."""
        pastas = ["clipes_cortados", "clipes_prontos", "temp_raw"]
        for pasta in pastas:
            p = Path(pasta)
            if p.exists():
                shutil.rmtree(p)
                logger.info("🗑️ Removido: %s/", pasta)

        arquivos = [
            "clipes_info.json", "videos_prontos.json", "lista_concat.txt",
            "logo_baixada.png", "video_com_audio.mp4", "video_sem_audio.mp4",
        ]
        for arq in arquivos:
            p = Path(arq)
            if p.exists():
                p.unlink()
                logger.info("🗑️ Removido: %s", arq)

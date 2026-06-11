# -*- coding: utf-8 -*-
"""
classification.py — Classificação morfológica com cache local.

O cache evita reprocessar via Groq se o JSON já existir e for válido.
Ao mudar o SRT, chame invalidar_cache(lang) para forçar reclassificação.

Uso:
    from classification import Classifier
    clf = Classifier(config, groq_client)
    legendas = clf.classificar_idioma(legendas_pt, "pt")
    clf.salvar_json(legendas, "pt")
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from config import PipelineConfig
from groq_client import GroqClient
from models import Legenda, Palavra

logger = logging.getLogger(__name__)


class ClassificationError(Exception):
    """Erro na classificação morfológica."""


class Classifier:
    """Gerencia a classificação morfológica com cache JSON em disco."""

    def __init__(self, config: PipelineConfig, groq: GroqClient) -> None:
        self._cfg  = config
        self._groq = groq

    # ── Interface pública ─────────────────────────────────────────────────────

    def classificar_idioma(
        self,
        legendas: list[Legenda],
        lang: str,
        forcar: bool = False,
    ) -> list[Legenda]:
        """
        Classifica morfologicamente todas as legendas de um idioma.

        Se o JSON de cache existir e for válido, carrega sem chamar o Groq.
        Com forcar=True, reclassifica mesmo se o cache existir.

        Returns:
            As mesmas legendas com o campo `palavras` preenchido in-place.
        """
        caminho_json = Path(self._cfg.nome_classificacao(lang))

        # tenta carregar do cache
        if not forcar and caminho_json.exists():
            carregado = self._carregar_cache(caminho_json, legendas)
            if carregado:
                logger.info("✅ Classificação %s: cache carregado (%s)", lang.upper(), caminho_json.name)
                return legendas
            logger.warning("Cache inválido para %s — reclassificando", lang)

        # chama o Groq
        logger.info("🤖 Classificando %s: %d legendas via Groq...", lang.upper(), len(legendas))
        self._classificar_via_groq(legendas, lang)

        # salva cache
        self.salvar_json(legendas, lang)
        return legendas

    def salvar_json(self, legendas: list[Legenda], lang: str) -> Path:
        """
        Serializa as classificações em JSON compatível com o formato legado.
        Formato: { "1": { "inicio": ..., "fim": ..., "texto_original": ..., "palavras": [...] } }
        """
        caminho = Path(self._cfg.nome_classificacao(lang))
        dados: dict[str, dict] = {}

        for leg in legendas:
            dados[str(leg.id)] = {
                "inicio":          leg.inicio_str,
                "fim":             leg.fim_str,
                "texto_original":  leg.texto,
                "palavras": [
                    {"texto": p.texto, "classe": p.classe}
                    for p in leg.palavras
                ],
            }

        caminho.write_text(
            json.dumps(dados, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("💾 JSON salvo: %s (%d legendas)", caminho.name, len(legendas))
        return caminho

    def carregar_json(self, lang: str) -> dict[str, dict]:
        """Carrega o JSON de classificação do disco (formato legado)."""
        caminho = Path(self._cfg.nome_classificacao(lang))
        if not caminho.exists():
            raise ClassificationError(f"JSON de classificação não encontrado: {caminho}")
        try:
            texto = caminho.read_text(encoding="utf-8-sig")
            return json.loads(texto)
        except (json.JSONDecodeError, OSError) as exc:
            raise ClassificationError(f"JSON corrompido: {caminho}: {exc}") from exc

    def invalidar_cache(self, lang: str) -> None:
        """Remove o JSON de cache para forçar reclassificação."""
        caminho = Path(self._cfg.nome_classificacao(lang))
        if caminho.exists():
            caminho.unlink()
            logger.info("🗑️ Cache invalidado: %s", caminho.name)

    def sincronizar_timestamps(
        self,
        lang: str,
        legendas_mestre: list[Legenda],
    ) -> None:
        """
        Atualiza os timestamps no JSON de cache usando os timestamps do PT corrigido.
        Necessário quando o SRT PT é corrigido depois de o JSON ter sido gerado.
        """
        caminho = Path(self._cfg.nome_classificacao(lang))
        if not caminho.exists():
            return

        try:
            dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            return

        for leg in legendas_mestre:
            chave = str(leg.id)
            if chave in dados:
                dados[chave]["inicio"] = leg.inicio_str
                dados[chave]["fim"]    = leg.fim_str

        caminho.write_text(
            json.dumps(dados, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("🔄 Timestamps sincronizados no JSON: %s", caminho.name)

    # ── Internos ──────────────────────────────────────────────────────────────

    def _classificar_via_groq(self, legendas: list[Legenda], lang: str) -> None:
        """Chama o Groq para cada legenda e preenche leg.palavras in-place."""
        for i, leg in enumerate(legendas):
            logger.info(
                "  [%d/%d] %s: '%s'",
                i + 1, len(legendas), lang.upper(), leg.texto[:50],
            )
            leg.palavras = self._groq.classificar_legenda(leg.texto, lang)
            logger.debug("        → %d palavras", len(leg.palavras))
            # sleep extra após cada legenda para respeitar rate limit
            time.sleep(0.3)

    def _carregar_cache(
        self,
        caminho: Path,
        legendas: list[Legenda],
    ) -> bool:
        """
        Carrega o cache JSON e preenche leg.palavras.
        Retorna False se o cache não for válido ou estiver incompleto.
        """
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cache ilegível (%s): %s", caminho.name, exc)
            return False

        if not dados:
            return False

        mapa: dict[int, list[Palavra]] = {}
        for chave, entrada in dados.items():
            try:
                lid = int(chave)
            except ValueError:
                continue
            palavras_raw = entrada.get("palavras", [])
            mapa[lid] = [
                Palavra(texto=p.get("texto", ""), classe=p.get("classe", ""))
                for p in palavras_raw
                if p.get("texto")
            ]

        # verifica cobertura mínima: pelo menos metade das legendas com palavras
        com_palavras = sum(1 for leg in legendas if leg.id in mapa and mapa[leg.id])
        if com_palavras < len(legendas) // 2:
            logger.warning(
                "Cache cobre apenas %d/%d legendas — considerado inválido",
                com_palavras, len(legendas),
            )
            return False

        for leg in legendas:
            if leg.id in mapa:
                leg.palavras = mapa[leg.id]

        return True

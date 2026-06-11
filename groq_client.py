# -*- coding: utf-8 -*-
"""
groq_client.py — Cliente Groq com retry automático e funções específicas.

Funções principais:
    corrigir_texto_pt(legendas)            → aplica correções in-place
    redistribuir_traducoes(texto, legendas_pt, lang) → list[str]
    revisar_vocabulario_liturgico(segmentos, lang)   → list[str]
    classificar_legenda(texto, lang)        → list[Palavra]

Todas as chamadas têm:
    - Retry com backoff (até 3 tentativas)
    - Sleep de 2s entre chamadas para respeitar rate limit do Groq free tier
    - JSON parsing robusto (remove markdown code fences automaticamente)
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

from models import Legenda, Palavra
from constants import (
    MAPEAMENTO_CLASSES, FASES_PIPELINE,
    PROMPT_SISTEMA_CORRECAO_PT,
    PROMPT_SISTEMA_REDISTRIBUICAO,
    PROMPT_SISTEMA_REVISAO_LITURGICA,
    PROMPT_SISTEMA_CLASSIFICACAO,
    EXEMPLOS_LITURGICOS,
    NOMES_IDIOMA,
    CORES_HTML,
)

logger = logging.getLogger(__name__)


class GroqError(Exception):
    """Erro nas chamadas à API do Groq."""


class GroqClient:
    """
    Wrapper sobre a API do Groq (compatível com OpenAI).
    Instanciar com a GROQ_KEY obtida de userdata.get('GROQ_KEY').
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        max_tentativas: int = 3,
        delay_entre_calls: float = 2.0,
    ) -> None:
        if not api_key:
            raise GroqError("GROQ_KEY não fornecida")

        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        self.model              = model
        self.max_tentativas     = max_tentativas
        self.delay_entre_calls  = delay_entre_calls

    # ── Chamada base ──────────────────────────────────────────────────────────

    def call(
        self,
        user_prompt: str,
        system_prompt: str = "Você é um assistente útil.",
        max_tokens: int = 1000,
        temperature: float = 0.1,
    ) -> str:
        """
        Chama o modelo Groq com retry automático.

        Returns:
            Texto bruto da resposta.

        Raises:
            GroqError: Se todas as tentativas falharem.
        """
        ultimo_erro: Exception | None = None

        for tentativa in range(1, self.max_tentativas + 1):
            try:
                resposta = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                texto = resposta.choices[0].message.content.strip()
                time.sleep(self.delay_entre_calls)
                return texto

            except Exception as exc:
                ultimo_erro = exc
                logger.warning(
                    "Groq tentativa %d/%d falhou: %s",
                    tentativa, self.max_tentativas, str(exc)[:80],
                )
                if tentativa < self.max_tentativas:
                    time.sleep(self.delay_entre_calls * tentativa)  # backoff crescente

        raise GroqError(f"Groq falhou após {self.max_tentativas} tentativas: {ultimo_erro}")

    def call_json(
        self,
        user_prompt: str,
        system_prompt: str,
        max_tokens: int = 1000,
    ) -> dict | list:
        """
        Chama o modelo e faz parse do JSON retornado.
        Remove markdown code fences automaticamente.

        Raises:
            GroqError: Se não conseguir parsear JSON válido.
        """
        texto = self.call(user_prompt, system_prompt, max_tokens)
        return _parse_json(texto)

    # ── Correção de PT ────────────────────────────────────────────────────────

    def corrigir_texto_pt(self, legendas: list[Legenda]) -> list[Legenda]:
        """
        Corrige erros de transcrição do Whisper no texto PT.
        Aplica as correções in-place nas legendas.

        Erros comuns: "Perdua aí" → "Perdoai", "a mim" → "Amém", etc.
        """
        n = len(legendas)
        textos_numerados = "\n".join(
            f"{i + 1}. {leg.texto}" for i, leg in enumerate(legendas)
        )

        user_prompt = (
            f"Corrija os erros de transcrição nestas frases do Pai Nosso em português.\n"
            f"Erros comuns do Whisper: 'Perdua aí' → 'Perdoai', "
            f"'perduamos' → 'perdoamos', 'a mim' → 'Amém'.\n"
            f"Mantenha exatamente {n} frases na mesma ordem.\n\n"
            f"Frases:\n{textos_numerados}"
        )

        try:
            correcoes = self.call_json(user_prompt, PROMPT_SISTEMA_CORRECAO_PT)
        except GroqError as exc:
            logger.warning("Falha ao corrigir PT: %s — mantendo original", exc)
            return legendas

        for corr in (correcoes if isinstance(correcoes, list) else []):
            idx = int(corr.get("id", 0)) - 1
            if 0 <= idx < n:
                texto_antigo = legendas[idx].texto
                novo_texto   = corr.get("texto", texto_antigo)
                if texto_antigo != novo_texto:
                    logger.debug("  ✏️  #%d: '%s' → '%s'", idx + 1, texto_antigo, novo_texto)
                    legendas[idx].texto = novo_texto

        logger.info("corrigir_texto_pt: %d legendas processadas", n)
        return legendas

    # ── Redistribuição de traduções ───────────────────────────────────────────

    def redistribuir_traducoes(
        self,
        texto_corrido: str,
        legendas_pt: list[Legenda],
        lang: str,
    ) -> list[str]:
        """
        Redistribui o texto corrido de um idioma nos mesmos N cortes do PT.

        Returns:
            Lista de strings, uma por legenda, no idioma solicitado.
        """
        n           = len(legendas_pt)
        nome_idioma = NOMES_IDIOMA.get(lang, lang)
        frases_pt   = "\n".join(
            f"{i + 1}. {leg.texto}" for i, leg in enumerate(legendas_pt)
        )

        system = PROMPT_SISTEMA_REDISTRIBUICAO.format(N=n, idioma=nome_idioma)
        user   = (
            f"Texto completo em {nome_idioma}:\n{texto_corrido}\n\n"
            f"Segmentação de referência em português ({n} frases):\n{frases_pt}\n\n"
            f"Redistribua em exatamente {n} segmentos. Cada segmento deve corresponder "
            f"semanticamente ao segmento PT de mesmo número."
        )

        try:
            segmentos = self.call_json(user, system, max_tokens=600)
        except GroqError as exc:
            logger.warning("Falha na redistribuição (%s): %s", lang, exc)
            return [leg.texto for leg in legendas_pt]

        resultado = _extrair_textos(segmentos, n, legendas_pt)
        logger.info("redistribuir_traducoes(%s): %d segmentos", lang, len(resultado))
        return resultado

    def revisar_vocabulario_liturgico(
        self,
        segmentos: list[str],
        lang: str,
    ) -> list[str]:
        """
        Revisa o vocabulário para usar termos litúrgicos clássicos.
        Ex: en: "hallowed", "trespass"; es: "santificado", "deudas".
        """
        n           = len(segmentos)
        nome_idioma = NOMES_IDIOMA.get(lang, lang)
        exemplos    = EXEMPLOS_LITURGICOS.get(lang, "")
        texto_num   = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(segmentos))

        system = PROMPT_SISTEMA_REVISAO_LITURGICA.format(
            idioma=nome_idioma, exemplos=exemplos, N=n
        )
        user = (
            f"Revise o vocabulário litúrgico destas {n} frases em {nome_idioma}.\n"
            f"Apenas substitua termos modernos por equivalentes clássicos quando necessário.\n"
            f"Não altere estrutura ou número de frases.\n\nFrases:\n{texto_num}"
        )

        try:
            revisados = self.call_json(user, system, max_tokens=600)
        except GroqError as exc:
            logger.warning("Falha na revisão litúrgica (%s): %s", lang, exc)
            return segmentos

        resultado = _extrair_textos(revisados, n, None)
        if len(resultado) != n:
            logger.warning(
                "Revisão litúrgica (%s) retornou %d itens, esperado %d — revertendo",
                lang, len(resultado), n
            )
            return segmentos
        return resultado

    # ── Classificação morfológica ─────────────────────────────────────────────

    def classificar_legenda(self, texto: str, lang: str) -> list[Palavra]:
        """
        Classifica morfologicamente cada palavra de uma legenda.

        Returns:
            Lista de Palavra com texto e classe.
        """
        classes_disponiveis = "\n".join(
            f"- {c}" for c in sorted(CORES_HTML.keys())
        )
        user = (
            f"Idioma: {NOMES_IDIOMA.get(lang, lang)}\n"
            f"Legenda: {texto}\n\n"
            f"Classes disponíveis:\n{classes_disponiveis}\n\n"
            f"JSON:"
        )

        try:
            resultado = self.call_json(user, PROMPT_SISTEMA_CLASSIFICACAO, max_tokens=600)
        except GroqError as exc:
            logger.warning("Falha na classificação: '%s': %s", texto[:40], exc)
            return _palavras_sem_classe(texto)

        palavras_raw = resultado.get("palavras", []) if isinstance(resultado, dict) else []
        palavras: list[Palavra] = []

        for p in palavras_raw:
            texto_p  = str(p.get("texto", "")).strip()
            classe_p = _normalizar_classe(str(p.get("classe", "")).strip().lower())
            if texto_p:
                palavras.append(Palavra(texto=texto_p, classe=classe_p))

        if not palavras:
            logger.warning("Classificação vazia para: '%s'", texto[:40])
            return _palavras_sem_classe(texto)

        return palavras


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_json(texto: str) -> dict | list:
    """Remove markdown code fences e faz parse de JSON."""
    limpo = re.sub(r"```json|```", "", texto).strip()
    try:
        return json.loads(limpo)
    except json.JSONDecodeError as exc:
        # tenta extrair o primeiro array/objeto JSON da resposta
        match = re.search(r"(\[.*\]|\{.*\})", limpo, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise GroqError(f"JSON inválido na resposta Groq: {exc}\nTexto: {limpo[:200]}") from exc


def _normalizar_classe(classe: str) -> str:
    """Normaliza nome de classe usando o mapeamento de compatibilidade."""
    return MAPEAMENTO_CLASSES.get(classe, classe)


def _extrair_textos(
    segmentos: list | dict,
    n: int,
    fallback: Optional[list[Legenda]],
) -> list[str]:
    """
    Extrai lista de strings de um retorno Groq (array de {id, texto}).
    Completa com o fallback se o resultado for menor que n.
    """
    if isinstance(segmentos, list):
        textos = [str(s.get("texto", "")) for s in segmentos if isinstance(s, dict)]
    else:
        textos = []

    # preenche se ficou curto
    while len(textos) < n:
        if fallback and len(textos) < len(fallback):
            textos.append(fallback[len(textos)].texto)
        else:
            textos.append(textos[-1] if textos else "")

    return textos[:n]


def _palavras_sem_classe(texto: str) -> list[Palavra]:
    """Retorna palavras do texto com classe desconhecida (fallback)."""
    return [
        Palavra(texto=t, classe="substantivo_masculino_singular")
        for t in texto.split()
        if t
    ]

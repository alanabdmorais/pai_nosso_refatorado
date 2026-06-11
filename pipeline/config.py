# -*- coding: utf-8 -*-
"""
config.py — Configuração centralizada do pipeline.
Altere NOME_ORACAO e TEXTO_ORACAO para reutilizar com outra oração.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from constants import (
    IDIOMAS, SIGLAS_IDIOMAS, POSICOES_Y, POS_SIGLA_Y,
    CORES_HTML, TEXTO_PRETO, LARGURA_TELA, ALTURA_TELA,
    TAMANHO_FONTE_TAG, TAMANHO_FONTE_SIGLA, BOX_BORDER,
    ESPACAMENTO_PALAVRA, LARGURA_CHAR,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """
    Configuração completa do pipeline.

    Para trocar a oração basta alterar NOME_ORACAO e TEXTO_ORACAO.
    Todos os nomes de arquivo são derivados automaticamente.
    """

    # ── Identidade da oração ──────────────────────────────────────────────────
    NOME_ORACAO: str = "pai_nosso"
    TEXTO_ORACAO: str = (
        "Pai Nosso que estais no céu,\n"
        "santificado seja o vosso nome.\n"
        "Venha a nós o vosso reino.\n"
        "Seja feita a vossa vontade,\n"
        "assim na terra como no céu.\n"
        "O pão nosso de cada dia nos dai hoje.\n"
        "Perdoai as nossas ofensas,\n"
        "assim como nós perdoamos a quem nos tem ofendido.\n"
        "E não nos deixeis cair em tentação,\n"
        "mas livrai-nos do mal. Amém."
    )

    # ── Voz e idiomas ─────────────────────────────────────────────────────────
    VOZ_EDGE: str = "pt-BR-AntonioNeural"
    IDIOMAS: list[str] = field(default_factory=lambda: IDIOMAS.copy())

    # ── IDs do Google Drive ───────────────────────────────────────────────────
    ID_PLANILHA_DRIVE:      str = "1bF7hnGSY7AALm4ZAS5owWNpiSTdgArW4ahAuVZaHPL0"
    ID_PASTA_AUDIO:         str = "1ZkEf6L6ZU0slgb-3QIhszWgu5A15v3rp"
    ID_PASTA_LEGENDAS:      str = "1X3aYPgrGvmUa_o57wksJs9AqkigZ7RNe"
    ID_PASTA_CLASSIFICACAO: str = "143trJsd-DNTTNoZzbUigO4LAXxQpWSMF"
    ID_PASTA_LOGO:          str = "1ANVbsVrFLugX5Z4wWZZ6ZdJZ-nk_CapO"
    ID_PASTA_MUSICA:        str = "1Ti_BxaT6HZ_dk84pRNUqHyRDJDb1ee_3"
    ID_PASTA_VIDEOS:        str = "1VR0dneES_DJxRX6jupeQHmC05ouLWV1e"
    ID_PASTA_COOKIES:       str = "1ZuxVr-pofA-Naqo8ysfGxWpYjSaSt3aE"

    # ── Assets externos ───────────────────────────────────────────────────────
    NOME_ARQUIVO_LOGO:   str = "globo_cruz_logo.png"
    NOME_ARQUIVO_MUSICA: str = (
        "Calmo créditos Shattered Paths - Aakash Gandhi(Youtube Audio Library).mp3"
    )
    NOME_COOKIES: str = "cookies.txt"

    # ── Parâmetros de vídeo ───────────────────────────────────────────────────
    DURACAO_CLIPE:   int   = 5        # segundos por clipe de estoque
    TAMANHO_LOGO:    int   = 80       # px (colada na borda direita/inferior)
    VOLUME_MUSICA:   float = 0.25     # 25 % de volume para trilha de fundo
    GROQ_MODEL:      str   = "llama-3.3-70b-versatile"

    # ── Layout de legenda ─────────────────────────────────────────────────────
    POSICOES_Y:     dict[str, int] = field(default_factory=lambda: POSICOES_Y.copy())
    POS_SIGLA_Y:    dict[str, int] = field(default_factory=lambda: POS_SIGLA_Y.copy())
    SIGLAS_IDIOMAS: dict[str, str] = field(default_factory=lambda: SIGLAS_IDIOMAS.copy())
    CORES_HTML:     dict[str, str] = field(default_factory=lambda: CORES_HTML.copy())
    TEXTO_PRETO:    set[str]       = field(default_factory=lambda: TEXTO_PRETO.copy())
    LARGURA_TELA:   int = LARGURA_TELA
    ALTURA_TELA:    int = ALTURA_TELA
    TAMANHO_FONTE_TAG:   int = TAMANHO_FONTE_TAG
    TAMANHO_FONTE_SIGLA: int = TAMANHO_FONTE_SIGLA
    BOX_BORDER:          int = BOX_BORDER
    ESPACAMENTO_PALAVRA: int = ESPACAMENTO_PALAVRA
    LARGURA_CHAR:        int = LARGURA_CHAR

    # ── Retry / performance ───────────────────────────────────────────────────
    GROQ_MAX_TENTATIVAS:    int   = 3
    GROQ_DELAY_ENTRE_CALLS: float = 2.0   # segundos entre chamadas
    DOWNLOAD_TIMEOUT:       int   = 30    # timeout HTTP em segundos
    FFMPEG_NUM_THREADS:     int   = 3     # threads para processar clipes em paralelo

    # ── Nomes de arquivo derivados do NOME_ORACAO ─────────────────────────────
    # Acesse via propriedades abaixo — não altere manualmente.

    @property
    def NOME_AUDIO(self) -> str:
        return f"{self.NOME_ORACAO}_audio.wav"

    @property
    def NOME_VIDEO_BASE(self) -> str:
        return f"{self.NOME_ORACAO}_base.mp4"

    @property
    def NOME_VIDEO_FINAL(self) -> str:
        return f"{self.NOME_ORACAO}_final.mp4"

    @property
    def NOME_SRT_PT_EDGE(self) -> str:
        """SRT bruto gerado pelo Whisper."""
        return f"{self.NOME_ORACAO}_pt_edge.srt"

    @property
    def NOME_SRT_PT(self) -> str:
        """SRT mestre em PT, corrigido pelo Groq."""
        return f"{self.NOME_ORACAO}_pt.srt"

    def nome_srt(self, lang: str) -> str:
        """Nome do SRT para qualquer idioma."""
        return f"{self.NOME_ORACAO}_{lang}.srt"

    def nome_classificacao(self, lang: str) -> str:
        """Nome do JSON de classificação morfológica."""
        return f"classificacao_{self.NOME_ORACAO}_{lang}.json"

    def nome_ass(self, lang: str) -> str:
        """Nome do arquivo .ass de legendas para um idioma."""
        return f"legendas_{self.NOME_ORACAO}_{lang}.ass"

    # ── Validação ─────────────────────────────────────────────────────────────
    def validate(self) -> None:
        """Verifica se a configuração está completa. Lança ValueError se falhar."""
        erros: list[str] = []

        if not self.NOME_ORACAO:
            erros.append("NOME_ORACAO não pode ser vazio")
        if not self.TEXTO_ORACAO:
            erros.append("TEXTO_ORACAO não pode ser vazio")
        if not self.ID_PLANILHA_DRIVE:
            erros.append("ID_PLANILHA_DRIVE não configurado")
        for id_attr in [
            "ID_PASTA_AUDIO", "ID_PASTA_LEGENDAS",
            "ID_PASTA_CLASSIFICACAO", "ID_PASTA_VIDEOS",
        ]:
            if not getattr(self, id_attr):
                erros.append(f"{id_attr} não configurado")

        if erros:
            msg = "PipelineConfig inválido:\n" + "\n".join(f"  - {e}" for e in erros)
            raise ValueError(msg)

        logger.info("PipelineConfig validado com sucesso para '%s'", self.NOME_ORACAO)

    def resumo(self) -> str:
        """Retorna string legível com as configurações principais."""
        linhas = [
            f"Oração:       {self.NOME_ORACAO}",
            f"Áudio:        {self.NOME_AUDIO}",
            f"SRT mestre:   {self.NOME_SRT_PT}",
            f"Vídeo base:   {self.NOME_VIDEO_BASE}",
            f"Vídeo final:  {self.NOME_VIDEO_FINAL}",
            f"Idiomas:      {', '.join(self.IDIOMAS)}",
            f"Voz Edge TTS: {self.VOZ_EDGE}",
            f"Modelo Groq:  {self.GROQ_MODEL}",
            f"Duração clipe:{self.DURACAO_CLIPE}s",
            f"Volume música:{int(self.VOLUME_MUSICA * 100)}%",
        ]
        return "\n".join(linhas)

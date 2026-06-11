# -*- coding: utf-8 -*-
"""
constants.py — Constantes imutáveis do pipeline.
Cores das 39+ classes morfológicas, siglas, mapeamentos de normalização,
posições de legenda e prompts do Groq.
"""

# ── Idiomas suportados ────────────────────────────────────────────────────────
IDIOMAS: list[str] = ["pt", "en", "es", "fr"]

SIGLAS_IDIOMAS: dict[str, str] = {
    "pt": "PT-BR",
    "en": "EN-US",
    "es": "ES-ES",
    "fr": "FR-FR",
}

NOMES_IDIOMA: dict[str, str] = {
    "pt": "português",
    "en": "inglês",
    "es": "espanhol",
    "fr": "francês",
}

# ── Posições Y das legendas na tela (pixels, tela 1280px) ────────────────────
POSICOES_Y: dict[str, int] = {
    "pt": 100,
    "en": 180,
    "es": 260,
    "fr": 340,
}

# Posição Y da sigla do idioma (acima da linha de legenda)
POS_SIGLA_Y: dict[str, int] = {
    "pt": 65,
    "en": 145,
    "es": 225,
    "fr": 305,
}

# ── Dimensões da tela ─────────────────────────────────────────────────────────
LARGURA_TELA: int = 1280
ALTURA_TELA: int = 720
CENTRO_X: int = LARGURA_TELA // 2

# ── Fontes e layout de legenda ────────────────────────────────────────────────
TAMANHO_FONTE_TAG: int = 24     # palavras com box colorido
TAMANHO_FONTE_SIGLA: int = 20   # rótulo PT-BR / EN-US etc.
BOX_BORDER: int = 6             # padding interno do box no drawtext (px)
ESPACAMENTO_PALAVRA: int = 40   # gap entre palavras (px)
LARGURA_CHAR: int = 12          # estimativa de largura por caractere (px)

# ── Cores das 39+ classes morfológicas (formato ASS: &H00BBGGRR) ─────────────
# Nota: ASS usa BGR (Blue-Green-Red) e prefixo &H00
# Conversão: hex HTML #RRGGBB → ASS &H00BBGGRR
def _hex_to_ass(html_hex: str) -> str:
    """Converte cor HTML #RRGGBB ou 0xRRGGBB para formato ASS &H00BBGGRR."""
    h = html_hex.replace("#", "").replace("0x", "").upper()
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}"


# Mapa principal: classe → hex HTML (para compatibilidade com código legado)
CORES_HTML: dict[str, str] = {
    # SUBSTANTIVOS
    "substantivo_masculino_singular": "#4169E1",
    "substantivo_masculino_plural":   "#1E3A8A",
    "substantivo_feminino_singular":  "#FF1493",
    "substantivo_feminino_plural":    "#C71585",
    # PRONOMES
    "pronome_possessivo_singular":    "#006400",
    "pronome_possessivo_plural":      "#004D00",
    "pronome_relativo":               "#FFD700",
    "pronome_pessoal":                "#008080",
    "pronome_indefinido":             "#20B2AA",
    "pronome_demonstrativo":          "#9370DB",
    "pronome_interrogativo":          "#FF6347",
    "pronome_reflexivo":              "#2E8B57",
    # VERBOS
    "verbo_presente":                 "#9B59B6",
    "verbo_passado":                  "#4A235A",
    "verbo_futuro":                   "#1ABC9C",
    "verbo_imperativo":               "#E67E22",
    "verbo_condicional":              "#F39C12",
    "verbo_subjuntivo":               "#8E44AD",
    "verbo_gerundio":                 "#D35400",
    "verbo_modal":                    "#E6E6FA",
    "verbo_auxiliar":                 "#3498DB",
    "verbo_futuro_proximo":           "#32CD32",
    # ADJETIVOS
    "adjetivo_normal":                "#E74C3C",
    "adjetivo_comparativo":           "#CC5500",
    "adjetivo_superlativo":           "#B22222",
    # ADVÉRBIOS
    "advérbio_normal":                "#16A085",
    "advérbio_intensificador":        "#27AE60",
    # OUTROS
    "preposicao":                     "#FF8C00",
    "artigo_definido":                "#D3D3D3",
    "artigo_indefinido":              "#BDC3C7",
    "conjuncao":                      "#8B4513",
    "interjeicao":                    "#FF69B4",
    # INGLÊS
    "comparativo_superlativo":        "#8B0000",
    "pronome_it":                     "#A9A9A9",
    # ESPANHOL
    "usted":                          "#DDA0DD",
    "voseo":                          "#FFA500",
    "lo_neutro":                      "#C0C0C0",
    "se_impessoal":                   "#98FB98",
    "preterito_perfecto":             "#8B008B",
    "subjuntivo_es":                  "#FF7F50",
    "imperativo_pronome":             "#CC5500",
    # FRANCÊS
    "passe_compose":                  "#BA55D3",
    "imparfait":                      "#C39BD3",
    "plus_que_parfait":               "#4A235A",
    "subjonctif_fr":                  "#FF69B4",
    "conditionnel":                   "#B8860B",
    "futur_proche":                   "#90EE90",
    "pronome_objeto":                 "#87CEEB",
    "pronome_adverbial":              "#89CFF0",
    "artigo_partitivo":               "#EAEAEA",
    "concordancia_adjetivo":          "#FF00FF",
    # PORTUGUÊS ESPECÍFICO
    "vos_portugues":                  "#009C3B",
    "pronome_obliquo":                "#000080",
    "colocacao_pronominal":           "#F28500",
    "futuro_subjuntivo":              "#8B0000",
    "gerundio_participio":            "#800080",
}

# Mapa derivado: classe → cor ASS (&H00BBGGRR)
CORES_ASS: dict[str, str] = {
    classe: _hex_to_ass(cor) for classe, cor in CORES_HTML.items()
}

# Cor padrão para classes desconhecidas
COR_PADRAO_HTML: str = "#666666"
COR_PADRAO_ASS: str  = _hex_to_ass(COR_PADRAO_HTML)

# Classes que exigem texto preto (fundos claros)
TEXTO_PRETO: set[str] = {
    "pronome_relativo",       # #FFD700 dourado
    "artigo_definido",        # #D3D3D3 cinza claro
    "artigo_indefinido",      # #BDC3C7 cinza médio
    "verbo_modal",            # #E6E6FA lavanda
    "pronome_it",             # #A9A9A9 cinza
    "usted",                  # #DDA0DD lilás claro
    "lo_neutro",              # #C0C0C0 cinza prata
    "se_impessoal",           # #98FB98 verde claro
    "imparfait",              # #C39BD3 roxo lavanda
    "futur_proche",           # #90EE90 verde claro
    "pronome_adverbial",      # #89CFF0 azul bebê
    "artigo_partitivo",       # #EAEAEA cinza bem claro
}

# ── Mapeamento de normalização: inglês/variante → português padrão ────────────
MAPEAMENTO_CLASSES: dict[str, str] = {
    # Inglês genérico
    "noun":          "substantivo_masculino_singular",
    "verb":          "verbo_presente",
    "pronoun":       "pronome_pessoal",
    "preposition":   "preposicao",
    "adjective":     "adjetivo_normal",
    "adverb":        "advérbio_normal",
    "conjunction":   "conjuncao",
    "determiner":    "artigo_definido",
    "article":       "artigo_definido",
    "interjection":  "interjeicao",
    # Variantes com underscore/hífen
    "possessive_pronoun":    "pronome_possessivo_singular",
    "relative_pronoun":      "pronome_relativo",
    "personal_pronoun":      "pronome_pessoal",
    "present_verb":          "verbo_presente",
    "past_verb":             "verbo_passado",
    "modal_verb":            "verbo_modal",
    "auxiliary_verb":        "verbo_auxiliar",
    "definite_article":      "artigo_definido",
    "indefinite_article":    "artigo_indefinido",
    "gerund":                "verbo_gerundio",
    "participle":            "gerundio_participio",
    # Português com erros tipográficos comuns do Groq
    "adverbio_normal":       "advérbio_normal",
    "adverbio":              "advérbio_normal",
    "advérbio":              "advérbio_normal",
}

# ── Fases do pipeline (para o sistema de checkpoint) ─────────────────────────
FASES_PIPELINE: list[str] = [
    "audio_gerado",
    "srt_pt_bruto",
    "srt_pt_corrigido",
    "srt_traduzidos",
    "classificacoes_feitas",
    "clipes_cortados",
    "video_base_criado",
    "legendas_queimadas",
]

# ── Vocabulário litúrgico por idioma (para revisão Groq) ─────────────────────
EXEMPLOS_LITURGICOS: dict[str, str] = {
    "en": "thy/thine/art/hallowed/trespass/forgive us our trespasses",
    "es": "santificado/venga/hágase/perdónanos/deudas/líbranos",
    "fr": "ton/que ton nom soit sanctifié/pardonne-nous/délivre-nous",
}

# ── System prompts do Groq ────────────────────────────────────────────────────
PROMPT_SISTEMA_CORRECAO_PT = (
    "Você é um especialista em português e textos religiosos cristãos. "
    "Corrija APENAS erros de transcrição do Whisper, mantendo a segmentação exata. "
    "Retorne SOMENTE um JSON válido, sem markdown, sem texto extra. "
    'Formato: [{"id": 1, "texto": "frase corrigida"}, ...]'
)

PROMPT_SISTEMA_REDISTRIBUICAO = (
    "Você é um especialista em alinhamento de legendas multilíngues. "
    "Redistribua o texto em exatamente {N} segmentos seguindo os cortes do PT. "
    "Retorne SOMENTE um JSON válido, sem markdown, sem texto extra. "
    'Formato: [{{"id": 1, "texto": "frase em {idioma}"}}]'
)

PROMPT_SISTEMA_REVISAO_LITURGICA = (
    "Você é um especialista em textos litúrgicos cristãos em {idioma}. "
    "Revise o vocabulário para usar termos clássicos/litúrgicos (ex: {exemplos}). "
    "Mantenha a estrutura de {N} frases. "
    "Retorne SOMENTE JSON válido. "
    'Formato: [{{"id": 1, "texto": "frase revisada"}}]'
)

PROMPT_SISTEMA_CLASSIFICACAO = (
    "Você é um especialista em linguística. "
    "Classifique cada palavra da legenda usando SOMENTE as classes fornecidas. "
    "Retorne SOMENTE um objeto JSON válido, sem markdown, sem texto extra. "
    'Formato: {"palavras": [{"texto": "palavra", "classe": "classe"}]}'
)

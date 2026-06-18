import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

AZUL      = colors.HexColor('#1B3A6B')
AZUL_CLARO= colors.HexColor('#2472B5')
VERDE     = colors.HexColor('#27AE60')
AMARELO   = colors.HexColor('#E67E22')
VERMELHO  = colors.HexColor('#E74C3C')
CINZA     = colors.HexColor('#F5F7FA')
CINZA_MED = colors.HexColor('#E2E9F2')

STATUS_COLOR = {'verde': VERDE, 'amarelo': AMARELO, 'vermelho': VERMELHO}
STATUS_LABEL = {'verde': 'CONFORME', 'amarelo': 'ATENÇÃO',  'vermelho': 'CRÍTICO'}


def _get_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        'titulo':   ParagraphStyle('t',   parent=base['Title'],
                                   fontSize=22, textColor=AZUL, spaceAfter=2,
                                   fontName='Helvetica-Bold'),
        'sub':      ParagraphStyle('s',   parent=base['Normal'],
                                   fontSize=9, textColor=colors.grey, spaceAfter=12),
        'secao':    ParagraphStyle('se',  parent=base['Heading2'],
                                   fontSize=11, textColor=AZUL, spaceBefore=14, spaceAfter=5,
                                   fontName='Helvetica-Bold', borderPad=2),
        'subsecao': ParagraphStyle('ss',  parent=base['Heading3'],
                                   fontSize=9.5, textColor=AZUL_CLARO, spaceBefore=8, spaceAfter=3,
                                   fontName='Helvetica-Bold'),
        'corpo':    ParagraphStyle('c',   parent=base['Normal'],
                                   fontSize=9, leading=14, spaceAfter=5, alignment=TA_JUSTIFY),
        'corpo_bold': ParagraphStyle('cb', parent=base['Normal'],
                                   fontSize=9, leading=14, spaceAfter=3,
                                   fontName='Helvetica-Bold'),
        'rodape':   ParagraphStyle('r',   parent=base['Normal'],
                                   fontSize=7, textColor=colors.grey, alignment=TA_CENTER),
        'label':    ParagraphStyle('l',   parent=base['Normal'],
                                   fontSize=8, textColor=colors.grey),
        'numero':   ParagraphStyle('n',   parent=base['Normal'],
                                   fontSize=9, fontName='Helvetica-Bold', textColor=AZUL),
    }


def _tabela_kv(dados: list[list], col_w=None, st=None):
    col_w = col_w or [4.5*cm, 12.5*cm]
    t = Table(dados, colWidths=col_w)
    t.setStyle(TableStyle([
        ('FONTNAME',  (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (0, -1), AZUL),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [CINZA, colors.white]),
        ('PADDING',   (0, 0), (-1, -1), 5),
        ('GRID',      (0, 0), (-1, -1), 0.3, CINZA_MED),
    ]))
    return t


def gerar_pdf(
    resumo_segmentos: list[dict],
    pl: float,
    data_ref: str,
    analise_ia: str | None = None,
    benchmarks: dict | None = None,
    meta_planos=None,       # pd.DataFrame from calcular_meta_atuarial
    ultima_pos=None,        # pd.DataFrame from ultima_posicao
    total_investido: float | None = None,
) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    s = _get_styles()
    els = []
    bm = benchmarks or {}

    # ── Cabeçalho ────────────────────────────────────────────────────────────
    els.append(Paragraph("VIGIA", s['titulo']))
    els.append(Paragraph(
        "Vigilância de Investimentos e Gestão do IAJA — Sistema de Análise de Investimentos",
        s['sub'],
    ))
    els.append(HRFlowable(width='100%', thickness=2, color=AZUL, spaceAfter=6))

    # ── Identificação ─────────────────────────────────────────────────────────
    els.append(Paragraph("Identificação do Relatório", s['secao']))
    total_inv = total_investido or sum(r['valor'] for r in resumo_segmentos)
    pct_inv   = total_inv / pl if pl else 0
    els.append(_tabela_kv([
        ['Entidade',           'IAJA — Instituto Adventista de Jubilação e Assistência'],
        ['CNPJ / Tipo',        'EFPC — Entidade Fechada de Previdência Complementar'],
        ['Supervisão',         'PREVIC — Previd. Complementar Fechada'],
        ['Base regulatória',   'Resolução CMN 4.994/2022'],
        ['Data de referência', data_ref],
        ['Patrimônio Social',  f"R$ {pl:,.2f}"],
        ['Total Investido',    f"R$ {total_inv:,.2f}  ({pct_inv:.1%} do PS)"],
        ['Emitido em',         datetime.now().strftime('%d/%m/%Y às %H:%M')],
    ]))
    els.append(Spacer(1, 0.4*cm))

    # ── Resumo de Alertas ─────────────────────────────────────────────────────
    els.append(Paragraph("Resumo de Conformidade Regulatória", s['secao']))
    criticos  = sum(1 for r in resumo_segmentos if r['status'] == 'vermelho')
    atencao   = sum(1 for r in resumo_segmentos if r['status'] == 'amarelo')
    conformes = sum(1 for r in resumo_segmentos if r['status'] == 'verde')
    total_seg = len(resumo_segmentos)

    t_alert = Table(
        [['Conformes', 'Em Atenção', 'Críticos', 'Total Segmentos'],
         [str(conformes), str(atencao), str(criticos), str(total_seg)]],
        colWidths=[4.25*cm]*4,
    )
    t_alert.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), AZUL),
        ('TEXTCOLOR',   (0, 0), (-1, 0), colors.white),
        ('FONTNAME',    (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, -1), 11),
        ('ALIGN',       (0, 0), (-1, -1), 'CENTER'),
        ('PADDING',     (0, 0), (-1, -1), 8),
        ('GRID',        (0, 0), (-1, -1), 0.5, CINZA_MED),
        ('TEXTCOLOR',   (0, 1), (0, 1), VERDE),
        ('TEXTCOLOR',   (1, 1), (1, 1), AMARELO),
        ('TEXTCOLOR',   (2, 1), (2, 1), VERMELHO if criticos > 0 else VERDE),
    ]))
    els.append(t_alert)
    els.append(Spacer(1, 0.4*cm))

    # ── Benchmarks de Mercado ─────────────────────────────────────────────────
    if bm:
        els.append(Paragraph("Benchmarks de Mercado — Banco Central do Brasil", s['secao']))
        bm_rows = [['Índice', 'No Mês', 'No Ano']]
        bm_data = [
            ('CDI — Taxa DI',    bm.get('cdi_mes', 0),  bm.get('cdi_ano', 0)),
            ('IPCA — Inflação',  bm.get('ipca_mes', 0), bm.get('ipca_ano', 0)),
            ('INPC — Meta Base', bm.get('inpc_mes', 0), bm.get('inpc_ano', 0)),
            ('Ibovespa — B3',    bm.get('ibov_mes', 0), bm.get('ibov_ano', 0)),
        ]
        for nome, mes, ano in bm_data:
            bm_rows.append([nome, f"{mes:+.2f}%", f"{ano:+.2f}%"])
        t_bm = Table(bm_rows, colWidths=[8.5*cm, 4.25*cm, 4.25*cm])
        bm_style = [
            ('BACKGROUND', (0, 0), (-1, 0), AZUL),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0, 0), (-1, -1), 9),
            ('ALIGN',      (1, 0), (-1, -1), 'CENTER'),
            ('PADDING',    (0, 0), (-1, -1), 5),
            ('GRID',       (0, 0), (-1, -1), 0.3, CINZA_MED),
        ]
        for i in range(1, len(bm_rows)):
            bg = CINZA if i % 2 == 0 else colors.white
            bm_style.append(('BACKGROUND', (0, i), (-1, i), bg))
            _, mes_v, ano_v = bm_data[i-1]
            bm_style.append(('TEXTCOLOR', (1, i), (1, i), VERDE if mes_v >= 0 else VERMELHO))
            bm_style.append(('TEXTCOLOR', (2, i), (2, i), VERDE if ano_v >= 0 else VERMELHO))
            bm_style.append(('FONTNAME',  (1, i), (2, i), 'Helvetica-Bold'))
        t_bm.setStyle(TableStyle(bm_style))
        els.append(t_bm)
        els.append(Spacer(1, 0.4*cm))

    # ── Desempenho dos Planos vs Meta Atuarial ────────────────────────────────
    if meta_planos is not None and not meta_planos.empty:
        els.append(Paragraph("Desempenho dos Planos vs Meta Atuarial Oficial", s['secao']))
        els.append(Paragraph(
            "Metas oficiais conforme Políticas de Investimentos 2025-2029 aprovadas pelo Conselho Deliberativo. "
            "Alpha (BD — Benefício Definido): INPC + 5,24% a.a. | Beta e Gama (CV — Contribuição Variável): INPC + 4,50% a.a.",
            s['label'],
        ))
        els.append(Spacer(1, 0.2*cm))
        mp_header = ['Plano', 'Tipo', 'Ret. Mês', 'Meta Mês', 'Δ Mês', 'Status', 'Ret. Ano', 'Meta Ano', 'Δ Ano', 'Status']
        mp_rows = [mp_header]
        for _, row in meta_planos.iterrows():
            dm = row['Δ Mês (%)']
            da = row['Δ Ano (%)']
            mp_rows.append([
                row['Plano'],
                row.get('Tipo', ''),
                f"{row['Retorno Mês (%)']:.2f}%",
                f"{row['Meta Mês (%)']:.2f}%",
                f"{dm:+.2f}%",
                row['Status Mês'],
                f"{row['Retorno Ano (%)']:.2f}%",
                f"{row['Meta Ano (%)']:.2f}%",
                f"{da:+.2f}%",
                row['Status Ano'],
            ])
        t_mp = Table(mp_rows, colWidths=[2.6*cm, 1.0*cm, 1.7*cm, 1.7*cm, 1.5*cm, 1.0*cm,
                                          1.7*cm, 1.7*cm, 1.5*cm, 1.0*cm])
        mp_style = [
            ('BACKGROUND', (0, 0), (-1, 0), AZUL),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0, 0), (-1, -1), 8),
            ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN',      (0, 1), (0, -1), 'LEFT'),
            ('PADDING',    (0, 0), (-1, -1), 4),
            ('GRID',       (0, 0), (-1, -1), 0.3, CINZA_MED),
        ]
        for i, row in enumerate(meta_planos.itertuples(), 1):
            bg = CINZA if i % 2 == 0 else colors.white
            mp_style.append(('BACKGROUND', (0, i), (-1, i), bg))
            dm = row._5  # Δ Mês (%)
            da = row._9  # Δ Ano (%)
            mp_style.append(('TEXTCOLOR', (4, i), (4, i), VERDE if dm >= 0 else VERMELHO))
            mp_style.append(('TEXTCOLOR', (8, i), (8, i), VERDE if da >= 0 else VERMELHO))
            mp_style.append(('FONTNAME',  (4, i), (4, i), 'Helvetica-Bold'))
            mp_style.append(('FONTNAME',  (8, i), (8, i), 'Helvetica-Bold'))
        t_mp.setStyle(TableStyle(mp_style))
        els.append(t_mp)
        els.append(Spacer(1, 0.4*cm))

    # ── Retorno dos Planos vs Benchmarks (se cotas disponíveis) ──────────────
    if ultima_pos is not None and not ultima_pos.empty and bm:
        els.append(Paragraph("Retorno Realizado vs Benchmarks de Mercado", s['secao']))
        planos_nomes = ['PL Alpha', 'PL Beta', 'PL Gama', 'Administrativo']
        ub_header = ['Plano', 'Ret. Mês', 'vs CDI', 'vs IPCA', 'Ret. Ano', 'vs CDI Ano']
        ub_rows = [ub_header]
        ub_data = []
        for nome in planos_nomes:
            row = ultima_pos[ultima_pos['fundo'] == nome]
            if row.empty:
                continue
            r = row.iloc[0]
            dm_cdi  = r['Mês_pct'] - bm.get('cdi_mes', 0)
            dm_ipca = r['Mês_pct'] - bm.get('ipca_mes', 0)
            da_cdi  = r['Ano_pct']  - bm.get('cdi_ano', 0)
            ub_rows.append([
                nome,
                f"{r['Mês_pct']:.2f}%",
                f"{dm_cdi:+.2f}%",
                f"{dm_ipca:+.2f}%",
                f"{r['Ano_pct']:.2f}%",
                f"{da_cdi:+.2f}%",
            ])
            ub_data.append((dm_cdi, dm_ipca, da_cdi))

        if len(ub_rows) > 1:
            t_ub = Table(ub_rows, colWidths=[3.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            ub_style = [
                ('BACKGROUND', (0, 0), (-1, 0), AZUL),
                ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
                ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0, 0), (-1, -1), 9),
                ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN',      (0, 1), (0, -1), 'LEFT'),
                ('PADDING',    (0, 0), (-1, -1), 5),
                ('GRID',       (0, 0), (-1, -1), 0.3, CINZA_MED),
            ]
            for i, (dm_cdi, dm_ipca, da_cdi) in enumerate(ub_data, 1):
                bg = CINZA if i % 2 == 0 else colors.white
                ub_style.append(('BACKGROUND', (0, i), (-1, i), bg))
                ub_style.append(('TEXTCOLOR', (2, i), (2, i), VERDE if dm_cdi  >= 0 else VERMELHO))
                ub_style.append(('TEXTCOLOR', (3, i), (3, i), VERDE if dm_ipca >= 0 else VERMELHO))
                ub_style.append(('TEXTCOLOR', (5, i), (5, i), VERDE if da_cdi  >= 0 else VERMELHO))
                for col in (2, 3, 5):
                    ub_style.append(('FONTNAME', (col, i), (col, i), 'Helvetica-Bold'))
            t_ub.setStyle(TableStyle(ub_style))
            els.append(t_ub)
            els.append(Spacer(1, 0.4*cm))

    # ── Compliance por Segmento ───────────────────────────────────────────────
    els.append(Paragraph("Posição por Segmento — Resolução CMN 4.994/2022", s['secao']))
    header = ['Segmento', 'Valor (R$ MM)', '% do PS', 'Limite CMN', '% do Limite', 'Status']
    rows = [header] + [
        [
            r['segmento'],
            f"{r['valor']/1e6:.2f}",
            f"{r['pct_pl']:.2%}",
            f"{r['limite_pct']:.0%}",
            f"{r['pct_limite']:.1%}",
            STATUS_LABEL[r['status']],
        ]
        for r in resumo_segmentos
    ]
    t_seg = Table(rows, colWidths=[5.2*cm, 2.6*cm, 2.0*cm, 2.0*cm, 2.2*cm, 2.0*cm])
    seg_style = [
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, -1), 8.5),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN',      (0, 1), (0, -1), 'LEFT'),
        ('PADDING',    (0, 0), (-1, -1), 5),
        ('GRID',       (0, 0), (-1, -1), 0.3, CINZA_MED),
    ]
    for i, r in enumerate(resumo_segmentos, 1):
        bg = CINZA if i % 2 == 0 else colors.white
        seg_style.append(('BACKGROUND', (0, i), (-1, i), bg))
        seg_style.append(('TEXTCOLOR',  (5, i), (5, i), STATUS_COLOR[r['status']]))
        seg_style.append(('FONTNAME',   (5, i), (5, i), 'Helvetica-Bold'))
        if r['pct_limite'] > 0.80:
            seg_style.append(('TEXTCOLOR', (4, i), (4, i), VERMELHO if r['status'] == 'vermelho' else AMARELO))
            seg_style.append(('FONTNAME',  (4, i), (4, i), 'Helvetica-Bold'))
    t_seg.setStyle(TableStyle(seg_style))
    els.append(t_seg)
    els.append(Spacer(1, 0.4*cm))

    # ── Análise Inteligente ────────────────────────────────────────────────────
    if analise_ia:
        els.append(PageBreak())
        els.append(Paragraph("Análise Inteligente — VIGIA AI", s['secao']))
        els.append(Paragraph(
            "Análise gerada por inteligência artificial (Groq / Llama 3.3 70B) com base nos dados "
            "reais do portfólio IAJA. Documento de suporte — não substitui parecer técnico formal.",
            s['label'],
        ))
        els.append(Spacer(1, 0.2*cm))

        for bloco in analise_ia.split('\n\n'):
            txt = bloco.strip()
            if not txt:
                continue
            # Títulos de seção (## 1. Síntese...)
            if txt.startswith('##'):
                titulo = txt.lstrip('#').strip()
                els.append(Paragraph(titulo, s['subsecao']))
            else:
                els.append(Paragraph(txt.replace('\n', '<br/>'), s['corpo']))
                els.append(Spacer(1, 0.1*cm))

    # ── Rodapé ─────────────────────────────────────────────────────────────────
    els.append(Spacer(1, 0.6*cm))
    els.append(HRFlowable(width='100%', thickness=0.5, color=CINZA_MED))
    els.append(Paragraph(
        f"VIGIA — Sistema de Análise de Investimentos  ·  IAJA — Instituto Adventista de Jubilação e Assistência  ·  "
        f"Res. CMN 4.994/2022  ·  Supervisão: PREVIC  ·  Emitido em {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
        s['rodape'],
    ))

    doc.build(els)
    buf.seek(0)
    return buf

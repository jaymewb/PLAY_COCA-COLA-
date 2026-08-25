from datetime import datetime
from io import BytesIO
import os
import re
import sqlite3
import urllib.parse

from flask import Flask, request, render_template_string
import pandas as pd
import requests

app = Flask(__name__)

# URL da sua planilha no OneDrive
SHEET_URL = "https://1drv.ms/x/c/b96adcc2e8fff38f/IQDxY7NKJj9mR6k_xhOTtGBGAUiE7EiJCON8mKvXXKzLfAM?e=LIduIn&nav=MTVfezAwMDAwMDAwLTAwMDEtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMH0"

# ================= CONFIGURAÇÃO DO BANCO DE DADOS (SQLITE) =================
DB_NAME = "rh_escala.db"


def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Cria a tabela caso não exista
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_envios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hora TEXT,
            nome TEXT,
            sucesso BOOLEAN,
            detalhe TEXT,
            mensagem TEXT
        )
    """)
    # Compatibilidade caso a tabela já exista sem a coluna mensagem
    try:
        cursor.execute("ALTER TABLE historico_envios ADD COLUMN mensagem TEXT")
    except sqlite3.OperationalError:
        pass  # A coluna já existe
    conn.commit()
    conn.close()


inicializar_banco()

# ================= HTML / CSS / JS =================
HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Painel de Escala RH - Disparo Automatizado</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #0f172a;
            color: white;
            margin: 0;
            padding: 0;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .topo-fixo {
            flex-shrink: 0;
            padding: 15px 20px 10px 20px;
            background: #0f172a;
            z-index: 1000;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }

        .header-painel {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #1e293b;
            padding: 10px 20px;
            border-radius: 8px;
            margin-bottom: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        h2 { margin: 0; font-size: 20px; }

        .relogio-24h {
            font-size: 15px;
            font-weight: bold;
            color: #38bdf8;
            background: #0f172a;
            padding: 5px 12px;
            border-radius: 6px;
            border: 1px solid #334155;
        }

        .painel-controles {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: flex-start;
        }

        .search-form {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            flex: 2;
            background: #1e293b;
            padding: 12px 18px;
            border-radius: 8px;
            border: 1px solid #334155;
            align-items: center;
        }

        .search-box-item {
            flex: 1;
            min-width: 160px;
            position: relative;
        }

        input[type="text"] {
            padding: 9px 12px;
            width: 100%;
            box-sizing: border-box;
            border-radius: 8px;
            border: 1px solid #475569;
            background: #0f172a;
            color: white;
            font-size: 13px;
            outline: none;
        }
        input[type="text"]:focus { border-color: #38bdf8; }

        .painel-bot {
            background: #1e293b;
            border: 1px solid #334155;
            padding: 12px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            width: 230px;
        }

        .btn-acao {
            padding: 7px 10px;
            border: none;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            font-size: 12px;
            text-align: center;
        }
        .btn-iniciar { background: #22c55e; color: #0f172a; }
        .btn-pausar { background: #eab308; color: #0f172a; }
        .btn-iniciar:hover { background: #16a34a; }
        .btn-pausar:hover { background: #ca8a04; }

        .btn-home {
            background: #3b82f6;
            color: white;
            text-decoration: none;
            display: inline-block;
        }
        .btn-home:hover { background: #2563eb; }

        .cronometro-box {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 5px;
            text-align: center;
            font-size: 11px;
            color: #38bdf8;
            font-weight: bold;
        }

        .barra-progresso-container {
            width: 100%;
            background: #334155;
            border-radius: 4px;
            height: 6px;
            overflow: hidden;
            margin-top: 4px;
        }
        .barra-progresso-fill {
            width: 0%;
            height: 100%;
            background: #22c55e;
            transition: width 0.4s ease;
        }

        .multiselect-btn {
            padding: 9px 12px;
            width: 100%;
            box-sizing: border-box;
            border-radius: 8px;
            border: 1px solid #475569;
            background: #0f172a;
            color: white;
            font-size: 13px;
            text-align: left;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .multiselect-content {
            display: none;
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            max-height: 200px;
            overflow-y: auto;
            z-index: 2000;
            box-shadow: 0 8px 16px rgba(0,0,0,0.5);
            padding: 8px;
            margin-top: 4px;
        }
        .multiselect-content.show { display: block; }

        .dropdown-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px;
            font-size: 13px;
            color: #cbd5e1;
            cursor: pointer;
            border-radius: 4px;
        }
        .dropdown-item:hover { background: #334155; }

        .calendario-box {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px 12px;
            width: 210px;
            text-align: center;
        }
        .cal-header {
            font-weight: bold;
            font-size: 12px;
            margin-bottom: 6px;
            color: #38bdf8;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .cal-header button {
            background: #334155;
            color: white;
            border: none;
            padding: 3px 6px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
        }
        .cal-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 2px;
            font-size: 10px;
        }
        .cal-day-name { font-weight: bold; color: #94a3b8; padding-bottom: 2px; }
        .cal-day {
            padding: 4px 0;
            background: #0f172a;
            border-radius: 3px;
            color: #cbd5e1;
            cursor: pointer;
        }
        .cal-day:hover { background: #334155; color: white; }
        .cal-day.today { border: 1px solid #22c55e; color: #22c55e; font-weight: bold; }
        .cal-day.selected { background: #38bdf8 !important; color: #0f172a !important; font-weight: bold; }
        .cal-day.empty { background: transparent; cursor: default; }
        .btn-limpar-data {
            background: transparent;
            border: none;
            color: #f43f5e;
            font-size: 10px;
            cursor: pointer;
            text-decoration: underline;
            margin-top: 4px;
            display: inline-block;
        }

        .main-layout {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        .conteudo-scroll {
            flex: 2;
            overflow-y: auto;
            padding: 20px;
        }

        .relatorio-lateral {
            flex: 1;
            background: #1e293b;
            border-left: 1px solid #334155;
            padding: 15px;
            overflow-y: auto;
            min-width: 320px;
            display: flex;
            flex-direction: column;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 15px;
        }

        .card {
            background: #1e293b;
            border-radius: 10px;
            padding: 14px;
            border: 1px solid #334155;
            box-shadow: 0px 4px 10px rgba(0,0,0,0.3);
            transition: border-color 0.3s;
        }
        .card.card-ativo {
            border-color: #38bdf8;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
        }

        .posto {
            border: 2px solid #facc15;
            color: #facc15;
            padding: 3px 8px;
            border-radius: 4px;
            display: inline-block;
            font-size: 11px;
            font-weight: bold;
            margin-bottom: 8px;
        }

        .nome { font-weight: bold; font-size: 15px; margin-bottom: 6px; color: #f8fafc; }
        .info { font-size: 12px; margin: 4px 0; color: #cbd5e1; }

        .input-pendencia-editavel {
            background: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #475569;
            padding: 5px 8px;
            border-radius: 4px;
            font-size: 12px;
            width: 100%;
            box-sizing: border-box;
            margin-top: 2px;
            font-weight: 500;
        }

        .preview-msg {
            background: #0f172a;
            border: 1px dashed #475569;
            padding: 8px;
            border-radius: 6px;
            font-size: 11px;
            color: #38bdf8;
            margin-top: 8px;
            word-break: break-word;
        }

        .btn {
            display: block;
            margin-top: 10px;
            padding: 8px;
            text-align: center;
            background: #22c55e;
            color: #0f172a;
            border-radius: 6px;
            text-decoration: none;
            font-weight: bold;
            font-size: 12px;
            cursor: pointer;
        }
        .btn:hover { background: #16a34a; }

        .sem-pendencia-box {
            background: #1e293b;
            border: 1px dashed #334155;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            color: #94a3b8;
            font-size: 15px;
            grid-column: 1 / -1;
        }

        .log-item {
            font-size: 11px;
            padding: 8px;
            margin-bottom: 6px;
            border-radius: 6px;
            border-left: 4px solid #334155;
            background: #0f172a;
        }
        .log-sucesso { border-left-color: #22c55e; }
        .log-erro { border-left-color: #ef4444; }

        .log-msg-preview {
            color: #94a3b8;
            margin-top: 4px;
            font-style: italic;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .relatorio-acoes {
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
        }
        .btn-limpar-log {
            background: #ef4444;
            color: white;
            border: none;
            padding: 5px 8px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            font-weight: bold;
        }
        .btn-limpar-log:hover { background: #dc2626; }

        .btn-maximizar-log {
            background: #334155;
            color: #38bdf8;
            border: none;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            cursor: pointer;
            float: right;
            font-weight: bold;
        }
        .btn-maximizar-log:hover { background: #475569; }

        /* Modal Maximizada */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.7);
            z-index: 3000;
            justify-content: center;
            align-items: center;
        }
        .modal-conteudo {
            background: #1e293b;
            border: 1px solid #334155;
            padding: 25px;
            border-radius: 10px;
            width: 600px;
            max-width: 90%;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }
        .modal-titulo {
            font-size: 16px;
            font-weight: bold;
            color: #38bdf8;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-texto {
            background: #0f172a;
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #475569;
            font-size: 14px;
            color: #f8fafc;
            word-break: break-word;
            max-height: 300px;
            overflow-y: auto;
            margin-bottom: 15px;
        }
        .btn-fechar-modal {
            background: #3b82f6;
            color: white;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            float: right;
        }
        .btn-fechar-modal:hover { background: #2563eb; }
    </style>
</head>
<body>

    <div class="topo-fixo">
        <div class="header-painel">
            <h2>📋 Painel de Escala RH - Disparo Automatizado por Pendência</h2>
            <div id="relogio" class="relogio-24h">--:--:--</div>
        </div>

        <div class="painel-controles">
            <form class="search-form" method="get" id="searchForm" action="/">
                <input type="hidden" name="data_selecionada" id="dataSelecionadaInput" value="{{ data_selecionada }}">

                <div class="search-box-item">
                    <label style="display:block; font-size:11px; color:#94a3b8; margin-bottom:2px;">Pesquisar Colaborador:</label>
                    <input type="text" id="buscaInput" name="busca" placeholder="Digite o nome..." value="{{busca}}">
                </div>

                <div class="search-box-item">
                    <label style="display:block; font-size:11px; color:#94a3b8; margin-bottom:2px;">Unidade(s):</label>
                    <div class="multiselect-btn" onclick="toggleDropdown('dropdownUnidade')">
                        <span id="labelUnidade">Todas</span>
                        <span>▼</span>
                    </div>
                    <div class="multiselect-content" id="dropdownUnidade">
                        <label class="dropdown-item" style="font-weight:bold; border-bottom:1px solid #334155; margin-bottom:4px;">
                            <input type="checkbox" onchange="toggleTodos(this, 'chk-unidade')"> (Marcar Todos)
                        </label>
                        {% for u in unidades_disponiveis %}
                            <label class="dropdown-item">
                                <input type="checkbox" name="filtro_posto" value="{{ u }}" class="chk-unidade" {% if u in filtro_posto %}checked{% endif %} onchange="submeterFormulario()"> {{ u }}
                            </label>
                        {% endfor %}
                    </div>
                </div>

                <div class="search-box-item">
                    <label style="display:block; font-size:11px; color:#94a3b8; margin-bottom:2px;">Status:</label>
                    <div class="multiselect-btn" onclick="toggleDropdown('dropdownStatus')">
                        <span id="labelStatus">Todos</span>
                        <span>▼</span>
                    </div>
                    <div class="multiselect-content" id="dropdownStatus">
                        <label class="dropdown-item" style="font-weight:bold; border-bottom:1px solid #334155; margin-bottom:4px;">
                            <input type="checkbox" onchange="toggleTodos(this, 'chk-status')"> (Marcar Todos)
                        </label>
                        {% for s in status_disponiveis %}
                            <label class="dropdown-item">
                                <input type="checkbox" name="filtro_status" value="{{ s }}" class="chk-status" {% if s in filtro_status %}checked{% endif %} onchange="submeterFormulario()"> {{ s }}
                            </label>
                        {% endfor %}
                    </div>
                </div>

                <div class="search-box-item">
                    <label style="display:block; font-size:11px; color:#94a3b8; margin-bottom:2px;">Pendência:</label>
                    <div class="multiselect-btn" onclick="toggleDropdown('dropdownPendencia')">
                        <span id="labelPendencia">Todas</span>
                        <span>▼</span>
                    </div>
                    <div class="multiselect-content" id="dropdownPendencia">
                        <label class="dropdown-item" style="font-weight:bold; border-bottom:1px solid #334155; margin-bottom:4px;">
                            <input type="checkbox" onchange="toggleTodos(this, 'chk-pendencia')"> (Marcar Todos)
                        </label>
                        {% for pend in pendencias_disponiveis %}
                            <label class="dropdown-item">
                                <input type="checkbox" name="filtro_pendencia" value="{{ pend }}" class="chk-pendencia" {% if pend in filtro_pendencia %}checked{% endif %} onchange="submeterFormulario()"> {{ pend }}
                            </label>
                        {% endfor %}
                    </div>
                </div>
            </form>

            <div class="calendario-box">
                <div class="cal-header">
                    <button type="button" onclick="mudarMes(-1)">◀</button>
                    <span id="mesAnoTitulo">Mês Ano</span>
                    <button type="button" onclick="mudarMes(1)">▶</button>
                </div>
                <div class="cal-grid" id="calendarioGrid"></div>
                {% if data_selecionada %}
                    <button type="button" class="btn-limpar-data" onclick="limparData()">❌ Limpar Data ({{data_selecionada}})</button>
                {% endif %}
            </div>

            <div class="painel-bot">
                <span style="font-size: 11px; font-weight: bold; color: #38bdf8;">🤖 Disparo em Massa</span>
                <button type="button" class="btn-acao btn-iniciar" id="btnIniciar" onclick="alternarBot()">▶ Iniciar Massa</button>
                <button type="button" class="btn-acao btn-pausar" onclick="pausarDisparos()">⏸ Pausar</button>

                <div class="cronometro-box">
                    <span id="timerTexto">00:00</span>
                    <div class="barra-progresso-container">
                        <div class="barra-progresso-fill" id="barraProgresso"></div>
                    </div>
                </div>

                <a href="/" class="btn-acao btn-home">🏠 Página Inicial</a>
                <span id="statusBot" style="font-size: 10px; color: #94a3b8;">Pronto</span>
            </div>
        </div>
    </div>

    <div class="main-layout">
        <div class="conteudo-scroll">
            <div class="grid">
            {% if dados %}
                {% for p in dados %}
                {% set card_id = loop.index %}
                <div class="card" id="card-{{ card_id }}" data-nome="{{ p.nome }}" data-telefone="{{ p.telefone_bruto }}">
                    <div class="posto">🏢 {{p.posto}}</div>
                    <div class="nome">👤 {{p.nome}}</div>
                    <div class="info">📱 <strong>Contato:</strong> {{p.telefone_formatado}}</div>
                    {% if p.status %}
                    <div class="info">📌 <strong>Status:</strong> <span style="color: #38bdf8;">{{p.status}}</span></div>
                    {% endif %}

                    {% if filtro_pendencia %}
                    <div class="info" style="margin-top: 6px;">
                        <span id="simbolo-{{card_id}}" style="font-size: 14px; margin-right: 3px;">⚠️</span> 
                        <strong>Pendência:</strong>
                        <input type="text" 
                               id="input-pend-{{card_id}}"
                               value="{{p.pendencia}}" 
                               class="input-pendencia-editavel" 
                               oninput="atualizarPendenciaCard(this, '{{p.nome}}', '{{p.telefone_bruto}}', {{card_id}})">
                    </div>

                    <div class="preview-msg" id="preview-{{card_id}}">
                        💬 <strong>Msg Direta:</strong> {{p.mensagem}}
                    </div>
                    {% endif %}

                    <a class="btn" href="{{p.link}}" target="_blank" id="btn-{{card_id}}" data-linklimpo="{{p.link}}" onclick="registrarEnvioManual('{{ p.nome }}', '{{ p.telefone_bruto }}', {{ card_id }})">💬 Enviar Mensagem</a>
                </div>
                {% endfor %}
            {% else %}
                <div class="sem-pendencia-box">
                    <h3>📭 Nenhum registro encontrado</h3>
                    <p>Não há colaboradores para os filtros ou data selecionados.</p>
                </div>
            {% endif %}
            </div>
        </div>

        <div class="relatorio-lateral">
            <h3 style="font-size: 15px; margin-top: 0; color: #38bdf8;">📊 Relatório Salvo</h3>

            <div class="relatorio-acoes">
                <input type="text" id="buscaHistorico" placeholder="Pesquisar por nome, contato ou mensagem..." oninput="filtrarHistorico()" style="font-size: 11px; padding: 5px 8px; flex: 1;">
                <button type="button" class="btn-limpar-log" onclick="limparHistorico()">Limpar</button>
            </div>

            <div id="containerLogs" style="overflow-y: auto; flex: 1;">
                {% if historico %}
                    {% for h in historico %}
                        <div class="log-item {{ 'log-sucesso' if h[3] else 'log-erro' }}" data-logtext="{{ h[2]|lower }} {{ h[4]|lower }} {{ h[5]|lower }}">
                            <div>
                                <strong>{{ h[1] }}</strong> - {{ h[2] }} 
                                <button type="button" class="btn-maximizar-log" onclick="abrirModalMensagem('{{ h[2] }}', '{{ h[5]|e }}')">🔍 Maximizar</button>
                            </div>
                            <div style="font-size:10px; color:#cbd5e1;">{{ h[4] }}</div>
                            <div class="log-msg-preview">💬 {{ h[5] }}</div>
                        </div>
                    {% endfor %}
                {% else %}
                    <p id="semHistoricoMsg" style="font-size: 12px; color: #64748b;">Nenhum registro.</p>
                {% endif %}
            </div>
        </div>
    </div>

    <!-- Modal Maximizada para Mensagem -->
    <div class="modal-overlay" id="modalMensagem">
        <div class="modal-conteudo">
            <div class="modal-titulo">
                <span>💬 Mensagem Enviada - <span id="modalNomeColaborador"></span></span>
            </div>
            <div class="modal-texto" id="modalTextoConteudo"></div>
            <button type="button" class="btn-fechar-modal" onclick="fecharModalMensagem()">Fechar</button>
        </div>
    </div>

    <script>
        let rodandoBot = false;
        let indiceAtual = 0;
        let intervaloBot = null;
        let timeoutBusca = null;
        let segundosDecorridos = 0;
        let timerIntervalo = null;

        const inputBusca = document.getElementById('buscaInput');
        if(inputBusca) {
            inputBusca.addEventListener('input', function() {
                clearTimeout(timeoutBusca);
                timeoutBusca = setTimeout(() => {
                    document.getElementById('searchForm').submit();
                }, 300);
            });
        }

        function submeterFormulario() { 
            document.getElementById('searchForm').submit(); 
        }

        function atualizarRelogio() {
            const agora = new Date();
            document.getElementById('relogio').innerText = agora.toLocaleTimeString('pt-BR');
        }
        setInterval(atualizarRelogio, 1000);
        atualizarRelogio();

        function toggleDropdown(id) {
            document.querySelectorAll('.multiselect-content').forEach(el => {
                if(el.id !== id) el.classList.remove('show');
            });
            document.getElementById(id).classList.toggle('show');
        }

        window.onclick = function(event) {
            if (!event.target.matches('.multiselect-btn') && !event.target.closest('.multiselect-content')) {
                document.querySelectorAll('.multiselect-content').forEach(el => el.classList.remove('show'));
            }
        }

        function toggleTodos(master, classe) {
            document.querySelectorAll('.' + classe).forEach(cb => cb.checked = master.checked);
            submeterFormulario();
        }

        function detectarSimbolo(texto) {
            const t = texto.toLowerCase();
            if (t.includes('cpf') || t.includes('rg') || t.includes('cnh')) return '🪪';
            if (t.includes('foto') || t.includes('selfie')) return '📷';
            if (t.includes('certidão') || t.includes('nascimento')) return '📜';
            if (t.includes('banco') || t.includes('pix')) return '💳';
            if (t.includes('exame') || t.includes('médico')) return '🩺';
            return '⚠️';
        }

        window.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('.input-pendencia-editavel').forEach((input, index) => {
                const cardId = index + 1;
                const simboloSpan = document.getElementById('simbolo-' + cardId);
                if (simboloSpan && input.value) {
                    simboloSpan.innerText = detectarSimbolo(input.value);
                }
            });
        });

        function atualizarPendenciaCard(inputEl, nome, telefone, cardId) {
            const novaPendencia = inputEl.value;
            const simboloSpan = document.getElementById('simbolo-' + cardId);
            const previewDiv = document.getElementById('preview-' + cardId);
            const btnLink = document.getElementById('btn-' + cardId);

            if(simboloSpan) simboloSpan.innerText = detectarSimbolo(novaPendencia);

            const hora = new Date().getHours();
            let saudacao = "Bom dia";
            if (hora >= 12 && hora < 18) saudacao = "Boa tarde";
            else if (hora >= 18) saudacao = "Boa noite";

            const primeiroNome = nome.split(' ')[0];
            let msg = `Prezado(a) ${primeiroNome}, ${saudacao.toLowerCase()}! Identificamos a pendência: ${novaPendencia}.`;

            if(previewDiv) previewDiv.innerHTML = `💬 <strong>Msg Direta:</strong> ${msg}`;

            const textoEncoded = encodeURIComponent(msg);
            const novoLink = telefone && telefone.length >= 10 ? `https://api.whatsapp.com/send?phone=55${telefone}&text=${textoEncoded}` : '#';

            if(btnLink) {
                btnLink.setAttribute('href', novoLink);
                btnLink.setAttribute('data-linklimpo', novoLink);
            }
        }

        function alternarBot() {
            const cards = document.querySelectorAll('.card');
            if (cards.length === 0) { alert("Nenhum contato na tela para disparar!"); return; }

            rodandoBot = !rodandoBot;
            const btn = document.getElementById('btnIniciar');
            const statusTxt = document.getElementById('statusBot');

            if (rodandoBot) {
                btn.innerText = "⏹ Parar Massa";
                btn.style.background = "#ef4444";
                statusTxt.innerText = "Enviando em Massa...";

                segundosDecorridos = 0;
                timerIntervalo = setInterval(() => {
                    segundosDecorridos++;
                    let min = String(Math.floor(segundosDecorridos / 60)).padStart(2, '0');
                    let seg = String(segundosDecorridos % 60).padStart(2, '0');
                    document.getElementById('timerTexto').innerText = `${min}:${seg}`;
                }, 1000);

                processarProximoDisparo(cards);

                intervaloBot = setInterval(() => {
                    if (!rodandoBot) return;
                    processarProximoDisparo(cards);
                }, 9000);

            } else {
                pausarDisparos();
            }
        }

        function processarProximoDisparo(cards) {
            if (!rodandoBot) return;

            document.querySelectorAll('.card').forEach(c => c.classList.remove('card-ativo'));

            if (indiceAtual >= cards.length) {
                pausarDisparos();
                document.getElementById('statusBot').innerText = "Concluído!";
                return;
            }

            const card = cards[indiceAtual];
            card.classList.add('card-ativo');
            card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

            const nome = card.getAttribute('data-nome');
            const tel = card.getAttribute('data-telefone');
            const linkBtn = card.querySelector('.btn');
            const urlDestino = linkBtn.getAttribute('data-linklimpo');

            const cardId = card.id.replace('card-', '');
            const inputPend = document.getElementById('input-pend-' + cardId);
            let pendenciaTexto = inputPend ? inputPend.value : '';

            const hora = new Date().getHours();
            let saudacao = "Bom dia";
            if (hora >= 12 && hora < 18) saudacao = "Boa tarde";
            else if (hora >= 18) saudacao = "Boa noite";
            const primeiroNome = nome.split(' ')[0];
            const msgFinal = `Prezado(a) ${primeiroNome}, ${saudacao.toLowerCase()}! Identificamos a pendência: ${pendenciaTexto}.`;

            if (tel && tel.length >= 10) {
                let win = window.open(urlDestino, '_blank');
                registrarLogNoBanco(nome, true, `Contato: ${tel}`, msgFinal);
                setTimeout(() => { if (win) win.close(); }, 7000);
            } else {
                registrarLogNoBanco(nome, false, `Contato Inválido: ${tel}`, msgFinal);
            }

            indiceAtual++;
            let progresso = (indiceAtual / cards.length) * 100;
            document.getElementById('barraProgresso').style.width = `${progresso}%`;
        }

        function pausarDisparos() {
            rodandoBot = false;
            clearInterval(intervaloBot);
            clearInterval(timerIntervalo);
            document.querySelectorAll('.card').forEach(c => c.classList.remove('card-ativo'));
            document.getElementById('btnIniciar').innerText = "▶ Iniciar Massa";
            document.getElementById('btnIniciar').style.background = "#22c55e";
            document.getElementById('statusBot').innerText = "Pausado";
            indiceAtual = 0;
        }

        function registrarEnvioManual(nome, tel, cardId) {
            const inputPend = document.getElementById('input-pend-' + cardId);
            let pendenciaTexto = inputPend ? inputPend.value : '';
            const hora = new Date().getHours();
            let saudacao = "Bom dia";
            if (hora >= 12 && hora < 18) saudacao = "Boa tarde";
            else if (hora >= 18) saudacao = "Boa noite";
            const primeiroNome = nome.split(' ')[0];
            const msgFinal = `Prezado(a) ${primeiroNome}, ${saudacao.toLowerCase()}! Identificamos a pendência: ${pendenciaTexto}.`;

            if (tel && tel.length >= 10) {
                registrarLogNoBanco(nome, true, `Manual - Contato: ${tel}`, msgFinal);
            } else {
                registrarLogNoBanco(nome, false, `Erro Manual - Contato Inválido: ${tel}`, msgFinal);
            }
        }

        function registrarLogNoBanco(nome, sucesso, detalhe, mensagem) {
            fetch('/registrar_log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nome: nome, sucesso: sucesso, detalhe: detalhe, mensagem: mensagem })
            }).then(() => {
                setTimeout(() => { carregarHistoricoLateral(); }, 300);
            });
        }

        function limparHistorico() {
            if (confirm("Tem certeza que deseja limpar todo o histórico de envios?")) {
                fetch('/limpar_historico', { method: 'POST' }).then(() => {
                    carregarHistoricoLateral();
                });
            }
        }

        function carregarHistoricoLateral() {
            fetch('/obter_historico')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('containerLogs');
                let html = '';
                if (data.length > 0) {
                    data.forEach(h => {
                        let classe = h[4] ? 'log-sucesso' : 'log-erro';
                        let nomeEscapado = h[2].replace(/'/g, "\\'");
                        let msgEscapada = h[5].replace(/'/g, "\\'");
                        html += `<div class="log-item ${classe}" data-logtext="${h[2].toLowerCase()} ${h[3].toLowerCase()} ${h[5].toLowerCase()}">
                            <div>
                                <strong>${h[1]}</strong> - ${h[2]}
                                <button type="button" class="btn-maximizar-log" onclick="abrirModalMensagem('${nomeEscapado}', '${msgEscapada}')">🔍 Maximizar</button>
                            </div>
                            <div style="font-size:10px; color:#cbd5e1;">${h[3]}</div>
                            <div class="log-msg-preview">💬 ${h[5]}</div>
                        </div>`;
                    });
                } else {
                    html = `<p id="semHistoricoMsg" style="font-size: 12px; color: #64748b;">Nenhum registro.</p>`;
                }
                container.innerHTML = html;
                filtrarHistorico();
            });
        }

        function filtrarHistorico() {
            const termo = document.getElementById('buscaHistorico').value.toLowerCase();
            const itens = document.querySelectorAll('.log-item');
            itens.forEach(item => {
                const texto = item.getAttribute('data-logtext');
                if (texto.includes(termo)) {
                    item.style.display = 'block';
                } else {
                    item.style.display = 'none';
                }
            });
        }

        function abrirModalMensagem(nome, mensagem) {
            document.getElementById('modalNomeColaborador').innerText = nome;
            document.getElementById('modalTextoConteudo').innerText = mensagem;
            document.getElementById('modalMensagem').style.display = 'flex';
        }

        function fecharModalMensagem() {
            document.getElementById('modalMensagem').style.display = 'none';
        }

        let dataAtualCal = new Date();
        const dataSelecionada = "{{ data_selecionada }}";

        function montarCalendario() {
            const ano = dataAtualCal.getFullYear();
            const mes = dataAtualCal.getMonth();
            const hoje = new Date();
            const mesesNomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
            document.getElementById('mesAnoTitulo').innerText = `${mesesNomes[mes]} ${ano}`;

            const primeiroDia = new Date(ano, mes, 1).getDay();
            const ultimoDia = new Date(ano, mes + 1, 0).getDate();

            let html = `<div class="cal-day-name">D</div><div class="cal-day-name">S</div><div class="cal-day-name">T</div><div class="cal-day-name">Q</div><div class="cal-day-name">Q</div><div class="cal-day-name">S</div><div class="cal-day-name">S</div>`;

            for (let i = 0; i < primeiroDia; i++) { html += `<div class="cal-day empty"></div>`; }

            for (let dia = 1; dia <= ultimoDia; dia++) {
                const mesFmt = String(mes + 1).padStart(2, '0');
                const diaFmt = String(dia).padStart(2, '0');
                const dataIso = `${ano}-${mesFmt}-${diaFmt}`;

                let ehHoje = (dia === hoje.getDate() && mes === hoje.getMonth() && ano === hoje.getFullYear());
                let ehSelecionada = (dataIso === dataSelecionada);

                let classeDia = 'cal-day';
                if (ehHoje) classeDia += ' today';
                if (ehSelecionada) classeDia += ' selected';

                html += `<div class="${classeDia}" onclick="selecionarData('${dataIso}')">${dia}</div>`;
            }
            document.getElementById('calendarioGrid').innerHTML = html;
        }

        function mudarMes(dir) { dataAtualCal.setMonth(dataAtualCal.getMonth() + dir); montarCalendario(); }
        function selecionarData(dataIso) { document.getElementById('dataSelecionadaInput').value = dataIso; submeterFormulario(); }
        function limparData() { document.getElementById('dataSelecionadaInput').value = ''; submeterFormulario(); }

        montarCalendario();
    </script>
</body>
</html>
"""


# ================= FUNÇÕES AUXILIARES =================
def limpar(valor):
    return str(valor).strip() if not pd.isna(valor) else ""


def carregar_planilha(link):
    link = link.replace("?e=", "?download=1&")
    response = requests.get(link)
    response.raise_for_status()
    return pd.read_excel(BytesIO(response.content), header=None)


def obter_saudacao():
    hora = datetime.now().hour
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
        return "Boa tarde"
    else:
        return "Boa noite"


# ================= ROTAS DO FLASK =================
@app.route("/")
def home():
    try:
        busca = request.args.get("busca", "").lower()
        filtro_posto = request.args.getlist("filtro_posto")
        filtro_status = request.args.getlist("filtro_status")
        filtro_pendencia = request.args.getlist("filtro_pendencia")
        data_selecionada = request.args.get("data_selecionada", "").strip()

        df = carregar_planilha(SHEET_URL)

        unidades_set = set()
        status_set = set()
        pendencias_set = set()

        for _, row in df.iterrows():
            posto = limpar(row[0]) if len(row) > 0 else ""
            nome = limpar(row[1]) if len(row) > 1 else ""
            status = limpar(row[5]) if len(row) > 5 else ""
            pendencia = limpar(row[6]) if len(row) > 6 else ""

            if not nome or nome.lower() == "nome":
                continue
            if posto:
                unidades_set.add(posto)
            if status:
                status_set.add(status)
            if pendencia:
                pendencias_set.add(pendencia)

        unidades_disponiveis = sorted(list(unidades_set))
        status_disponiveis = sorted(list(status_set))
        pendencias_disponiveis = sorted(list(pendencias_set))

        saudacao = obter_saudacao()
        dados = []

        for _, row in df.iterrows():
            posto = limpar(row[0]) if len(row) > 0 else ""
            nome = limpar(row[1]) if len(row) > 1 else ""
            telefone = limpar(row[4]) if len(row) > 4 else ""
            status = limpar(row[5]) if len(row) > 5 else ""
            pendencia = limpar(row[6]) if len(row) > 6 else ""
            data_coluna = row[7] if len(row) > 7 else None

            if not nome or nome.lower() == "nome":
                continue

            if busca and busca not in nome.lower():
                continue
            if filtro_posto and posto not in filtro_posto:
                continue
            if filtro_status and status not in filtro_status:
                continue
            if filtro_pendencia and (not pendencia or pendencia not in filtro_pendencia):
                continue

            if data_selecionada:
                if pd.isna(data_coluna):
                    continue
                try:
                    dt = pd.to_datetime(data_coluna)
                    data_iso = dt.strftime("%Y-%m-%d")
                    if not data_iso.startswith(data_selecionada):
                        continue
                except:
                    continue

            data_fmt = ""
            if pd.notna(data_coluna):
                try:
                    dt = pd.to_datetime(data_coluna)
                    data_fmt = dt.strftime("%d/%m/%Y")
                except:
                    pass

            num = re.sub(r"\D", "", telefone)
            partes_nome = nome.split()
            primeiro_nome = partes_nome[0] if partes_nome else "Colaborador"

            texto_mensagem = (
                f"Prezado(a) {primeiro_nome}, {saudacao.lower()}! Identificamos a"
                f" pendência: {pendencia}."
            )
            texto_encoded = urllib.parse.quote(texto_mensagem)

            link_wa = (
                f"https://api.whatsapp.com/send?phone=55{num}&text={texto_encoded}"
                if num
                else "#"
            )

            pendencia_card = pendencia if filtro_pendencia else ""
            if not filtro_pendencia:
                texto_mensagem = ""

            dados.append({
                "posto": posto,
                "nome": nome,
                "telefone_bruto": telefone,
                "telefone_formatado": telefone if telefone else "Não cadastrado",
                "status": status,
                "pendencia": pendencia_card,
                "data_fmt": data_fmt,
                "mensagem": texto_mensagem,
                "link": link_wa,
            })

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, hora, nome, sucesso, detalhe, mensagem FROM historico_envios"
            " ORDER BY id DESC LIMIT 50"
        )
        historico = cursor.fetchall()
        conn.close()

        return render_template_string(
            HTML,
            dados=dados,
            busca=busca,
            unidades_disponiveis=unidades_disponiveis,
            status_disponiveis=status_disponiveis,
            pendencias_disponiveis=pendencias_disponiveis,
            filtro_posto=filtro_posto,
            filtro_status=filtro_status,
            filtro_pendencia=filtro_pendencia,
            data_selecionada=data_selecionada,
            historico=historico,
        )

    except Exception as e:
        return f"❌ Erro ao processar: {str(e)}"


@app.route("/registrar_log", methods=["POST"])
def registrar_log():
    dados = request.get_json()
    if dados:
        nome = dados.get("nome")
        sucesso = dados.get("sucesso")
        detalhe = dados.get("detalhe")
        mensagem = dados.get("mensagem", "")
        hora_atual = datetime.now().strftime("%H:%M:%S")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO historico_envios (hora, nome, sucesso, detalhe, mensagem)"
            " VALUES (?, ?, ?, ?, ?)",
            (hora_atual, nome, sucesso, detalhe, mensagem),
        )
        conn.commit()
        conn.close()

    return {"status": "ok"}


@app.route("/obter_historico")
def obter_historico():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, hora, nome, detalhe, sucesso, mensagem FROM historico_envios"
        " ORDER BY id DESC LIMIT 50"
    )
    historico = cursor.fetchall()
    conn.close()
    return historico


@app.route("/limpar_historico", methods=["POST"])
def limpar_historico():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM historico_envios")
    conn.commit()
    conn.close()
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
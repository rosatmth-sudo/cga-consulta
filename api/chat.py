from http.server import BaseHTTPRequestHandler
import json
import os
import csv
import re
import urllib.request

def buscar_dados_relevantes(pergunta, linhas, max_linhas=50):
    """Filtra linhas relevantes baseado na pergunta"""
    pergunta_lower = pergunta.lower()
    
    # Palavras-chave para filtrar
    keywords = []
    
    # Extrai possíveis termos de busca
    termos_comuns = ['cimento', 'tinta', 'parafuso', 'ferramenta', 'eletric', 'hidraulic', 
                     'construcao', 'escritorio', 'limpeza', 'papel', 'caneta', 'computador',
                     'pendente', 'entregue', 'cancelad', 'aguardando', 'sem entrega']
    
    for termo in termos_comuns:
        if termo in pergunta_lower:
            keywords.append(termo)
    
    # Se não encontrou keywords específicas, retorna resumo geral
    if not keywords:
        # Retorna amostra diversificada
        return linhas[:max_linhas]
    
    # Filtra linhas que contêm alguma keyword
    relevantes = []
    for linha in linhas:
        linha_texto = ' '.join(str(v).lower() for v in linha.values())
        for kw in keywords:
            if kw in linha_texto:
                relevantes.append(linha)
                break
    
    return relevantes[:max_linhas] if relevantes else linhas[:max_linhas]

def formatar_contexto(linhas):
    """Formata linhas para contexto do Claude"""
    if not linhas:
        return "Nenhum dado encontrado."
    
    # Colunas mais importantes
    colunas_importantes = ['Descrição', 'Grupo', 'Subgrupo', 'Registrado', 'Autorizado', 
                          'Saldo', 'Valor unitário', 'Compra QT.', 'Compra Valor', 
                          'Status', 'Compra Data', 'Executor', 'Destino']
    
    resultado = []
    for i, linha in enumerate(linhas):
        partes = []
        for col in colunas_importantes:
            if col in linha and linha[col] and str(linha[col]).strip():
                valor = str(linha[col]).strip()
                if valor and valor != 'nan':
                    partes.append(f"{col}: {valor}")
        if partes:
            resultado.append(f"Item {i+1}: " + " | ".join(partes))
    
    return "\n".join(resultado)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Lê o body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            pergunta = data.get('pergunta', '')
            
            if not pergunta:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'erro': 'Pergunta vazia'}).encode())
                return
            
            # Lê a planilha
            csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'planilha.csv')
            linhas = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    linhas.append(row)
            
            # Filtra dados relevantes
            dados_relevantes = buscar_dados_relevantes(pergunta, linhas)
            contexto = formatar_contexto(dados_relevantes)
            
            # Monta prompt
            system_prompt = f"""Voce e um assistente da SEAPE (Secretaria de Administracao Penitenciaria do DF) que responde perguntas sobre compras e materiais.

Dados encontrados na planilha ({len(dados_relevantes)} itens):

{contexto}

Responda de forma clara e objetiva. Use R$ para valores."""

            # Chama Claude API
            api_key = os.environ.get('CLAUDE_API_KEY')
            if not api_key:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'erro': 'API key nao configurada'}).encode())
                return
            
            req_data = json.dumps({
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 1024,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': pergunta}]
            }).encode('utf-8')
            
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=req_data,
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01'
                }
            )
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                resposta = result['content'][0]['text']
            
            # Retorna resposta
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'resposta': resposta}).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'erro': str(e)}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

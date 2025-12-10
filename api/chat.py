from http.server import BaseHTTPRequestHandler
import json
import os
import csv
import urllib.request
import re

def carregar_planilha():
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'planilha.csv')
    linhas = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            linhas.append(row)
    return linhas

def extrair_termos(pergunta):
    """Extrai itens da pergunta"""
    stopwords = ['compras', 'compra', 'compramos', 'comprar', 'tem', 'temos', 'existe', 
                 'existem', 'disponivel', 'disponiveis', 'disponibilidade',
                 'de', 'do', 'da', 'dos', 'das', 'o', 'a', 'os', 'as', 
                 'um', 'uma', 'uns', 'umas', 'e', 'ou', 'para', 'por', 'com', 'sem',
                 'que', 'qual', 'quais', 'como', 'onde', 'quando', 'quanto', 'quanta',
                 'ha', 'havia', 'houve', 'buscar', 'procurar', 'encontrar', 'listar', 
                 'mostrar', 'ver', 'preciso', 'precisamos', 'quero', 'queremos', 
                 'gostaria', 'esse', 'este', 'essa', 'esta', 'ano', 'mes', 'dia',
                 'pra', 'pro', 'nos', 'na', 'no', 'nas', 'nos', 'ja', 'ainda']
    
    texto = pergunta.lower()
    texto = re.sub(r'[;\n\r\t\?\!]', ',', texto)
    texto = re.sub(r'\s+e\s+', ',', texto)
    texto = re.sub(r'\s+ou\s+', ',', texto)
    
    partes = [p.strip() for p in texto.split(',')]
    
    termos = []
    for parte in partes:
        palavras = parte.split()
        palavras_filtradas = [p for p in palavras if p not in stopwords and len(p) > 2]
        if palavras_filtradas:
            termos.append(' '.join(palavras_filtradas))
    
    return termos if termos else None

def detectar_tipo_busca(pergunta):
    """Detecta se é busca de disponibilidade ou histórico"""
    pergunta_lower = pergunta.lower()
    
    historico_keywords = ['compramos', 'comprou', 'compraram', 'comprado', 'comprada',
                          'quando', 'data', 'datas', 'historico', 'ultimas', 'ultimos',
                          'realizadas', 'realizados', 'ja comprou', 'ja compramos']
    
    for kw in historico_keywords:
        if kw in pergunta_lower:
            return 'historico'
    
    return 'disponibilidade'

def converter_percentual(valor):
    """Converte valor de % para float"""
    try:
        if valor is None or valor == '' or valor == 'nan':
            return 0.0
        v = float(valor)
        return v if v <= 1 else v / 100
    except:
        return 0.0

def converter_dias(valor):
    """Converte dias restantes para int"""
    try:
        if valor is None or valor == '' or valor == 'nan':
            return 0
        return int(float(valor))
    except:
        return 0

def buscar_disponibilidade(termos, linhas):
    """Busca itens disponíveis (não vencidos e com saldo)"""
    resultados = {}
    
    for termo in termos:
        termo_lower = termo.lower()
        encontrados = []
        
        for linha in linhas:
            descricao = str(linha.get('Descrição', '')).lower()
            
            if termo_lower in descricao:
                dias = converter_dias(linha.get('Dias restantes', 0))
                perc = converter_percentual(linha.get('%', 0))
                
                # Filtra: não vencido (dias > 0) e não 100% utilizado
                if dias > 0 and perc < 1.0:
                    encontrados.append({
                        'descricao': linha.get('Descrição', ''),
                        'arp': linha.get('ARP', ''),
                        'fonte': linha.get('Fonte', ''),
                        'saldo': linha.get('Saldo', ''),
                        'autorizado': linha.get('Autorizado', ''),
                        'dias_restantes': dias,
                        'percentual_usado': f"{perc*100:.0f}%",
                        'valor_unitario': linha.get('Valor unitário', ''),
                        'aba': linha.get('Aba', '')
                    })
        
        resultados[termo] = encontrados
    
    return resultados

def buscar_historico(termos, linhas):
    """Busca histórico de compras realizadas"""
    resultados = {}
    
    for termo in termos:
        termo_lower = termo.lower()
        encontrados = []
        
        for linha in linhas:
            descricao = str(linha.get('Descrição', '')).lower()
            
            if termo_lower in descricao:
                compra_qt = linha.get('Compra QT.', '')
                compra_data = linha.get('Compra Data', '')
                
                # Só inclui se tem dados de compra
                if compra_qt and str(compra_qt) != 'nan' and str(compra_qt) != '':
                    encontrados.append({
                        'descricao': linha.get('Descrição', ''),
                        'arp': linha.get('ARP', ''),
                        'fonte': linha.get('Fonte', ''),
                        'compra_qt': compra_qt,
                        'compra_data': compra_data,
                        'compra_valor': linha.get('Compra Valor', ''),
                        'status': linha.get('Status', ''),
                        'destino': linha.get('Destino', ''),
                        'aba': linha.get('Aba', '')
                    })
        
        resultados[termo] = encontrados
    
    return resultados

def formatar_disponibilidade(resultados):
    """Formata resultados de disponibilidade para o Claude"""
    saida = []
    
    for termo, itens in resultados.items():
        saida.append(f"\n### {termo.upper()} - {len(itens)} opção(ões) disponível(is)")
        
        if not itens:
            saida.append("Nenhum item disponível (vencido ou 100% utilizado).")
            continue
        
        for i, item in enumerate(itens, 1):
            saida.append(f"""
Item {i}:
- Descrição: {item['descricao'][:100]}...
- ARP: {item['arp']} | Fonte: {item['fonte']}
- Saldo disponível: {item['saldo']} (de {item['autorizado']} autorizado)
- Utilizado: {item['percentual_usado']}
- Vence em: {item['dias_restantes']} dias
- Valor unitário: R$ {item['valor_unitario']}""")
    
    return '\n'.join(saida)

def formatar_historico(resultados):
    """Formata resultados de histórico para o Claude"""
    saida = []
    
    for termo, itens in resultados.items():
        saida.append(f"\n### {termo.upper()} - {len(itens)} compra(s) encontrada(s)")
        
        if not itens:
            saida.append("Nenhuma compra encontrada.")
            continue
        
        for i, item in enumerate(itens, 1):
            saida.append(f"""
Compra {i}:
- Item: {item['descricao'][:80]}...
- ARP: {item['arp']} | Fonte: {item['fonte']}
- Quantidade: {item['compra_qt']}
- Data: {item['compra_data']}
- Valor: R$ {item['compra_valor']}
- Status: {item['status']}
- Destino: {item['destino']}""")
    
    return '\n'.join(saida)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
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
            
            # Carrega planilha
            linhas = carregar_planilha()
            
            # Extrai termos de busca
            termos = extrair_termos(pergunta)
            
            # Detecta tipo de busca
            tipo = detectar_tipo_busca(pergunta)
            
            # Executa busca apropriada
            if tipo == 'historico':
                resultados = buscar_historico(termos, linhas) if termos else {}
                contexto = formatar_historico(resultados)
                instrucao = "O usuário quer saber sobre COMPRAS JÁ REALIZADAS."
            else:
                resultados = buscar_disponibilidade(termos, linhas) if termos else {}
                contexto = formatar_disponibilidade(resultados)
                instrucao = "O usuário quer saber sobre ITENS DISPONÍVEIS PARA COMPRA (não vencidos e com saldo)."
            
            # Monta prompt
            system_prompt = f"""Você é um assistente da SEAPE (Secretaria de Administração Penitenciária do DF).
{instrucao}

Planilha total: {len(linhas)} itens
Termos buscados: {', '.join(termos) if termos else 'nenhum específico'}

RESULTADOS DA BUSCA:
{contexto}

INSTRUÇÕES:
- Responda de forma clara e organizada
- Se não encontrou itens, informe claramente
- Use R$ para valores
- Fonte "IRP" = compra compartilhada | Fonte "SEAPE" = compra própria
- Seja direto e objetivo"""

            # Chama Claude
            api_key = os.environ.get('CLAUDE_API_KEY')
            if not api_key:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'erro': 'API key não configurada'}).encode())
                return
            
            req_data = json.dumps({
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 2048,
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

import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import unquote
import threading
from fastapi import FastAPI, HTTPException

# --- Configurações e Variáveis Globais ---
API_KEY_2CAPTCHA = 'e25216456f6abcb50c6a53fb885093a6'
LOGIN_URL = 'https://painelcliente.com/'
USUARIO = 'leal1221'
SENHA = 'digitaltv2024'

app = FastAPI()

# Variável global para armazenar a sessão ativa
active_session = None
session_lock = threading.Lock()  # Para evitar condições de corrida

# --- Funções do Script Original ---

def resolver_captcha(sitekey):
    captcha_data = {
        'key': API_KEY_2CAPTCHA,
        'method': 'turnstile',
        'sitekey': sitekey,
        'pageurl': LOGIN_URL,
        'json': 1
    }

    resposta = requests.post('https://2captcha.com/in.php', data=captcha_data).json()
    if resposta['status'] != 1:
        raise Exception(f'Erro ao enviar captcha: {resposta.get("error_text", "Erro desconhecido")}')

    captcha_id = resposta['request']
    print("Aguardando resolução do captcha...")

    for _ in range(40):
        resposta = requests.get(
            f'https://2captcha.com/res.php?key={API_KEY_2CAPTCHA}&action=get&id={captcha_id}&json=1'
        ).json()
        
        if resposta['status'] == 1:
            return resposta['request']
        elif resposta['request'] != 'CAPCHA_NOT_READY':
            raise Exception(f'Erro ao resolver captcha: {resposta.get("error_text", "Erro desconhecido")}')
        time.sleep(5)
    
    raise Exception('Timeout na resolução do captcha')

def fazer_login():
    session = requests.Session()
    
    # Obter página de login
    response = session.get(LOGIN_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extrair CSRF Token
    token_element = soup.find('input', {'name': 'token'})
    if not token_element or not token_element.get('value'):
        raise Exception('CSRF token não encontrado')
    csrf_token = token_element['value']
    
    # Resolver Captcha
    sitekey = '0x4AAAAAAAx8gsAnBKZ2qcgT'
    token_captcha = resolver_captcha(sitekey)
    
    # Submeter login
    dados_login = {
        'username': USUARIO,
        'password': SENHA,
        'token': csrf_token,
        'cf-turnstile-response': token_captcha
    }

    resposta_login = session.post(
        f'{LOGIN_URL}/index',
        data=dados_login,
        allow_redirects=False
    )

    if resposta_login.status_code != 302:
        raise Exception('Falha no login - Verifique as credenciais')
    
    print("✅ Login realizado com sucesso!")
    return session

def criar_test(session, adulto=True):
    package_id = 1 if adulto else 0
    test_url = f"{LOGIN_URL}sys/API.php?action=create_test&package_id={package_id}"
    
    response = session.get(test_url)
    
    if response.status_code != 200:
        raise Exception('Erro ao criar teste')
    
    return response.text

def extrair_dados(html):
    soup = BeautifulSoup(html, 'html.parser')
    
    dados = {
        'usuario': '',
        'senha': '',
        'vencimento': '',
        'observacoes': '',
        'links': {}
    }

    # Extrair username e password
    username = soup.find('input', {'id': 'username'})
    if username:
        dados['usuario'] = username.get('value', '')
    
    password = soup.find('input', {'id': 'password'})
    if password:
        dados['senha'] = password.get('value', '')

    # Extrair vencimento
    vencimento = soup.find('p', class_='h6 text-primary')
    if vencimento:
        dados['vencimento'] = vencimento.text.strip().replace('Vencimento: ', '')

    # Extrair observações
    observacoes = soup.find('textarea', {'name': 'reseller_notes'})
    if observacoes:
        dados['observacoes'] = observacoes.text.strip()

    # Extrair links com labels corretos
    grupos = soup.select('div.input-group')
    for grupo in grupos:
        label = grupo.find('span', class_='input-group-text')
        input_field = grupo.find('input', {'type': 'text'})
        
        if label and input_field:
            link_label = label.get_text(strip=True)
            link_value = unquote(input_field.get('value', '')).replace('&amp;', '&')
            dados['links'][link_label] = link_value

    return dados

# --- Endpoint da API ---

@app.get("/create_test")
def api_create_test(adulto: bool = True):
    """
    Endpoint que cria um teste e retorna os dados extraídos.
    O parâmetro "adulto" (booleano) define se o teste é COM ou SEM Adultos.
    """
    global active_session
    # Verificar se já existe uma sessão ativa; se não, realizar login.
    with session_lock:
        if active_session is None:
            try:
                active_session = fazer_login()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Erro ao fazer login: {str(e)}")
    try:
        html = criar_test(active_session, adulto)
        dados = extrair_dados(html)
        return dados
    except Exception as e:
        # Se ocorrer erro (possivelmente relacionado à expiração da sessão),
        # limpamos a sessão para que na próxima chamada seja feito novo login.
        with session_lock:
            active_session = None
        raise HTTPException(status_code=500, detail=f"Erro ao criar teste: {str(e)}")

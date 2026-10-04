from datetime import datetime
import os
import threading
import time
import webbrowser
from flask import Flask, jsonify, render_template
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

URL_CHAT = 'https://chat.sonax.net.br/app/chat'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')

LOGIN_EMAIL = 'atendente02@amazoninf.com.br'
LOGIN_SENHA = 'Amazon@2025'

# Seletores XPATH
XPATH_CONTADOR_BOT = '/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div/div[2]/div[1]/span[1]/div/span'
XPATH_CONTADOR_FILA = '/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div[1]/div[2]/div[1]/span[2]/div/span'

XPATH_ABA_FILA = '/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div[1]/div[2]/div[1]/span[2]'
XPATH_PRIMEIRO_CHAT_FILA = '/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div[1]/div[2]/app-protocol-list/div/app-protocol-item/div/div/div[1]/div/div/div/div/div[1]/p'

XPATH_BOTAO_ASSUMIR = '/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div[2]/div/app-protocol-view/div/app-protocol-view-messages/div/div[2]/div[2]/div/button'
XPATH_BOTAO_CONFIRMA_SIM = "(//button[contains(., 'Sim')])[last()]"

app = Flask(__name__)
page = None
playwright_instance = None
browser = None
bot_ativo = False
status_message = 'A iniciar...'
bot_logs = []

if not os.path.exists(DOWNLOAD_DIR):
  os.makedirs(DOWNLOAD_DIR)


def add_log(mensagem, tipo='info'):
  hora = datetime.now().strftime('%H:%M:%S')
  bot_logs.insert(0, {'hora': hora, 'msg': mensagem, 'tipo': tipo})
  if len(bot_logs) > 100:
    bot_logs.pop()
  print(f'[{hora}] {mensagem}')


def force_click(xpath, timeout=2000):
  """Clica no elemento usando o clique nativo do Playwright com fallback via JS."""
  try:
    element = page.locator(f'xpath={xpath}')
    element.wait_for(state='visible', timeout=timeout)
    element.click(force=True, timeout=timeout)
    return True
  except Exception:
    return False


def setup_driver_and_login():
  global page, playwright_instance, browser, status_message

  try:
    playwright_instance = sync_playwright().start()

    # Inicializa o Chromium com configurações equivalentes
    browser = playwright_instance.chromium.launch(
        headless=False, args=['--start-maximized', '--ignore-certificate-errors']
    )

    context = browser.new_context(
        no_viewport=True, accepts_downloads=True, downloads_path=DOWNLOAD_DIR
    )

    page = context.new_page()

    status_message = 'Login...'
    page.goto('https://chat.sonax.net.br/login')

    # Preenchimento e clique usando seletores Playwright
    page.locator('input').first.fill(LOGIN_EMAIL)
    page.locator('input').nth(1).fill(LOGIN_SENHA)
    page.locator('button').click()

    status_message = 'Carregando...'
    page.wait_for_url('**/chat**', timeout=30000)
    page.wait_for_timeout(3000)  # Aguarda estabilizar a página

    status_message = 'Pronto!'
    add_log('Login OK. Ative o bot.', 'success')
    return True

  except Exception as e:
    status_message = 'Erro Login'
    add_log(f'Falha Login: {str(e)[:100]}', 'error')
    return False


def bot_loop():
  global bot_ativo, page, status_message
  time.sleep(2)
  status_message = 'Monitorando...'

  while True:
    try:
      if not bot_ativo:
        time.sleep(1)
        continue

      fila_count = 0
      try:
        elem = page.locator(f'xpath={XPATH_CONTADOR_FILA}')
        txt = ''.join(filter(str.isdigit, elem.inner_text(timeout=1000)))
        fila_count = int(txt) if txt else 0
      except Exception:
        pass

      if fila_count > 0:
        status_message = f'ATACANDO FILA ({fila_count})'
        add_log(f'Fila {fila_count}. Atacando...', 'warning')

        try:
          if not force_click(XPATH_ABA_FILA, 1000):
            raise Exception('Aba inacessível')
          page.wait_for_timeout(300)

          if not force_click(XPATH_PRIMEIRO_CHAT_FILA, 2000):
            raise Exception('Contato não apareceu')
          page.wait_for_timeout(500)

          if not force_click(XPATH_BOTAO_ASSUMIR, 2000):
            raise Exception('Botão Assumir sumiu')

          if not force_click(XPATH_BOTAO_CONFIRMA_SIM, 2000):
            raise Exception('Botão Sim falhou')

          add_log('ASSUMIDO!', 'success')
          status_message = 'Sucesso! Aguardando próximo...'
          page.wait_for_timeout(3000)

        except Exception as e:
          add_log(f'Falha na tentativa: {str(e)[:100]}', 'error')
          force_click(XPATH_ABA_FILA, 1000)
          page.wait_for_timeout(500)

      else:
        try:
          elem_bot = page.locator(f'xpath={XPATH_CONTADOR_BOT}')
          txt_bot = ''.join(
              filter(str.isdigit, elem_bot.inner_text(timeout=1000))
          )
          bot_c = int(txt_bot) if txt_bot else 0

          if bot_c > 0:
            status_message = f'Bot: {bot_c}'
            force_click(XPATH_ABA_FILA, 1000)
            page.wait_for_timeout(700)
          else:
            status_message = 'Monitorando...'
            page.wait_for_timeout(500)
        except Exception:
          page.wait_for_timeout(500)

    except Exception as e:
      add_log(f'Erro Loop: {str(e)[:100]}', 'error')
      time.sleep(2)


@app.route('/')
def index():
  return render_template('index.html')


@app.route('/status')
def get_status():
  return jsonify(
      {'status': status_message, 'ativo': bot_ativo, 'logs': bot_logs}
  )


@app.route('/toggle', methods=['POST'])
def toggle_bot():
  global bot_ativo
  if page is None:
    return jsonify({'success': False})
  bot_ativo = not bot_ativo
  add_log('Bot Ativado' if bot_ativo else 'Bot Pausado', 'info')
  return jsonify({'success': True, 'ativo': bot_ativo})


if __name__ == '__main__':
  if setup_driver_and_login():
    bot_ativo = True
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()
    threading.Timer(
        1.5, lambda: webbrowser.open('http://127.0.0.1:5000')
    ).start()
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
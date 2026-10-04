from datetime import datetime
import os
import threading
import time
import webbrowser
from flask import Flask, jsonify, render_template
from playwright.sync_api import sync_playwright

# Configurações do Ambiente e Credenciais
URL_LOGIN = "https://chat.sonax.net.br/login"
URL_CHAT = "https://chat.sonax.net.br/app/chat"

LOGIN_EMAIL = "atendente02@amazoninf.com.br"
LOGIN_SENHA = "Amazon@2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


class SonaxBot:
    """Gerencia a automação do Playwright para o Sonax Chat."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.ativo = False
        self.status = "A iniciar..."
        self.logs = []

    def add_log(self, mensagem: str, tipo: str = "info"):
        hora = datetime.now().strftime("%H:%M:%S")
        self.logs.insert(0, {"hora": hora, "msg": mensagem, "tipo": tipo})
        if len(self.logs) > 100:
            self.logs.pop()
        print(f"[{hora}] [{tipo.upper()}] {mensagem}")

    def iniciar_e_logar(self) -> bool:
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=False,
                args=["--start-maximized", "--ignore-certificate-errors"],
            )

            context = self.browser.new_context(
                no_viewport=True,
                accepts_downloads=True,
                downloads_path=DOWNLOAD_DIR,
            )
            self.page = context.new_page()

            self.status = "Realizando Login..."
            self.add_log("Acessando página de login...", "info")
            self.page.goto(URL_LOGIN)

            # Preenchimento de login via seletores robustos
            self.page.locator("input[type='email'], input").first.fill(
                LOGIN_EMAIL
            )
            self.page.locator("input[type='password'], input").nth(1).fill(
                LOGIN_SENHA
            )
            self.page.locator("button[type='submit'], button").first.click()

            self.status = "Carregando sistema..."
            self.page.wait_for_url("**/chat**", timeout=30000)
            self.page.wait_for_timeout(3000)

            self.status = "Pronto!"
            self.add_log("Login efetuado com sucesso.", "success")
            return True

        except Exception as e:
            self.status = "Erro no Login"
            self.add_log(f"Falha ao realizar login: {str(e)[:100]}", "error")
            return False

    def force_click(self, selector: str, timeout: int = 2000) -> bool:
        """Tenta clicar em um elemento de forma resiliente."""
        try:
            locator = (
                self.page.locator(f"xpath={selector}")
                if selector.startswith("/") or selector.startswith("(")
                else self.page.locator(selector)
            )
            locator.wait_for(state="visible", timeout=timeout)
            locator.click(force=True, timeout=timeout)
            return True
        except Exception:
            return False

    def obter_contador_fila(self) -> int:
        try:
            # Busca números no texto da aba/indicador de fila
            selector = "app-chat-home span:has-text('Fila'), app-protocol-list"
            elem = self.page.locator(
                f"xpath=/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div[1]/div[2]/div[1]/span[2]/div/span"
            )
            txt = "".join(filter(str.isdigit, elem.inner_text(timeout=1000)))
            return int(txt) if txt else 0
        except Exception:
            return 0

    def assumir_proximo_atendimento(self) -> bool:
        """Executa a sequência de cliques para capturar um atendimento."""
        # XPaths de ação (mantidos estruturados)
        xpath_aba_fila = "/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div[1]/div[2]/div[1]/span[2]"
        xpath_primeiro_chat = "/html/body/app-root/app-layout/ng-sidebar-container/div/div/app-chat-home/app-content/main/div/div/div[1]/div[2]/app-protocol-list/div/app-protocol-item/div/div/div[1]"
        xpath_btn_assumir = "//button[contains(., 'Assumir')]"
        xpath_btn_sim = "(//button[contains(., 'Sim')])[last()]"

        if not self.force_click(xpath_aba_fila, 1000):
            raise Exception("Erro ao clicar na Aba Fila")
        self.page.wait_for_timeout(300)

        if not self.force_click(xpath_primeiro_chat, 2000):
            raise Exception("Contato da fila não carregou")
        self.page.wait_for_timeout(500)

        if not self.force_click(xpath_btn_assumir, 2000):
            raise Exception("Botão 'Assumir' não encontrado")

        if not self.force_click(xpath_btn_sim, 2000):
            raise Exception("Confirmação ('Sim') falhou")

        return True

    def loop_monitoramento(self):
        """Loop principal do robô."""
        time.sleep(2)
        self.status = "Monitorando..."

        while True:
            try:
                if not self.ativo:
                    time.sleep(1)
                    continue

                fila_count = self.obter_contador_fila()

                if fila_count > 0:
                    self.status = f"ATACANDO FILA ({fila_count})"
                    self.add_log(
                        f"Fila detectada com {fila_count} chamado(s). Atacando...",
                        "warning",
                    )

                    try:
                        if self.assumir_proximo_atendimento():
                            self.add_log(
                                "Atendimento assumido com sucesso!", "success"
                            )
                            self.status = "Sucesso! Aguardando próximo..."
                            self.page.wait_for_timeout(3000)
                    except Exception as err:
                        self.add_log(f"Falha na tentativa: {err}", "error")
                        self.page.wait_for_timeout(500)

                else:
                    self.status = "Monitorando..."
                    self.page.wait_for_timeout(800)

            except Exception as e:
                self.add_log(f"Erro no loop principal: {str(e)[:100]}", "error")
                time.sleep(2)


# Instância Global do Bot
bot = SonaxBot()

# Servidor Flask
app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/status")
def get_status():
    return jsonify(
        {"status": bot.status, "ativo": bot.ativo, "logs": bot.logs}
    )


@app.route("/toggle", methods=["POST"])
def toggle_bot():
    if bot.page is None:
        return jsonify({"success": False, "message": "Navegador não iniciado"})

    bot.ativo = not bot.ativo
    bot.add_log("Bot Ativado" if bot.ativo else "Bot Pausado", "info")
    return jsonify({"success": True, "ativo": bot.ativo})


if __name__ == "__main__":
    if bot.iniciar_e_logar():
        bot.ativo = True

        # Inicia a thread de monitoramento em segundo plano
        bot_thread = threading.Thread(
            target=bot.loop_monitoramento, daemon=True
        )
        bot_thread.start()

        # Abre a interface local automaticamente
        threading.Timer(
            1.5, lambda: webbrowser.open("http://127.0.0.1:5000")
        ).start()

        # Executa o painel Web
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
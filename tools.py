import time
import sys
from pathlib import Path
from pywinauto import Application, mouse
import psutil
import pyperclip

# ──────────────────────────────────────────────
# CONFIGURAÇÕES
# ──────────────────────────────────────────────
PASTA = Path(r"C:\Users\p0046863\Desktop\lotaçãotools")
ARQUIVO_PESSOAS = PASTA / "cadastrarpessoas.txt"

QUANTIDADE_DE_GABINETES = 10
PAPEL_MEMBRO = "Outros"

PAUSA_CURTA = 1.0
PAUSA_MEDIA = 2.5
PAUSA_CARREGAMENTO_SISTEMA = 15.0


# ──────────────────────────────────────────────
# FUNÇÕES DE APOIO
# ──────────────────────────────────────────────
def ler_pessoas(caminho: Path) -> list:
    if not caminho.exists(): return []
    with open(caminho, "r", encoding="utf-8") as f:
        return [l.strip() for l in f.readlines() if l.strip()]


def encontrar_pid_themis():
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if "themis" in proc.info['name'].lower(): return proc.info['pid']
        except:
            pass
    return None


def conectar_themis():
    pid = encontrar_pid_themis()
    if not pid: sys.exit(1)
    app = Application(backend="win32").connect(process=pid)
    janela = app.top_window()
    janela.set_focus()
    return app, janela


# ──────────────────────────────────────────────
# CICLO COM CLIQUES POR COORDENADA (FOCO EM DIGITAR)
# ──────────────────────────────────────────────
def realizar_ciclo_completo(app, salto_gabinete, nome_pessoa):
    try:
        dlg = app.window(title_re=".*Assistente de Grupo.*")
        dlg.wait(wait_for='ready', timeout=20)
        dlg.set_focus()

        # 1. SELEÇÃO DO GABINETE
        dlg.type_keys("{TAB}{DOWN 6}{ENTER}")
        time.sleep(PAUSA_MEDIA)
        dlg.type_keys("{TAB}{HOME}")
        for _ in range(4 + salto_gabinete): dlg.type_keys("{DOWN}")

        # 2. AVANÇAR ATÉ A TELA DE MEMBROS
        dlg.type_keys("{TAB}{TAB}{ENTER}")
        time.sleep(PAUSA_MEDIA)
        dlg.type_keys("{ENTER}")

        print(f"      [AGUARDE] Carregando tela de membros...")
        time.sleep(PAUSA_CARREGAMENTO_SISTEMA)

        # 3. DIGITAR O NOME (USANDO COORDENADA RELATIVA)
        # Em vez de procurar o campo, clicamos no local onde ele fica (topo esquerdo da área branca)
        rect = dlg.rectangle()
        # Clica na caixa de texto (ajuste os valores 150, 100 se necessário)
        mouse.click(button='left', coords=(rect.left + 150, rect.top + 100))
        time.sleep(0.5)

        # Limpa e Cola
        dlg.type_keys("^a{BACKSPACE}")
        time.sleep(0.5)
        pyperclip.copy(nome_pessoa)
        dlg.type_keys("^v")
        time.sleep(0.5)
        dlg.type_keys("{ENTER}")

        print(f"      [AÇÃO] Nome inserido: {nome_pessoa}. Aguardando filtro...")
        time.sleep(5.0)

        # 4. SELECIONAR NA LISTA (Clica logo abaixo da busca)
        mouse.click(button='left', coords=(rect.left + 150, rect.top + 160))
        time.sleep(1.0)

        # 5. INCLUIR NOVO -> PAPEL -> ATUALIZAR
        # Usando os atalhos de teclado (Alt+I e Alt+U) que são mais seguros
        dlg.type_keys("%i")  # Alt + I
        time.sleep(PAUSA_MEDIA)

        dlg.type_keys("{TAB}Outros{ENTER}")
        time.sleep(PAUSA_MEDIA)

        dlg.type_keys("%u")  # Alt + U
        time.sleep(PAUSA_MEDIA)

        # 6. FINALIZAÇÃO (Avançar e Finalizar)
        dlg.type_keys("{ENTER}")  # Avançar >>
        time.sleep(PAUSA_MEDIA)
        dlg.type_keys("{ENTER}")  # Finalizar
        time.sleep(PAUSA_MEDIA)
        dlg.type_keys("{ENTER}")  # OK final do resumo

    except Exception as e:
        print(f"      [ERRO NO CICLO] {e}")
        try:
            dlg.type_keys("{ESC}")
        except:
            pass


def main():
    lista = ler_pessoas(ARQUIVO_PESSOAS)
    for g in range(QUANTIDADE_DE_GABINETES):
        for p_index, pessoa in enumerate(lista):
            print(f"  -> Processando: {pessoa}")
            app, janela = conectar_themis()
            janela.set_focus()
            janela.type_keys("%CA")
            realizar_ciclo_completo(app, g, pessoa)
            time.sleep(PAUSA_MEDIA)


if __name__ == "__main__":
    main()
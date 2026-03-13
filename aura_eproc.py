import threading
import time
import os
import csv
import tkinter as tk
from tkinter import messagebox, filedialog, ttk

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# ===============================
# CONFIGURAÇÕES E GLOBAIS
# ===============================
CAMINHO_PDF = None
CAMINHO_PLANILHA = None
ARQUIVO_HISTORICO = 'processos_ajuizados.csv'
USUARIO = None
SENHA = None
URL = None

def salvar_no_historico(dados):
    colunas = ["Data", "Classe", "Magistrado", "Processo", "Chave"]
    file_exists = os.path.isfile(ARQUIVO_HISTORICO)
    with open(ARQUIVO_HISTORICO, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=colunas)
        if not file_exists:
            writer.writeheader()
        writer.writerow(dados)

def capturar_dados_finais(driver, wait):
    try:
        num_processo = wait.until(EC.presence_of_element_located((By.ID, "lblDesNumProcesso"))).text
        classe = driver.find_element(By.ID, "lblDesClasse").text
        juiz = driver.find_element(By.ID, "lblDesJuiz").text
        chave = driver.find_element(By.ID, "lblDesChaveConsulta").text
        dados = {
            "Data": time.strftime("%d/%m/%Y"),
            "Classe": classe.strip(),
            "Magistrado": juiz.strip(),
            "Processo": num_processo.strip(),
            "Chave": chave.strip()
        }
        salvar_no_historico(dados)
        return dados
    except:
        return None

def clicar_seguro(driver, wait, xpath):
    try:
        elemento = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", elemento)
    except:
        pass

def proxima(driver):
    driver.execute_script('var btn = document.querySelector("#btnProxima"); if(btn) btn.click();')

def campo_visivel(driver, elemento_id):
    """Verifica se um campo existe e está visível na tela."""
    try:
        el = driver.find_elements(By.ID, elemento_id)
        return el and el[0].is_displayed()
    except:
        return False

def incluir_autocomplete(driver, wait, actions, campo_id, div_id, nome, btn_incluir_xpath):
    """Digita no campo autocomplete, aguarda sugestão, clica com ActionChains e inclui."""
    campo = wait.until(EC.presence_of_element_located((By.ID, campo_id)))
    # Clica para disparar onclick (limpa valor padrao como "Digite para selecionar...")
    driver.execute_script("arguments[0].click();", campo)
    time.sleep(0.5)
    campo.clear()
    # Limpa via JS caso ainda tenha valor residual
    driver.execute_script("arguments[0].value = '';", campo)
    campo.send_keys(nome[:30])
    time.sleep(3)
    # Aguarda o dropdown ficar visivel
    wait.until(EC.visibility_of_element_located((By.ID, div_id)))
    time.sleep(0.5)
    sugestao = driver.find_element(By.XPATH, f"//div[@id='{div_id}']//li[1]/a")
    # Move o mouse ate a sugestao e clica (simula comportamento humano)
    actions.move_to_element(sugestao).pause(0.3).click().perform()
    time.sleep(2)
    clicar_seguro(driver, wait, btn_incluir_xpath)
    time.sleep(2)

# ===============================
# ROBÔ PRINCIPAL (AURA)
# ===============================
def executar_peticionamento_lote(status, perfil_cinprot=False):
    global CAMINHO_PDF, CAMINHO_PLANILHA

    try:
        if not CAMINHO_PDF or not CAMINHO_PLANILHA:
            messagebox.showerror("AURA", "Selecione o PDF e a Planilha CSV.")
            return

        status.config(text="Status: Inicializando Chrome...")
        chrome_options = Options()
        chrome_options.add_experimental_option("detach", True)
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        wait = WebDriverWait(driver, 60)
        actions = ActionChains(driver)

        if not URL:
            messagebox.showerror("AURA", "Informe a URL do sistema.")
            return
        driver.get(URL)
        driver.maximize_window()

        # LOGIN
        if not USUARIO or not SENHA:
            messagebox.showerror("AURA", "Informe o usuário e a senha.")
            return
        status.config(text="Status: Autenticando...")
        wait.until(EC.presence_of_element_located((By.ID, "txtUsuario"))).send_keys(USUARIO)
        driver.find_element(By.ID, "pwdSenha").send_keys(SENHA)
        clicar_seguro(driver, wait, '//*[@id="sbmEntrar"]')

        # PERFIL
        if perfil_cinprot:
            clicar_seguro(driver, wait, '//*[@data-descricao="DIRETOR DISTRIBUIÇÃO / CINPROT"]')
        else:
            clicar_seguro(driver, wait, '//*[@id="tr1"]')
        clicar_seguro(driver, wait, '//*[@id="action-bar"]/a[1]')

        with open(CAMINHO_PLANILHA, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for idx, linha in enumerate(reader):
                num_fila = idx + 1
                status.config(text=f"Processando Linha {num_fila}...")

                time.sleep(2)
                wait.until(EC.presence_of_element_located((By.XPATH, "//a[@aria-label='Petição Inicial']")))
                clicar_seguro(driver, wait, "//a[@aria-label='Petição Inicial']")

                id_area    = int(linha['AREA'].split("POS ")[-1])
                id_classe  = int(linha['Classeprocessual'].split("POS ")[-1])
                proc_orig  = str(linha['Numero de processo originario']).strip()
                tipo_doc    = str(linha.get('Tipodocumento', 'Petição inicial')).strip()
                tipo_autor  = str(linha.get('Tipoautor', 'Pessoa física')).strip().replace("\n", "").replace("\r", "")
                tipo_reu    = str(linha.get('Tiporeu', 'Pessoa física')).strip().replace("\n", "").replace("\r", "")
                assunto     = str(linha.get('Assunto ', linha.get('Assunto', ''))).strip()

                tem_originario = proc_orig and proc_orig.upper() != "NAO PRECISA" and proc_orig.lower() != "nan"

                def extrair_cpf(texto):
                    """Extrai CPF de strings como 'Pessoa física = 13642624600 (Nome)'"""
                    import re
                    match = re.search(r'=\s*(\d{8,11})', texto.replace(".", "").replace("-", ""))
                    return match.group(1).zfill(11) if match else None

                def extrair_nome(texto):
                    """Extrai nome após '=' removendo CPF e parênteses"""
                    import re
                    # Remove CPF e parênteses, retorna só o nome
                    parte = texto.split("=", 1)[-1].strip()
                    parte = re.sub(r'\d[\d\.\-]+', '', parte)  # remove CPF
                    parte = re.sub(r'\(.*?\)', '', parte)       # remove parênteses
                    return parte.strip()

                # --- Detecta tipo do autor ---
                tipo_autor_upper = tipo_autor.upper()
                cpf_autor = extrair_cpf(tipo_autor) or "06935703697"
                if tipo_autor_upper.startswith("ENTIDADE ="):
                    nome_entidade_autor = extrair_nome(tipo_autor)
                    modo_autor = "ENTIDADE"
                elif tipo_autor_upper.startswith("AUTORIDADE COATORA ="):
                    nome_autoridade_autor = extrair_nome(tipo_autor)
                    modo_autor = "AUTORIDADE"
                else:
                    modo_autor = "PESSOA"

                # --- Detecta tipo do réu ---
                tipo_reu_upper = tipo_reu.upper()
                cpf_reu = extrair_cpf(tipo_reu) or "10652203671"
                if tipo_reu_upper.startswith("JUÍZO =") or tipo_reu_upper.startswith("JUIZO ="):
                    nome_juizo = extrair_nome(tipo_reu)
                    modo_reu = "JUIZO"
                elif tipo_reu_upper.startswith("ENTIDADE ="):
                    nome_entidade_reu = extrair_nome(tipo_reu)
                    modo_reu = "ENTIDADE"
                elif tipo_reu_upper.startswith("AUTORIDADE COATORA ="):
                    nome_autoridade_reu = extrair_nome(tipo_reu)
                    modo_reu = "AUTORIDADE"
                elif tipo_reu_upper.strip() in ("NAO PRECISA", "", "NAN"):
                    modo_reu = "NENHUM"
                else:
                    modo_reu = "PESSOA"

                # --- TELA 1: DADOS INICIAIS ---
                sel_area = Select(wait.until(EC.presence_of_element_located((By.ID, "selIdGrupoCompetencia"))))
                sel_area.select_by_index(id_area)
                time.sleep(3)
                wait.until(lambda d: len(Select(d.find_element(By.ID, "selIdClasseJudicial")).options) > 1)
                Select(driver.find_element(By.ID, "selIdClasseJudicial")).select_by_index(id_classe)

                # Marca "Não se aplica" no valor da causa se aparecer
                time.sleep(1.5)
                try:
                    chk = driver.find_elements(By.ID, "chkNaoAplicaValor")
                    if chk and chk[0].is_displayed() and not chk[0].is_selected():
                        driver.execute_script("arguments[0].click();", chk[0])
                        time.sleep(0.5)
                except: pass

                if tem_originario:
                    campo_orig = wait.until(EC.presence_of_element_located((By.ID, "txtProcessoOriginario")))
                    campo_orig.clear()
                    campo_orig.send_keys(proc_orig)
                    time.sleep(1)
                    try:
                        chk = driver.find_elements(By.ID, "chkNaoAplicaValor")
                        if chk and not chk[0].is_selected():
                            driver.execute_script("arguments[0].click();", chk[0])
                    except: pass
                    try:
                        campo_juizo_orig = wait.until(EC.presence_of_element_located((By.ID, "txtDescJuizo")))
                        actions.double_click(campo_juizo_orig).perform()
                        time.sleep(1.5)
                    except: pass

                clicar_seguro(driver, wait, '//*[@id="btnSalvar"]')

                # --- TELA DE IMPORTAÇÃO (APENAS SE TIVER ORIGINÁRIO) ---
                if tem_originario:
                    for polo in ["Autor", "Reu"]:
                        try:
                            time.sleep(2)
                            checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox'][name^='chkInfraItem']")
                            if checkboxes:
                                if not checkboxes[0].is_selected():
                                    driver.execute_script("arguments[0].click();", checkboxes[0])
                                clicar_seguro(driver, wait, f'//*[@name="sbmProcessoEtapa{1 if polo == "Autor" else 2}"]')
                        except: break

                # --- TELA DE ASSUNTO ---
                status.config(text=f"L{num_fila}: Selecionando Assunto ({assunto})...")
                time.sleep(2)
                campo_assunto = wait.until(EC.element_to_be_clickable((By.ID, "txtFiltroPesquisa")))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", campo_assunto)
                time.sleep(0.5)
                campo_assunto.clear()
                campo_assunto.click()
                campo_assunto.send_keys(assunto)
                time.sleep(1)
                # Clica em Filtrar
                btn_filtrar = wait.until(EC.element_to_be_clickable((By.ID, "btnFiltrar")))
                driver.execute_script("arguments[0].click();", btn_filtrar)
                time.sleep(2)
                # Clica no assunto que apareceu na arvore
                clicar_seguro(driver, wait, f'//*[@id="{assunto}_anchor"]/span/span')
                time.sleep(1)
                # Inclui e avanca
                clicar_seguro(driver, wait, '//*[@id="btnIncluirAssunto"]')
                clicar_seguro(driver, wait, '//*[@id="sbmProcessoEtapa2"]')

                # --- TELAS DE PARTES ---
                for polo_idx, polo_nome in enumerate(["Autor", "Reu"]):
                    time.sleep(3)

                    if tem_originario and polo_idx == 0 and modo_autor == "PESSOA":
                        # Autor importado do originário: verifica se precisa adicionar principal
                        status.config(text=f"L{num_fila}: Verificando Autor principal...")
                        try:
                            principais = driver.find_elements(By.XPATH, "//table//td[contains(text(),'Sim')]")
                            if not principais:
                                status.config(text=f"L{num_fila}: Incluindo Autor principal (CPF)...")
                                input_cpf = wait.until(EC.presence_of_element_located((By.ID, "txtCpfCnpj")))
                                input_cpf.clear()
                                input_cpf.send_keys(cpf_autor)
                                clicar_seguro(driver, wait, '//*[@id="btnConsultarNome"]')
                                time.sleep(1.5)
                                clicar_seguro(driver, wait, '//*[@id="btnIncluir"]')
                                time.sleep(1.5)
                        except: pass
                        proxima(driver)

                    elif tem_originario and polo_idx == 1 and modo_reu == "PESSOA":
                        # Réu importado do originário: só avança
                        status.config(text=f"L{num_fila}: Avancando Reu importado...")
                        proxima(driver)

                    elif polo_idx == 0 and modo_autor == "ENTIDADE":
                        # Autor = Entidade (só se campo estiver visível)
                        if campo_visivel(driver, "selTipoPessoa"):
                            status.config(text=f"L{num_fila}: Preenchendo Autor Entidade...")
                            Select(wait.until(EC.presence_of_element_located((By.ID, "selTipoPessoa")))).select_by_value("ENT")
                            time.sleep(1)
                            incluir_autocomplete(driver, wait, actions,
                                "txtEntidade", "divInfraAjaxtxtEntidade",
                                nome_entidade_autor, '//*[@id="btnIncluirEnt"]')
                        else:
                            status.config(text=f"L{num_fila}: Sem campo Autor, avancando...")
                        proxima(driver)

                    elif polo_idx == 0 and modo_autor == "AUTORIDADE":
                        # Autor = Autoridade Coatora (só se campo estiver visível)
                        if campo_visivel(driver, "selTipoPessoa"):
                            status.config(text=f"L{num_fila}: Preenchendo Autor Autoridade Coatora...")
                            Select(wait.until(EC.presence_of_element_located((By.ID, "selTipoPessoa")))).select_by_value("AUT")
                            time.sleep(1)
                            incluir_autocomplete(driver, wait, actions,
                                "txtDesAutoridade", "divInfraAjaxtxtDesAutoridade",
                                nome_autoridade_autor, '//*[@id="btnIncluirAut"]')
                        else:
                            status.config(text=f"L{num_fila}: Sem campo Autor, avancando...")
                        proxima(driver)

                    elif polo_idx == 1 and modo_reu == "JUIZO":
                        # Réu = Juízo (só se campo estiver visível)
                        if campo_visivel(driver, "txtJuizoFederal"):
                            status.config(text=f"L{num_fila}: Preenchendo Suscitado (Juizo)...")
                            incluir_autocomplete(driver, wait, actions,
                                "txtJuizoFederal", "divInfraAjaxtxtJuizoFederal",
                                nome_juizo, '//*[@id="btnIncluirJui"]')
                        else:
                            status.config(text=f"L{num_fila}: Sem campo Juizo, avancando...")
                        proxima(driver)

                    elif polo_idx == 1 and modo_reu == "ENTIDADE":
                        # Réu = Entidade (só se campo estiver visível)
                        if campo_visivel(driver, "selTipoPessoa"):
                            status.config(text=f"L{num_fila}: Preenchendo Reu Entidade...")
                            Select(wait.until(EC.presence_of_element_located((By.ID, "selTipoPessoa")))).select_by_value("ENT")
                            time.sleep(1)
                            incluir_autocomplete(driver, wait, actions,
                                "txtEntidade", "divInfraAjaxtxtEntidade",
                                nome_entidade_reu, '//*[@id="btnIncluirEnt"]')
                        else:
                            status.config(text=f"L{num_fila}: Sem campo Reu, avancando...")
                        proxima(driver)

                    elif polo_idx == 1 and modo_reu == "AUTORIDADE":
                        # Réu = Autoridade Coatora (só se campo estiver visível)
                        if campo_visivel(driver, "selTipoPessoa"):
                            status.config(text=f"L{num_fila}: Preenchendo Reu Autoridade Coatora...")
                            Select(wait.until(EC.presence_of_element_located((By.ID, "selTipoPessoa")))).select_by_value("AUT")
                            time.sleep(1)
                            incluir_autocomplete(driver, wait, actions,
                                "txtDesAutoridade", "divInfraAjaxtxtDesAutoridade",
                                nome_autoridade_reu, '//*[@id="btnIncluirAut"]')
                        else:
                            status.config(text=f"L{num_fila}: Sem campo Reu, avancando...")
                        proxima(driver)

                    elif polo_idx == 1 and modo_reu == "NENHUM":
                        # Sem réu: só avança
                        status.config(text=f"L{num_fila}: Sem Reu, avancando...")
                        proxima(driver)

                    else:
                        # Pessoa física por CPF da planilha (só se campo estiver visível)
                        if campo_visivel(driver, "txtCpfCnpj"):
                            status.config(text=f"L{num_fila}: Preenchendo {polo_nome} (CPF)...")
                            input_cpf = wait.until(EC.presence_of_element_located((By.ID, "txtCpfCnpj")))
                            cpf_manual = cpf_autor if polo_idx == 0 else cpf_reu
                            input_cpf.clear()
                            input_cpf.send_keys(cpf_manual)
                            clicar_seguro(driver, wait, '//*[@id="btnConsultarNome"]')
                            time.sleep(1.5)
                            clicar_seguro(driver, wait, '//*[@id="btnIncluir"]')
                            time.sleep(1.5)
                        else:
                            status.config(text=f"L{num_fila}: Sem campo CPF, avancando...")
                        proxima(driver)

                # --- DOCUMENTOS E FINALIZAÇÃO ---
                status.config(text=f"L{num_fila}: Enviando PDF ({tipo_doc})...")
                upload = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='file']")))
                upload.send_keys(CAMINHO_PDF)
                campo_doc = wait.until(EC.presence_of_element_located((By.ID, "txtTipo_1")))
                driver.execute_script("arguments[0].click();", campo_doc)
                campo_doc.clear()
                driver.execute_script("arguments[0].value = '';", campo_doc)
                campo_doc.send_keys(tipo_doc)
                time.sleep(2)
                # CINPROT: clica na segunda opcao; Advogado: clica na primeira
                try:
                    opcoes = driver.find_elements(By.XPATH, "//ul[contains(@id,'autocomplete')]//li | //div[contains(@id,'autocomplete')]//li")
                    idx_opcao = 1 if perfil_cinprot and len(opcoes) > 1 else 0
                    driver.execute_script("arguments[0].click();", opcoes[idx_opcao])
                except:
                    campo_doc.send_keys(Keys.ARROW_DOWN, Keys.ENTER)
                time.sleep(1)
                clicar_seguro(driver, wait, '//*[@id="btnEnviarArquivos"]')

                clicar_seguro(driver, wait, '//*[@id="btnSalvar"]')
                driver.switch_to.default_content()
                iframe = wait.until(EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src,'confirmacao')]")))
                driver.switch_to.frame(iframe)
                clicar_seguro(driver, wait, '//*[@id="sbmConfirmar"]')
                time.sleep(6)
                driver.switch_to.default_content()

                capturar_dados_finais(driver, wait)
                clicar_seguro(driver, wait, '//*[@id="btnNovaPeticao"]')
                time.sleep(2)

        status.config(text="Status: Lote concluído!")
        messagebox.showinfo("AURA", "Processamento finalizado!")

    except Exception as e:
        status.config(text="Erro.")
        messagebox.showerror("Erro AURA", str(e))

# ===============================
# INTERFACE
# ===============================
def selecionar_pdf():
    global CAMINHO_PDF
    arquivo = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
    if arquivo:
        CAMINHO_PDF = arquivo
        label_pdf.config(text=f"PDF: {os.path.basename(arquivo)}", fg="#10b981")

def selecionar_planilha():
    global CAMINHO_PLANILHA
    arquivo = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
    if arquivo:
        CAMINHO_PLANILHA = arquivo
        label_csv.config(text=f"CSV: {os.path.basename(arquivo)}", fg="#10b981")

def abrir_consulta():
    janela_filtro = tk.Toplevel(janela)
    janela_filtro.title("Consultar Histórico")
    janela_filtro.geometry("700x450")
    janela_filtro.configure(bg="#1f2933")
    colunas = ("Data", "Classe", "Magistrado", "Processo")
    tree = ttk.Treeview(janela_filtro, columns=colunas, show='headings')
    for col in colunas: tree.heading(col, text=col)
    tree.pack(expand=True, fill='both', padx=10, pady=10)
    if os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tree.insert("", tk.END, values=(row['Data'], row['Classe'], row['Magistrado'], row['Processo']))

def iniciar():
    threading.Thread(target=executar_peticionamento_lote, args=(status_label,), daemon=True).start()

def iniciar_cinprot():
    threading.Thread(target=executar_peticionamento_lote, args=(status_label, True), daemon=True).start()

def salvar_login():
    global USUARIO, SENHA, URL
    USUARIO = entry_usuario.get().strip()
    SENHA = entry_senha.get().strip()
    URL = entry_url.get().strip()
    if USUARIO and SENHA and URL:
        frame_login.pack_forget()
        frame_principal.pack(fill='both', expand=True)
    else:
        messagebox.showerror("AURA", "Informe usuário, senha e URL.")

janela = tk.Tk()
janela.title("AURA – Automação eProc")
janela.geometry("560x720")
janela.configure(bg="#1f2933")

# --- TELA DE LOGIN ---
frame_login = tk.Frame(janela, bg="#1f2933")
frame_login.pack(fill='both', expand=True)

tk.Label(frame_login, text="AURA", font=("Segoe UI", 28, "bold"), bg="#1f2933", fg="white").pack(pady=(40, 5))
tk.Label(frame_login, text="Sistema de Peticionamento Automatizado", font=("Segoe UI", 10), bg="#1f2933", fg="#9ca3af").pack(pady=(0, 30))

tk.Label(frame_login, text="Usuário eProc", font=("Segoe UI", 10), bg="#1f2933", fg="#9ca3af").pack()
entry_usuario = tk.Entry(frame_login, font=("Segoe UI", 11), width=28, bg="#374151", fg="white", insertbackground="white", relief="flat")
entry_usuario.pack(pady=5, ipady=6)

tk.Label(frame_login, text="Senha", font=("Segoe UI", 10), bg="#1f2933", fg="#9ca3af").pack(pady=(10, 0))
entry_senha = tk.Entry(frame_login, font=("Segoe UI", 11), width=28, bg="#374151", fg="white", insertbackground="white", relief="flat", show="*")
entry_senha.pack(pady=5, ipady=6)

tk.Label(frame_login, text="URL do Sistema", font=("Segoe UI", 10), bg="#1f2933", fg="#9ca3af").pack(pady=(10, 0))
entry_url = tk.Entry(frame_login, font=("Segoe UI", 11), width=28, bg="#374151", fg="white", insertbackground="white", relief="flat")
entry_url.insert(0, "https://eproc2g-hml.tjmg.jus.br/eproc/")
entry_url.pack(pady=5, ipady=6)

tk.Button(frame_login, text="ENTRAR", font=("Segoe UI", 12, "bold"), bg="#2563eb", fg="white", width=20, relief="flat", command=salvar_login).pack(pady=30)

# --- TELA PRINCIPAL ---
frame_principal = tk.Frame(janela, bg="#1f2933")

tk.Label(frame_principal, text="AURA - Sistema de Lote", font=("Segoe UI", 16, "bold"), bg="#1f2933", fg="white").pack(pady=25)
tk.Button(frame_principal, text="1. Selecionar Planilha (CSV)", bg="#6366f1", fg="white", width=32, command=selecionar_planilha).pack(pady=5)
label_csv = tk.Label(frame_principal, text="Nenhum arquivo CSV", bg="#1f2933", fg="#9ca3af")
label_csv.pack()
tk.Button(frame_principal, text="2. Selecionar PDF", bg="#6366f1", fg="white", width=32, command=selecionar_pdf).pack(pady=5)
label_pdf = tk.Label(frame_principal, text="Nenhum arquivo PDF", bg="#1f2933", fg="#9ca3af")
label_pdf.pack()
tk.Button(frame_principal, text="HOMOLOGAR ADVOGADO", font=("Segoe UI", 12, "bold"), bg="#2563eb", fg="white", width=32, command=iniciar).pack(pady=(30, 8))
tk.Button(frame_principal, text="HOMOLOGAR CINPROT", font=("Segoe UI", 12, "bold"), bg="#7C3AED", fg="white", width=32, command=iniciar_cinprot).pack(pady=(0, 20))
tk.Button(frame_principal, text="Consultar Histórico", bg="#10b981", fg="white", width=32, command=abrir_consulta).pack()
status_label = tk.Label(frame_principal, text="Aguardando...", bg="#1f2933", fg="yellow")
status_label.pack(pady=20)

janela.mainloop()
"""
Script de Compilação Automatizada do Productivity Assistant.
Gera um executável (.exe) independente (standalone) com proteção de código-fonte,
suporte a console de terminal para logs, versionamento dinâmico (metadados Windows),
ícone customizado inspirado no Git e empacotamento automático para distribuição (.zip).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Configurar saída do console para UTF-8 compatível com Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def obter_versao_atual(diretorio_base: Path) -> str:
    """Lê a versão atual definida em app/__init__.py."""
    init_file = diretorio_base / "app" / "__init__.py"
    if init_file.exists():
        conteudo = init_file.read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', conteudo)
        if match:
            return match.group(1)
    return "1.0.0"


def atualizar_versao_projeto(diretorio_base: Path, nova_versao: str) -> None:
    """Atualiza a versão em app/__init__.py."""
    init_file = diretorio_base / "app" / "__init__.py"
    if init_file.exists():
        conteudo = init_file.read_text(encoding="utf-8")
        novo_conteudo = re.sub(
            r'__version__\s*=\s*["\'][^"\']+["\']',
            f'__version__ = "{nova_versao}"',
            conteudo,
        )
        init_file.write_text(novo_conteudo, encoding="utf-8")
        print(f"[+] Versão atualizada em app/__init__.py -> {nova_versao}")


def converter_versao_para_tupla(versao_str: str) -> tuple:
    """Converte '1.2.3' para uma tupla de 4 inteiros (1, 2, 3, 0) exigida pelo Windows."""
    numeros = [int(p) for p in re.findall(r"\d+", versao_str)]
    while len(numeros) < 4:
        numeros.append(0)
    return tuple(numeros[:4])


def gerar_arquivo_version_info(versao_str: str, destino_txt: Path) -> None:
    """Gera o arquivo de metadados de versão do Windows (VSVersionInfo) para o PyInstaller."""
    tupla_versao = converter_versao_para_tupla(versao_str)
    tupla_str = str(tupla_versao)

    conteudo = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tupla_str},
    prodvers={tupla_str},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '041604b0',
          [
            StringStruct('CompanyName', 'Tribunal de Justica do Ceara'),
            StringStruct('FileDescription', 'Productivity Assistant - Gerador de IC e Gestao'),
            StringStruct('FileVersion', '{versao_str}.0'),
            StringStruct('InternalName', 'ProductivityAssistant'),
            StringStruct('LegalCopyright', 'Copyright (C) 2026'),
            StringStruct('OriginalFilename', 'ProductivityAssistant.exe'),
            StringStruct('ProductName', 'Productivity Assistant'),
            StringStruct('ProductVersion', '{versao_str}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
"""
    destino_txt.write_text(conteudo, encoding="utf-8")


def limpar_diretorio_distribuicao(caminho_dist: Path, caminho_build: Path) -> None:
    """Remove artefatos de compilações anteriores para garantir um build limpo."""
    if caminho_dist.exists():
        print(f"[-] Removendo diretório dist anterior: {caminho_dist}")
        shutil.rmtree(caminho_dist, ignore_errors=True)
    if caminho_build.exists():
        print(f"[-] Removendo diretório build anterior: {caminho_build}")
        shutil.rmtree(caminho_build, ignore_errors=True)


def executar_compilacao_pyinstaller(
    diretorio_base: Path,
    caminho_dist: Path,
    versao: str,
    arquivo_version_info: Path,
    caminho_icone: Path,
) -> bool:
    """Executa a compilação utilizando PyInstaller com console, versão e ícone."""
    interpretador_python = sys.executable

    comando_compilacao = [
        interpretador_python,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        "--name",
        "ProductivityAssistant",
        "--add-data",
        "app/dashboard/templates;app/dashboard/templates",
        "--add-data",
        "app/dashboard/static;app/dashboard/static",
        "--collect-all",
        "uvicorn",
        "--collect-all",
        "psycopg2",
        "--hidden-import",
        "sqlalchemy.dialects.postgresql",
    ]

    # Adicionar ícone customizado se existir
    if caminho_icone.exists():
        comando_compilacao.extend(["--icon", str(caminho_icone)])
        comando_compilacao.extend(["--add-data", f"{caminho_icone.parent};assets"])
        print(f"[+] Ícone configurado: {caminho_icone}")

    # Adicionar metadados de versão do Windows
    if arquivo_version_info.exists():
        comando_compilacao.extend(["--version-file", str(arquivo_version_info)])
        print(f"[+] Metadados de versão do Windows configurados: v{versao}")

    comando_compilacao.append("main.py")

    print("\n[+] Iniciando compilação do executável com PyInstaller...")
    print(f"[+] Comando: {' '.join(comando_compilacao)}\n")

    processo = subprocess.run(comando_compilacao, cwd=str(diretorio_base))
    return processo.returncode == 0


def copiar_arquivos_auxiliares(diretorio_base: Path, pasta_executavel: Path, versao: str) -> None:
    """Copia o arquivo .env.exemplo e cria instruções de uso com a versão."""
    origem_env = diretorio_base / ".env.exemplo"
    if origem_env.exists():
        destino_env = pasta_executavel / ".env.exemplo"
        shutil.copy2(origem_env, destino_env)
        print(f"[+] Arquivo de configuração de exemplo copiado para: {destino_env}")

    # Criar LEIA-ME com instruções claras da release
    leia_me = pasta_executavel / "LEIA-ME.txt"
    agora_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    texto_instrucoes = f"""================================================================================
PRODUCTIVITY ASSISTANT - v{versao}
Data de Compilação: {agora_str}
================================================================================

COMO USAR ESTE APLICATIVO:
1. Certifique-se de que o PostgreSQL está em execução na sua máquina.
2. Na pasta deste aplicativo, crie uma cópia do arquivo '.env.exemplo' e renomeie para '.env'.
3. Abra o arquivo '.env' e configure suas credenciais:
   - REDMINE_URL, REDMINE_API_KEY
   - DB_NAME, DB_USER, DB_PASSWORD
   - GIT_REPO_PATH (caminho local do repositório Git que deseja analisar)
4. Execute o arquivo 'ProductivityAssistant.exe'.
5. O terminal abrirá mostrando os logs em tempo real e seu navegador abrirá
   automaticamente no endereço: http://127.0.0.1:8000

Dúvidas ou sugestões: Contate a equipe do projeto.
================================================================================
"""
    leia_me.write_text(texto_instrucoes, encoding="utf-8")
    print(f"[+] Arquivo LEIA-ME.txt gerado com sucesso em: {leia_me}")


def gerar_pacote_zip(pasta_origem: Path, caminho_dist: Path, versao: str) -> Path:
    """Compacta a pasta da release em um arquivo ZIP pronto para distribuição."""
    nome_zip = f"ProductivityAssistant_v{versao}"
    caminho_base_zip = caminho_dist / nome_zip
    print(f"\n[+] Compactando distribuição em {nome_zip}.zip...")
    arquivo_zip = shutil.make_archive(
        base_name=str(caminho_base_zip),
        format="zip",
        root_dir=str(pasta_origem.parent),
        base_dir=pasta_origem.name,
    )
    return Path(arquivo_zip)


def iniciar_processo_compilacao() -> None:
    """Orquestra o fluxo completo de geração e versionamento do executável."""
    diretorio_base = Path(__file__).resolve().parent
    versao_atual = obter_versao_atual(diretorio_base)

    parser = argparse.ArgumentParser(description="Compilador do Productivity Assistant")
    parser.add_argument(
        "-v",
        "--versao",
        type=str,
        default=None,
        help=f"Versão a compilar (padrão atual: {versao_atual})",
    )
    parser.add_argument(
        "--zip",
        dest="gerar_zip",
        action="store_true",
        default=True,
        help="Gerar pacote .zip versionado para compartilhamento (padrão: True)",
    )
    parser.add_argument(
        "--sem-zip",
        dest="gerar_zip",
        action="store_false",
        help="Não gerar o pacote .zip",
    )

    args = parser.parse_args()

    versao_escolhida = args.versao
    if not versao_escolhida:
        # Se executado interativamente no terminal, permitir input
        if sys.stdin.isatty():
            try:
                entrada = input(f"Informe a versão do executável [padrão: {versao_atual}]: ").strip()
                versao_escolhida = entrada if entrada else versao_atual
            except EOFError:
                versao_escolhida = versao_atual
        else:
            versao_escolhida = versao_atual

    # Limpar qualquer 'v' inicial se o usuário digitar 'v1.1.0'
    versao_limpa = versao_escolhida.lstrip("vV").strip()
    if not versao_limpa:
        versao_limpa = versao_atual

    # Atualizar versão no código do projeto
    atualizar_versao_projeto(diretorio_base, versao_limpa)

    caminho_dist = diretorio_base / "dist"
    caminho_build = diretorio_base / "build"
    caminho_icone = diretorio_base / "assets" / "icon.ico"

    print("=" * 75)
    print(f"   Compilador do Productivity Assistant (Windows .exe) - Versão v{versao_limpa}")
    print("=" * 75)

    limpar_diretorio_distribuicao(caminho_dist, caminho_build)

    # Gerar arquivo temporário com metadados de versão do Windows
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix="_version.txt") as temp_v:
        caminho_version_txt = Path(temp_v.name)

    try:
        gerar_arquivo_version_info(versao_limpa, caminho_version_txt)

        sucesso = executar_compilacao_pyinstaller(
            diretorio_base=diretorio_base,
            caminho_dist=caminho_dist,
            versao=versao_limpa,
            arquivo_version_info=caminho_version_txt,
            caminho_icone=caminho_icone,
        )
    finally:
        caminho_version_txt.unlink(missing_ok=True)

    if sucesso:
        pasta_gerada = caminho_dist / "ProductivityAssistant"
        copiar_arquivos_auxiliares(diretorio_base, pasta_gerada, versao_limpa)

        arquivo_zip = None
        if args.gerar_zip:
            arquivo_zip = gerar_pacote_zip(pasta_gerada, caminho_dist, versao_limpa)

        print("\n" + "=" * 75)
        print("[SUCESSO] COMPILACAO CONCLUIDA COM SUCESSO!")
        print(f"[+] Versao do executavel: v{versao_limpa}")
        print(f"[+] Icone embutido: {caminho_icone}")
        print(f"[+] Pasta do executavel: {pasta_gerada}")
        print(f"[+] Arquivo principal: {pasta_gerada / 'ProductivityAssistant.exe'}")
        if arquivo_zip:
            print(f"[+] Pacote ZIP para compartilhamento: {arquivo_zip}")

        print("\n[+] Instrucoes para envio ao seu time:")
        if arquivo_zip:
            print(f"    1. Envie o arquivo '{arquivo_zip.name}' para seus colegas de equipe;")
        else:
            print("    1. Compacte a pasta 'ProductivityAssistant' em um arquivo .zip e envie;")
        print("    2. O colega descompacta, renomeia '.env.exemplo' para '.env', preenche os dados e executa;")
        print("    3. O executavel abre com icone proprio do Git/IC, terminal de logs e o navegador em http://127.0.0.1:8000 automaticamente!")
        print("=" * 75)
    else:
        print("\n" + "=" * 75)
        print("[FALHA] FALHA NA COMPILACAO DO EXECUTAVEL.")
        print("Verifique os logs acima para detalhes do erro.")
        print("=" * 75)
        sys.exit(1)


if __name__ == "__main__":
    iniciar_processo_compilacao()

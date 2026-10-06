"""
Script de Compilação Automatizada do Productivity Assistant.
Gera um executável (.exe) independente (standalone) com proteção de código-fonte
e suporte a console de terminal para acompanhamento de logs em tempo real.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def limpar_diretorio_distribuicao(caminho_dist: Path, caminho_build: Path) -> None:
    """Remove artefatos de compilações anteriores para garantir um build limpo."""
    if caminho_dist.exists():
        print(f"[-] Removendo diretório dist anterior: {caminho_dist}")
        shutil.rmtree(caminho_dist, ignore_errors=True)
    if caminho_build.exists():
        print(f"[-] Removendo diretório build anterior: {caminho_build}")
        shutil.rmtree(caminho_build, ignore_errors=True)


def executar_compilacao_pyinstaller(diretorio_base: Path, caminho_dist: Path) -> bool:
    """Executa a compilação utilizando PyInstaller com terminal de console habilitado."""
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
        "main.py",
    ]

    print("\n[+] Iniciando compilação do executável com PyInstaller...")
    print(f"[+] Comando: {' '.join(comando_compilacao)}\n")

    processo = subprocess.run(comando_compilacao, cwd=str(diretorio_base))
    return processo.returncode == 0


def copiar_arquivos_auxiliares(diretorio_base: Path, pasta_executavel: Path) -> None:
    """Copia o arquivo .env.exemplo e eventuais instruções para a pasta do executável."""
    origem_env = diretorio_base / ".env.exemplo"
    if origem_env.exists():
        destino_env = pasta_executavel / ".env.exemplo"
        shutil.copy2(origem_env, destino_env)
        print(f"[+] Arquivo de configuração de exemplo copiado para: {destino_env}")


def iniciar_processo_compilacao() -> None:
    """Orquestra o fluxo completo de geração do executável."""
    diretorio_base = Path(__file__).resolve().parent
    caminho_dist = diretorio_base / "dist"
    caminho_build = diretorio_base / "build"

    print("=" * 70)
    print("   Compilador do Productivity Assistant (Standalone Windows .exe)")
    print("=" * 70)

    limpar_diretorio_distribuicao(caminho_dist, caminho_build)

    sucesso = executar_compilacao_pyinstaller(diretorio_base, caminho_dist)

    if sucesso:
        pasta_gerada = caminho_dist / "ProductivityAssistant"
        copiar_arquivos_auxiliares(diretorio_base, pasta_gerada)

        print("\n" + "=" * 70)
        print("[SUCESSO] COMPILACAO CONCLUIDA COM SUCESSO!")
        print(f"[+] Localizacao do executavel: {pasta_gerada / 'ProductivityAssistant.exe'}")
        print("[+] Instruções para envio ao seu time:")
        print("    1. Compacte a pasta 'ProductivityAssistant' em um arquivo .zip;")
        print("    2. Envie o .zip para os colegas;")
        print("    3. O colega descompacta, renomeia '.env.exemplo' para '.env', preenche os dados e executa!")
        print("    4. O terminal abre com logs em tempo real e o navegador abre em http://127.0.0.1:8000 automaticamente!")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("❌ FALHA NA COMPILAÇÃO DO EXECUTÁVEL.")
        print("Verifique os logs acima para detalhes do erro.")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    iniciar_processo_compilacao()

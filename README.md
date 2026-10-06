# Productivity Assistant 🚀

Sistema inteligente de levantamento automatizado de atividades e geração de **Itens de Catálogo (IC)** no **Redmine**, reduzindo o trabalho manual do desenvolvedor.

---

## 📋 Sumário
- [Visão Geral](#-visão-geral)
- [Arquitetura](#-arquitetura)
- [Entregáveis da Fase 1](#-entregáveis-da-fase-1)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Pré-requisitos](#-pré-requisitos)
- [Como Executar](#-como-executar)
- [Demonstração do Fluxo](#-demonstração-do-fluxo)
- [Testes Automatizados](#-testes-automatizados)
- [Próximas Fases](#-próximas-fases)

---

## 🎯 Visão Geral

O **Productivity Assistant** analisa commits do Git e (futuramente) reuniões corporativas no Microsoft Teams para:
1. Agrupar atividades correlatas automaticamente.
2. Gerar sugestões de títulos e descrições técnicas de Itens de Catálogo (IC).
3. Permitir aprovação e edição em um dashboard web moderno.
4. Criar automaticamente os ICs no Redmine corporativo via Selenium com evidências visuais (screenshots).
5. Gerar relatórios analíticos em PDF e Excel.
6. Manter todo o histórico persistido em banco de dados relacional PostgreSQL.

---

## 🏗 Arquitetura

- **Linguagem:** Python 3.12+
- **Backend:** FastAPI (Starlette, Uvicorn)
- **Frontend:** Jinja2 + Bootstrap 5.3 + Bootstrap Icons
- **Estilização:** CSS moderno com design Dark Mode e Glassmorphism
- **Banco de Dados:** PostgreSQL 17
- **ORM & Migrações:** SQLAlchemy 2.0 & Alembic
- **Integração Git:** GitPython
- **Relatórios:** OpenPyXL (Excel) e ReportLab (PDF)
- **Logs:** Loguru (saída no console e em `logs/app.log`)
- **Configurações:** Pydantic Settings & python-dotenv
- **Automação Redmine:** Selenium WebDriver + ChromeDriver *(preparado para Fase 3)*

---

## ✅ Entregáveis da Fase 1

Na Fase 1 foram implementados e validados:
- [x] Estrutura completa de diretórios e pacotes do projeto.
- [x] Conexão e integração completa com o PostgreSQL local (`database: productivity_assistant`).
- [x] Modelos ORM mapeados para todas as tabelas (`commits`, `meetings`, `catalog_items`, `evidences`, `execution_history`).
- [x] Migração inicial do Alembic configurada e versionada (`alembic/versions`).
- [x] Backend FastAPI com ciclo de vida, documentação e rotas Jinja2.
- [x] Dashboard moderno com KPIs, seleção de período e filtros rápidos (*Hoje*, *Ontem*, *Esta Semana*, *Este Mês*, *Personalizado*).
- [x] Integração GitPython (`GitService`) com busca por período, autor e múltiplos branches.
- [x] Persistência dos commits no PostgreSQL com detecção de duplicidades.
- [x] Tela detalhada de visualização de commits com filtros por repositório, período e busca textual.
- [x] Modal interativo para visualização dos arquivos alterados em cada commit.
- [x] Histórico de execuções com detalhamento de execuções anteriores.
- [x] Geração e download de relatórios em Excel (`.xlsx`) e PDF (`.pdf`).
- [x] Logging completo e rotativo em `logs/app.log`.
- [x] Suíte de testes automatizados com `pytest` (12 testes passando).

---

## 📂 Estrutura do Projeto

```
productivity_assistant/
│
├── alembic/                      # Configurações e versões de migração Alembic
│   ├── versions/
│   │   └── 0aed0f040dc5_initial_schema.py
│   └── env.py
│
├── app/
│   ├── core/                     # Configurações globais, banco e logs
│   │   ├── config.py             # Pydantic Settings e variáveis de ambiente
│   │   ├── database.py           # Engine SQLAlchemy, sessões e init_db
│   │   ├── logger.py             # Configuração do Loguru (console e arquivo)
│   │   └── selectors.py          # Seletores centralizados para Selenium
│   │
│   ├── models/                   # Modelos relacionais SQLAlchemy
│   │   ├── commit.py             # Tabela commits
│   │   ├── meeting.py            # Tabela meetings
│   │   ├── catalog_item.py       # Tabela catalog_items
│   │   ├── evidence.py           # Tabela evidences
│   │   └── execution_history.py  # Tabela execution_history
│   │
│   ├── services/                 # Regras de negócio e integrações
│   │   ├── git_service.py        # Leitura GitPython e persistência
│   │   ├── meeting_service.py    # Gestão de reuniões (Teams ready)
│   │   ├── catalog_generator_service.py # Agrupamento e sugestões de IC
│   │   ├── redmine_service.py    # Integração oficial REST com Redmine
│   │   └── report_service.py     # Exportação Excel e PDF
│   │
│   └── dashboard/                # Camada web FastAPI
│       ├── routes.py             # Rotas de interface e ações
│       ├── templates/            # Telas Jinja2 Bootstrap 5
│       │   ├── base.html
│       │   ├── index.html
│       │   ├── commits.html
│       │   ├── meetings.html
│       │   └── history.html
│       └── static/               # Assets estáticos
│           ├── css/custom.css    # Estilização Glassmorphism Dark
│           └── js/main.js        # Utilitários de filtros e modais
│
├── reports/                      # Relatórios gerados em PDF e Excel
├── logs/                         # Arquivos de log (app.log)
├── tests/                        # Testes automatizados (pytest)
│   ├── test_app.py
│   └── test_git_service.py
│
├── .env                          # Variáveis de ambiente locais
├── .env.exemplo                  # Template de configuração
├── .gitignore
├── alembic.ini                   # Configuração do Alembic
├── pytest.ini                    # Configuração de testes
├── requirements.txt              # Dependências do projeto
└── main.py                       # Ponto de entrada da aplicação
```

---

## ⚙️ Pré-requisitos

1. **Python 3.12+** instalado na máquina.
2. **PostgreSQL** em execução local (porta 5432).
3. **Git** configurado localmente.

---

## 🚀 Como Executar

### 1. Clonar ou Acessar a Pasta do Projeto
```powershell
cd D:\Projetos\gerador-ic
```

### 2. Ativar o Ambiente Virtual
```powershell
.venv\Scripts\Activate.ps1
```

### 3. Configurar o arquivo `.env`
Copie o arquivo de exemplo `.env.example` para `.env`:
```powershell
cp .env.example .env
```
Abra o `.env` e preencha as configurações da sua máquina:
```ini
# Caminho para o seu repositório local do PJE
DEFAULT_GIT_REPO_PATH=C:/ambiente/Git/PJE
# Seu nome de autor no Git (ex: seu.nome ou nome no git config user.name)
GIT_AUTHOR_NAME=seu.nome

# Sua Chave de Acesso à API do Redmine (obtida em: https://redmine.tjce.jus.br/my/account)
REDMINE_URL=https://redmine.tjce.jus.br
REDMINE_API_KEY=sua_chave_de_acesso_api_aqui
```

### 4. Iniciar o Sistema
```powershell
python main.py
```
Ou via Uvicorn diretamente:
```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 5. Acessar no Navegador
Abra: [http://localhost:8000](http://localhost:8000)

---

## 🧪 Testes Automatizados

Para executar toda a suíte de testes com validação do banco PostgreSQL e das rotas FastAPI:

```powershell
.venv\Scripts\pytest.exe -v
```

---

## 🗺️ Próximas Fases

- **Fase 2:** Integração com Microsoft Teams / Graph API para levantamento automático de reuniões no período e refinamento do algoritmo gerador de descrições de IC.
- **Fase 3:** Automação completa de login e cadastro no Redmine corporativo com Selenium WebDriver, captura de evidências passo a passo e registro de IDs gerados.

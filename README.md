# Lead Hunter - Automation Pipeline

`PT-BR`

Sistema em Python para busca, qualificacao e organizacao de leads com foco em restaurantes e operacoes locais. O projeto combina Google Maps, Instagram, Google Sheets, scoring e dashboard operacional em uma pipeline unica de prospeccao assistida.

`EN`

Python-based system for lead discovery, qualification, and operational organization focused on restaurants and local businesses. The project combines Google Maps, Instagram, Google Sheets, scoring, and an operational dashboard in a single assisted prospecting pipeline.

## Live Demo / Ver Demo

`PT-BR`

Dashboard tecnico publicado: [lead-hunter-alpha.vercel.app](https://lead-hunter-alpha.vercel.app/)

`EN`

Published technical dashboard: [lead-hunter-alpha.vercel.app](https://lead-hunter-alpha.vercel.app/)

## Positioning / Posicionamento

`PT-BR`

O `Lead Hunter` entra no portifolio como um case tecnico de automacao e engenharia aplicada. O foco aqui nao e venda agressiva, e sim mostrar arquitetura, fluxo operacional e capacidade de transformar coleta de dados em acao comercial organizada.

`EN`

`Lead Hunter` is positioned in the portfolio as a technical case in automation and applied engineering. The goal is not aggressive selling, but rather to demonstrate architecture, operational flow, and the ability to turn data collection into structured commercial action.

## What Is Public Here / O Que Esta Publico Aqui

`PT-BR`

- arquitetura principal da pipeline;
- dashboard publico de acompanhamento;
- fluxo de qualificacao;
- integracoes e requisitos tecnicos;
- repositorio sanitizado para avaliacao tecnica.

`EN`

- main pipeline architecture;
- public operational dashboard;
- qualification flow;
- integrations and technical requirements;
- sanitized repository for technical evaluation.

## Core Flow / Fluxo Principal

1. Busca estabelecimentos por cidade e categoria no Google Maps.
2. Analisa a presenca digital para identificar sinais de maturidade comercial.
3. Coleta sinais complementares do Instagram via Apify e fallback publico.
4. Calcula score de qualificacao com foco em conversao real.
5. Gera mensagens iniciais assistidas para abordagem manual.
6. Exporta leads priorizados para Google Sheets e arquivos locais.
7. Exibe acompanhamento e resultados em dashboard.

## Stack and Integrations / Stack e Integracoes

- Python 3.11+
- Google Places API
- Apify
- Gemini
- Google Sheets
- Gmail SMTP
- Dashboard publicado na Vercel

## Blueprint / Blueprint

- Technical blueprint: [BLUEPRINT-LITE.md](./BLUEPRINT-LITE.md)

## Structure / Estrutura

```text
lead_hunter/
├── config.py
├── maps_scraper.py
├── link_detector.py
├── instagram_scraper.py
├── scorer.py
├── message_writer.py
├── sheets_exporter.py
├── email_notifier.py
└── main.py
main.py
dashboard/
api/
SETUP_APIS.md
requirements.txt
```

## Local Setup / Como Rodar

1. Instale Python 3.11 ou superior.
2. Instale as dependencias:

```bash
pip install -r requirements.txt
```

3. Adicione os segredos localmente, sem versionar credenciais.
4. Compartilhe a planilha com o e-mail da service account.
5. Rode:

```bash
python main.py
```

## Sensitive Files / Arquivos Sensiveis

`PT-BR`

Credenciais, exports, logs e dados operacionais nao fazem parte da superficie publica do repositorio. Arquivos como `service_account.json`, `data/`, `logs/` e `exports/` permanecem locais.

`EN`

Credentials, exports, logs, and operational data are not part of the repository's public surface. Files such as `service_account.json`, `data/`, `logs/`, and `exports/` stay local.

## Operational Notes / Observacoes Operacionais

- a abordagem continua manual, sem disparo automatico de mensagens;
- o dashboard publico serve como vitrine tecnica da operacao;
- o sistema suporta retomada de execucao via checkpoint;
- mesmo quando Sheets ou e-mail falham, os arquivos locais continuam sendo gerados.

## License / Licenca

Este repositorio segue a licenca incluida neste projeto. O material esta publicado para avaliacao tecnica, referencia de arquitetura e demonstracao de fluxo.

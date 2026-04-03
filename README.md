# Lead Hunter B2B para Restaurantes

Sistema em Python para encontrar restaurantes com presença digital ativa, sem site profissional próprio, qualificar os melhores leads e gerar mensagens de primeiro contato para WhatsApp e Instagram DM.

O pipeline faz:

1. Busca restaurantes no Google Maps por cidade e categoria.
2. Analisa o link atual para separar quem depende de Linktree, WhatsApp, iFood ou site fraco.
3. Coleta dados do Instagram via Apify e, se necessário, por scraping público.
4. Calcula score de 0 a 100 com foco em conversão real.
5. Gera mensagem personalizada com Gemini.
6. Exporta HOTs e WARMs para Google Sheets.
7. Salva os leads localmente em CSV, JSON e HTML.
8. Envia um e-mail resumo com os melhores leads.

## Estrutura

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
setup_colab.ipynb
SETUP_APIS.md
requirements.txt
```

## Requisitos

- Python 3.11+
- Conta Google Cloud com Places API ativa
- Conta Apify gratuita
- Chave Gemini
- Planilha Google Sheets
- Conta Gmail com App Password
- Arquivo `service_account.json` do Google no diretório raiz do projeto

## Instalação local

1. Instale Python 3.11 ou superior.
2. Abra um terminal na pasta do projeto.
3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Coloque o arquivo `service_account.json` na raiz do projeto.
5. Abra [lead_hunter/config.py](/D:/Users/wesle/PROJETOS%20CODEX/AUTOMA%C3%87%C3%83O%20PARA%20BUSCAR%20LEAD/lead_hunter/config.py) e preencha:
   - `GOOGLE_MAPS_API_KEY`
   - `APIFY_TOKEN`
   - `GEMINI_API_KEY`
   - `GOOGLE_SHEETS_ID`
   - `NOTIFICATION_EMAIL`
   - `SMTP_EMAIL`
   - `SMTP_APP_PASSWORD`

6. Compartilhe a planilha com o e-mail da service account.
7. Rode:

```bash
python main.py
```

## Execução no Colab

Use [setup_colab.ipynb](/D:/Users/wesle/PROJETOS%20CODEX/AUTOMA%C3%87%C3%83O%20PARA%20BUSCAR%20LEAD/setup_colab.ipynb).

O notebook já vem com:

- instalação das libs
- configuração guiada
- teste das conexões
- execução do pipeline
- visualização rápida dos top 10 leads

## Arquivos gerados

- `data/checkpoint.json`: progresso da execução para retomar sem reprocessar
- `data/latest_qualified_leads.json`: snapshot dos leads qualificados
- `logs/lead_hunter.log`: log detalhado
- `exports/qualified_leads.csv`: leads prontos para abrir em Excel/Sheets
- `exports/qualified_leads.html`: visão rápida para revisão manual
- `exports/qualified_leads.json`: export bruto dos qualificados

## Como o score funciona

- `HOT`: 75+ pontos
- `WARM`: 60-74 pontos
- `COLD`: 40-59 pontos
- `SKIP`: abaixo de 40 ou desqualificado

Só `HOT` e `WARM` vão para a planilha.

## Observações importantes

- O projeto não envia mensagens automaticamente. A abordagem continua manual.
- O Google Places foi implementado com a API atual (`places.googleapis.com/v1`) para funcionar em projetos novos.
- O modelo padrão do Gemini está em `gemini-2.5-flash` para aumentar a chance de funcionar logo na primeira execução. O código ainda tenta fallback para `gemini-2.0-flash`.
- O limite de chamadas Apify por sessão está travado em 50 por padrão para economizar créditos.

## Rodar novamente sem perder progresso

Basta executar `python main.py` de novo. O sistema lê o checkpoint e pula `place_id` já processado.

## Solução de problemas rápida

- Sem resultados no Maps: confira a chave e se a Places API está habilitada.
- Erro no Sheets: confirme o `GOOGLE_SHEETS_ID`, o `service_account.json` e o compartilhamento da planilha.
- Erro no e-mail: valide `SMTP_EMAIL` e `SMTP_APP_PASSWORD`.
- Poucos dados do Instagram: o sistema cai para scraping público quando o Apify falha.
- Mesmo se Sheets ou e-mail falharem, os leads continuam sendo entregues em `exports/`.

# Setup das APIs e Credenciais

Este arquivo mostra exatamente onde pegar cada chave e como ligar tudo para o projeto funcionar na primeira execução.

## 1. Google Maps Places API

Usada para buscar restaurantes e puxar detalhes do negócio.

### Como criar

1. Acesse [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um projeto novo ou use um existente.
3. Vá em `APIs e serviços` -> `Biblioteca`.
4. Habilite `Places API`.
5. Vá em `APIs e serviços` -> `Credenciais`.
6. Clique em `Criar credenciais` -> `Chave de API`.
7. Restrinja a chave para `Places API` se quiser mais segurança.

### Onde colocar

Em [lead_hunter/config.py](/D:/Users/wesle/PROJETOS%20CODEX/AUTOMA%C3%87%C3%83O%20PARA%20BUSCAR%20LEAD/lead_hunter/config.py):

```python
GOOGLE_MAPS_API_KEY = "SUA_CHAVE_AQUI"
```

## 2. Apify

Usado para puxar dados ricos do Instagram com baixo custo.

### Como criar

1. Acesse [Apify](https://console.apify.com/).
2. Crie sua conta gratuita.
3. No painel, abra `Settings` -> `Integrations` ou `API & Integrations`.
4. Copie o token da API.

### Onde colocar

```python
APIFY_TOKEN = "SEU_TOKEN_AQUI"
```

## 3. Gemini API

Usado para escrever as mensagens personalizadas.

### Como criar

1. Acesse [Google AI Studio](https://aistudio.google.com/).
2. Faça login.
3. Clique em `Get API key`.
4. Gere a chave para o projeto desejado.

### Onde colocar

```python
GEMINI_API_KEY = "SUA_CHAVE_AQUI"
```

Observação:

- O projeto usa `gemini-2.5-flash` como padrão.
- Se esse modelo não estiver disponível na conta, o código tenta fallback automaticamente.

## 4. Google Sheets

Usado para salvar HOTs e WARMs em uma planilha pronta para operação.

### Como pegar o ID da planilha

Abra a planilha no navegador. O ID é o trecho entre `/d/` e `/edit`.

Exemplo:

```text
https://docs.google.com/spreadsheets/d/1ABCDEF1234567890XYZ/edit#gid=0
```

Nesse caso:

```text
1ABCDEF1234567890XYZ
```

### Onde colocar

```python
GOOGLE_SHEETS_ID = "ID_DA_PLANILHA"
```

## 5. Service Account do Google para Sheets

Necessária para o script escrever na planilha.

### Como criar

1. No Google Cloud Console, vá em `IAM e administrador` -> `Contas de serviço`.
2. Clique em `Criar conta de serviço`.
3. Dê um nome simples, como `lead-hunter-sheets`.
4. Depois de criada, entre nela.
5. Vá em `Chaves`.
6. Clique em `Adicionar chave` -> `Criar nova chave`.
7. Escolha `JSON`.
8. O arquivo será baixado automaticamente.

### Como usar no projeto

1. Renomeie o arquivo para `service_account.json`.
2. Coloque esse arquivo na raiz do projeto.
3. Compartilhe a planilha com o e-mail da conta de serviço, com permissão de editor.

Se quiser usar o JSON inline em vez do arquivo, preencha:

```python
GOOGLE_SERVICE_ACCOUNT_JSON = "{\"type\":\"service_account\", ... }"
```

Mas o caminho mais simples é deixar o arquivo na raiz.

## 6. Gmail para notificações

Usado para enviar o resumo da rodada.

### Como configurar

1. Ative autenticação em duas etapas na conta Gmail.
2. Acesse [App Passwords](https://myaccount.google.com/apppasswords).
3. Gere uma senha de app para `Mail`.
4. Copie a senha gerada.

### Onde colocar

```python
NOTIFICATION_EMAIL = "email_que_recebe_o_resumo@dominio.com"
SMTP_EMAIL = "seu_gmail@gmail.com"
SMTP_APP_PASSWORD = "senha_de_app_aqui"
```

## Checklist final

Antes de rodar, confirme:

- `GOOGLE_MAPS_API_KEY` preenchida
- `APIFY_TOKEN` preenchido
- `GEMINI_API_KEY` preenchida
- `GOOGLE_SHEETS_ID` preenchido
- `NOTIFICATION_EMAIL` preenchido
- `SMTP_EMAIL` preenchido
- `SMTP_APP_PASSWORD` preenchido
- `service_account.json` na raiz do projeto
- planilha compartilhada com a service account

## Primeiro teste

Rode:

```bash
python main.py
```

Se preferir Colab, abra [setup_colab.ipynb](/D:/Users/wesle/PROJETOS%20CODEX/AUTOMA%C3%87%C3%83O%20PARA%20BUSCAR%20LEAD/setup_colab.ipynb).

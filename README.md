# Radar de Licitações

MVP estático para localizar oportunidades com recebimento de propostas aberto no PNCP e gerar alertas Telegram. O piloto vem configurado para tecnologia em Santa Catarina; nenhuma cobrança é processada.

## Fonte e consulta

- Documentação consultada: [Portal PNCP](https://www.gov.br/pncp/pt-br), [Swagger da API de consulta](https://pncp.gov.br/api/consulta/swagger-ui/index.html), [OpenAPI JSON](https://pncp.gov.br/pncp-consulta/v3/api-docs) e [manual de consultas](https://www.gov.br/pncp/pt-br/pncp/copy_of_manuais).
- Endpoint usado: `GET https://pncp.gov.br/api/consulta/v1/contratacoes/proposta` (contratações com recebimento de propostas aberto).
- Parâmetros obrigatórios segundo o OpenAPI: `dataFinal` e `pagina`. A chamada testada usa `dataFinal=yyyyMMdd`; o Swagger omite a descrição do formato nesse endpoint, mas a chamada real com `20261018` foi aceita. `tamanhoPagina` aceita 10 a 50 (máximo documentado 50); `uf` e `codigoModalidadeContratacao` são opcionais. Não há filtro textual oficial nesse endpoint.
- A resposta é um objeto com `data`, `totalPaginas`, `totalRegistros`, `numeroPagina`, `paginasRestantes` e `empty`. Os registros consultados incluem objeto, órgão, unidade/UF/município, valor estimado, prazo, modalidade, situação e atualização, quando publicados.
- A janela da API tem apenas limite final. O código confere localmente prazo, rótulos explícitos de situação, palavra-chave e faixa de valor. Não mapeia os códigos numéricos de situação, pois o contrato consultado não explica seus significados.
- O OpenAPI limita páginas, mas não publica uma cota de requisições por intervalo. O cliente espaça chamadas, trata 429/5xx e timeout com tentativas progressivas, respeita `Retry-After` até 600 segundos e adia a execução se o servidor pedir mais. Após esgotar tentativas, a execução falha sem gravar uma lista vazia.

## Executar localmente

Requer Python 3.12+ e não usa dependências externas.

```powershell
Copy-Item .env.example .env
$env:RADAR_UF = "SC"
$env:RADAR_KEYWORD = "tecnologia"
python -m unittest discover -s tests -v
python main.py
python generate_pages.py
python -m http.server 8000 --directory dist
```

Abra `http://localhost:8000`. Sem uma coleta concluída, a interface mostra que ainda não há dados, sem afirmar que não existem oportunidades. Após 36 horas (configurável por `RADAR_MAX_DATA_AGE_HOURS`), o site esconde a lista e marca o snapshot como desatualizado; o gerador também deixa de criar páginas de detalhe/SEO a partir dele. Uma falha da API preserva o último estado bom. `RADAR_MAX_PAGES` limita a busca; se a API informar páginas além desse limite, a coleta é marcada incompleta e não é salva.

Variáveis disponíveis estão em `.env.example`. O piloto consulta uma UF para limitar volume; palavra-chave é filtrada localmente nos campos de objeto, órgão e modalidade.

## Telegram

Crie um bot no BotFather e configure `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` somente no ambiente local ou em GitHub Actions Secrets. Sem essas variáveis, o digest de novidades é salvo localmente em `data/last_digest.txt` e permanece pendente; nenhum segredo vai para logs. `RADAR_MAX_ALERTS` limita os editais por execução. O digest é ordenado por encerramento; falhas são mantidas no estado para nova tentativa.

O envio HTTP real não foi testado porque não há credenciais. Os testes verificam geração do digest, payload e persistência por lote usando transporte simulado. E-mail é somente uma interface futura (`radar/email_notifier.py`).

## GitHub Actions e publicação

O workflow `.github/workflows/radar.yml` executa diariamente às 10:15 UTC e também pode ser iniciado manualmente. Ele roda os testes, coleta, gera páginas e versiona `data/radar_data.json`, que contém apenas dados públicos e IDs técnicos de deduplicação. O workflow requer permissão de escrita em `contents`; configure os valores de filtro em Repository Variables e as credenciais Telegram apenas em Secrets.

Conecte o repositório ao Netlify para publicar `dist` conforme `netlify.toml`. O commit diário do estado dispara a nova publicação. O workflow evita execuções concorrentes. O sitemap só é gerado quando `RADAR_SITE_URL` estiver definida. Netlify Forms recebe o formulário de interesse e o pedido de exclusão no painel do provedor; esses formulários não funcionam como armazenamento local. Não há contagem própria de visitantes ou usuários ativos.

## Dados e limitações

- O arquivo JSON mantém a fotografia atual da UF selecionada, deduplicação e estado de alertas; não é um histórico analítico. É adequado para o volume limitado do piloto. Os commits diários guardam versões no histórico Git; uma base/histórico maior exigiria armazenamento separado, ainda não justificado.
- Detalhes individuais são gerados para registros da fotografia atual. Páginas SEO por segmento/UF só são criadas quando há pelo menos cinco oportunidades textualmente compatíveis. A busca textual não interpreta documentos nem garante classificação comercial.
- O canal público gratuito com 24 horas de atraso, cobrança, cadastro autenticado, envio de e-mail e métricas de visitantes/ativos não estão implementados.
- [Privacidade](site/privacidade.html) e [termos](site/termos.html) são rascunhos operacionais, não documentos prontos para lançamento. Faltam identificar o controlador, confirmar retenção/configurações contratuais do Netlify, definir prazo de resposta a pedidos e fazer revisão jurídica. Pedidos enviados pelo formulário ainda exigem atendimento manual no painel do provedor.
- A API respondeu a consultas reais e o contrato de paginação foi observado. Uma consulta nacional real com `dataFinal=20261018`, `pagina=1`, `tamanhoPagina=10` indicou quatro páginas. Após as chamadas exploratórias, uma execução completa do coletor recebeu HTTP 429 mesmo após tentativas; portanto, não foi possível concluir uma coleta integral nesta máquina.
- Amostra conferida manualmente: controle `01010042000176-1-000316/2025`, órgão CISVIR, unidade em Apucarana/PR, modalidade Credenciamento, valor estimado R$ 100.000,00, encerramento 19/10/2026 00:00. O link `https://pncp.gov.br/app/editais/01010042000176/2025/316` abriu o mesmo edital e apresentou esses campos. Valores e prazo dependem do órgão publicador.
- O domínio público limitou novas chamadas durante a validação. Não foi possível concluir a coleta completa, alimentar o site com o snapshot atual, verificar dados em vários estados nem enviar mensagem Telegram real. Reexecute `python main.py` ou o workflow quando a cota estiver disponível e confirme o novo timestamp antes de demonstrar oportunidades.

## Custos e validação comercial

GitHub Actions e Netlify têm faixas gratuitas sujeitas a cotas e políticas dos provedores; Telegram Bot API não tem custo de envio pelo próprio serviço. Não há banco, servidor permanente nem dependência paga nesta arquitetura. Crescimento de tráfego, analytics, envio de e-mail ou maior histórico podem gerar custos futuros.

O plano Fundador de R$ 49/mês é uma hipótese de preço; pagamentos não estão habilitados. O formulário coleta apenas segmento, UF e contato com consentimento; não peça CPF ou outros dados sensíveis.
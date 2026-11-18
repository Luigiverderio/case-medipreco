# Medipreço · fechamento do mês

Lê o contrato de cada cliente, calcula a mensalidade mês a mês, confere as notas emitidas e explica cada número para
Financeiro, Customer Success, RH do cliente e Comercial. Todos os dados são fictícios.

A proposta está em `saida/site/proposta.html` e o uso de IA em `USO_DE_IA.md`.

## Como ligar

1. Cole a chave da IA na aba **Sistema** (só a análise de contratos usa). Se preferir, copie `.env.example` para `.env` e preencha.
2. Dê dois cliques em **`iniciar.bat`** (na primeira vez ele instala o que precisa).
3. Abra **http://127.0.0.1:5000**. Não há login.

## O que tem no site

- **Financeiro:** as notas emitidas, quais batem e quais têm divergência. Escolha um cliente para ver todos os meses dele.
- **Customer Success:** uma página por cliente com a regra do contrato e cada mês.
- **RH do cliente:** um extrato por cliente, só com os dados dele.
- **Comercial:** o que o sistema já sabe cobrar.
- **Contratos:** envie um PDF. O agente lê, propõe a regra de cobrança e você **aprova** (a regra passa a valer) ou rejeita.
  Dá para excluir uma submissão.
- **Aprovações:** contratos que não foram vinculados sozinhos.
- **Sistema:** botões para atualizar as páginas, conferir as notas, analisar os contratos de exemplo, verificar a
  auditoria e rodar os testes.

Financeiro, Customer Success e RH geram uma página para cada cobrança de cliente.

## Limites

- Só dá para aprovar regra de cliente que já está na base de empresas.
- Usa só contratos fictícios: o texto do PDF vai para a API da NVIDIA.

# Como a IA foi usada

## Onde a IA está

1. **Dentro da solução.** Um agente lê o contrato em PDF, extrai como a cobrança funciona (citando a cláusula de cada
   campo) e propõe o vínculo com uma regra. Modelo atual: `nvidia/nemotron-3.5-super-vl-120b-a12b`, pela API da NVIDIA.
   O prompt do agente e o formato da resposta estão em `src/vincular.py` (constantes `SISTEMA` e `FERRAMENTA`).
   O agente **só classifica e extrai**. Quem confere os CNPJs, decide o vínculo e calcula são funções comuns de código.
2. **No processo.** Usei o Claude Code (Claude) como par de programação para ler o case, desenhar a arquitetura,
   escrever o motor de cálculo, as pontes de conciliação, a auditoria e as páginas, sempre numa conversa em que eu
   decidia e ele propunha e verificava.

## Decisões que foram minhas

- Montar uma **linha do tempo por cliente** e calcular a partir dela, separando o fato da regra.
- **Hash** na auditoria, para provar qual PDF foi lido e que o log não foi alterado.
- O motor deve cobrir o que o **PDF do case descreve**, e não só os 6 contratos de exemplo.
- **Páginas separadas por quem usa** (Financeiro, CS, RH, Comercial), com o extrato de cada cliente em arquivo próprio.
- Rodar só local, sem deploy, por causa do prazo.

## Prompts e perguntas que moveram o trabalho

- "O contrato é enviado ao sistema, um agente lê, procura se alguma regra se enquadra e liga a empresa; se não, deixa
  para aprovação humana, e isso pode ser auditado." (origem da parte 1)
- "Se for contrato diferente, ele vai tentar incluir numa dessas 4 regras ou deixa para aprovação manual?"
- "Se a empresa tinha 100 funcionários e saíram 20, serão cobrados 80 ou 100?"
- "Base sem filtrar por titular, isso não seria interessante?" (origem do diagnóstico de causa)
- "Quem cria essas regras atualmente?" e "Eu preciso construir o motor com base no PDF, não nos exemplos."

## Dados e segurança

Todos os dados são fictícios. O texto dos PDFs enviados na aba **Contratos** vai para o endpoint da NVIDIA. As chaves
de API ficam só no `.env` local, ignorado pelo git, e nunca no código.


## Guiando a IA

Em praticamente todas as etapas do processo de criação, orientei a IA de como eu gostaria que o sistema se comportasse
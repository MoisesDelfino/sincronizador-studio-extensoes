# Sincronizador do Studio Extensões

Aplicação web local para comparar e sincronizar os scripts do Studio Extensões com um repositório escolhido pelo usuário.

## Comportamento

- antes de criar um arquivo, o sincronizador procura recursivamente pelo mesmo nome em toda a pasta escolhida;
- se o arquivo já existir em qualquer subpasta, ele é comparado e atualizado naquele mesmo local, independentemente de ser `JOB` ou `COMPONENTE`;
- somente arquivos inexistentes usam o destino padrão: `JOB` na pasta escolhida e `COMPONENTE` na subpasta `Componentes`;
- caracteres que não podem existir em nomes de arquivos (`/`, `\\`, `:`, `*` e equivalentes) são convertidos para ` - `;
- duas ocorrências locais com o mesmo nome são tratadas como conflito para evitar atualizar o arquivo errado;
- o conteúdo remoto é mantido em cache por sistema, script e revisão; revisões já conhecidas não são baixadas novamente;
- a listagem remota continua sendo consultada em cada análise, portanto uma nova revisão invalida o cache automaticamente;
- arquivos locais que não existem remotamente não são removidos;
- conflitos exibem sua causa completa, mas não impedem a sincronização dos demais arquivos;
- a prévia permite pesquisar scripts, navegar em páginas de 10, 20 ou 50 itens e selecionar itens individuais, toda a página ou todos os itens sincronizáveis;
- a página aberta pode ser filtrada por uma ou mais situações: criar, atualizar, inalterado e conflito/erro; sem nenhuma situação marcada, a tabela fica vazia;
- o carregamento fica destacado durante operações demoradas e a interface indica continuamente o próximo passo;
- a listagem é carregada primeiro e o `codigoFonte` é solicitado somente quando a página correspondente é aberta; páginas já analisadas permanecem em cache;
- a análise não altera arquivos; somente o botão **Sincronizar** grava as mudanças;
- usuário, senha e MFA não são armazenados pelo sincronizador;
- a sessão é preservada no perfil privado do Chromium, como em um navegador comum, e pode ser apagada por **Trocar conta**.

## Preparação

Para desenvolvimento, é necessário Python 3.10 ou mais recente e Chromium para Playwright. Os aplicativos portáteis publicados já incluem essas dependências.

```bash
python3 -m pip install --user -r tools/studio_sync/requirements.txt
playwright install chromium
```

## Execução

Abra o aplicativo portátil **Studio Sync**. Para desenvolvimento, execute a partir da raiz deste projeto:

```bash
python3 -m tools.studio_sync.main
```

1. Clique em **Entrar no Studio Extensões**.
2. Conclua o login e o MFA diretamente na janela oficial da Betha.
3. Escolha a entidade de origem.
4. Selecione esta pasta `scripts` ou outro repositório compatível.
5. Analise as diferenças e revise a prévia.
6. Clique em **Sincronizar** para aplicar.

## Segurança

Não cole tokens no código. A janela de autenticação é temporária e fechada depois que a aplicação captura a sessão já autenticada. Cookies e armazenamento da página oficial permanecem no perfil local do Chromium para reutilizar a sessão enquanto ela for válida. Os logs nunca devem incluir cabeçalhos HTTP.


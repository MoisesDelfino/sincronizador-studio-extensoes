# Studio Sync

Ferramenta local para comparar e sincronizar scripts, componentes, críticas, fontes dinâmicas e relatórios do Studio Extensões com uma pasta do computador.

## Requisitos

- acesso à rede corporativa ou à VPN da Betha;
- internet na primeira execução;
- [Git](https://git-scm.com/downloads), para clonar e atualizar a ferramenta;
- [Python 3.10 ou mais recente](https://www.python.org/downloads/).

Não é necessário instalar pacotes Python, executar `pip` ou executar `npm`. O inicializador prepara as dependências e o navegador de autenticação automaticamente dentro da pasta do projeto.

No Windows, se o Python não estiver disponível, o inicializador tentará instalá-lo pelo `winget`. No Ubuntu ou Debian, se necessário, instale os requisitos com:

```bash
sudo apt install git python3 python3-venv python3-pip
```

## Instalar e abrir

### 1. Clonar o projeto

No terminal, execute:

```bash
git clone https://github.com/MoisesDelfino/sincronizador-studio-extensoes.git
```

Isso criará a pasta `sincronizador-studio-extensoes`. Abra essa pasta no explorador de arquivos.

Se preferir uma interface gráfica, use o GitHub Desktop e escolha **File → Clone repository → URL**, informando o mesmo endereço do repositório.

### 2. Abrir o inicializador

Dentro da pasta clonada, abra o arquivo correspondente ao seu sistema:

| Sistema | Arquivo |
| --- | --- |
| Windows | `Abrir Studio Sync.bat` |
| macOS | `Abrir Studio Sync.command` |
| Linux | `Abrir Studio Sync.desktop` |

### 3. Aguardar a primeira preparação

Na primeira abertura, a ferramenta cria um ambiente Python próprio, instala as dependências e baixa o navegador usado na autenticação. Esse processo requer internet e pode levar alguns minutos. Nas próximas aberturas, a inicialização será mais rápida.

- **macOS:** na primeira vez, clique com o botão direito no arquivo `.command` e selecione **Abrir**.
- **Linux:** se necessário, habilite **Permitir executar como programa** nas propriedades do arquivo `.desktop`.

O Studio Sync funciona somente enquanto estiver aberto.

## Como usar

1. Conecte-se à rede Betha ou à VPN.
2. Abra o Studio Sync pelo arquivo correspondente ao seu sistema.
3. Entre no Studio Extensões e conclua o MFA.
4. Selecione a entidade e o sistema.
5. Escolha a pasta local e os tipos de artefato.
6. Analise as diferenças.
7. Selecione os arquivos desejados e confirme a sincronização.

A análise é apenas uma prévia. Nenhum arquivo é alterado antes da confirmação.

Depois de sincronizar, é possível voltar e selecionar outra entidade, sistema ou pasta.

## Organização dos arquivos

| Tipo | Pasta de destino |
| --- | --- |
| Scripts | Pasta selecionada |
| Componentes | `Componentes` |
| Críticas | `Criticas` |
| Fontes dinâmicas | `FontesDinamicas` |
| Relatórios JRXML | `Relatorios` |

Se o arquivo já existir em uma subpasta, ele será atualizado no local existente. Arquivos locais que não existem no Studio não são removidos.

## Desfazer uma sincronização

Use **Desfazer última sincronização** para restaurar os arquivos atualizados e remover os arquivos criados pela última operação.

Por segurança, a restauração é bloqueada quando algum desses arquivos foi editado depois da sincronização.

## Problemas comuns

- **Entidade ou sistema não aparece:** solicite o acesso pelo Betha Admin e entre novamente na ferramenta.
- **Falha ao autenticar ou consultar:** confira a conexão com a rede corporativa ou VPN.
- **Verificação de versão indisponível:** a ferramenta abrirá a versão local; confira a internet, o Git e se o repositório possui alterações locais.
- **Primeira abertura não conclui:** confirme que o Python 3.10+ está instalado e tente novamente com acesso à internet.

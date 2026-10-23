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

### 2. Fazer a primeira execução pelo terminal

Na primeira execução, não use o atalho. Abra um terminal dentro da pasta `sincronizador-studio-extensoes` e execute:

```bash
python3 iniciar.py
```

No Windows, use:

```powershell
py iniciar.py
```

Esse primeiro início prepara automaticamente o ambiente e disponibiliza o atalho para as próximas execuções.

### 3. Aguardar a primeira preparação

A ferramenta cria um ambiente Python próprio, instala as dependências e baixa o navegador usado na autenticação. Esse processo requer internet e pode levar alguns minutos.

### 4. Usar o atalho nas próximas execuções

Depois que a primeira preparação terminar, use o atalho correspondente ao seu sistema:

| Sistema | Arquivo |
| --- | --- |
| Windows | `Abrir Studio Sync.bat` |
| macOS | `Abrir Studio Sync.command` |
| Linux | **Studio Sync**, no menu de aplicativos, ou `Abrir Studio Sync.desktop` |

- **macOS:** se necessário, clique com o botão direito no arquivo `.command` e selecione **Abrir**.
- **Linux:** prefira o atalho **Studio Sync** criado no menu de aplicativos. Para usar o arquivo `.desktop`, talvez seja necessário clicar nele com o botão direito e escolher **Permitir iniciar**.

### Se o atalho não abrir

Abra um terminal dentro da pasta `sincronizador-studio-extensoes` e execute:

```bash
python3 iniciar.py
```

No Windows, se o comando acima não for reconhecido, use:

```powershell
py iniciar.py
```

Esse comando pode ser usado sempre que o atalho não funcionar.

O Studio Sync funciona somente enquanto estiver aberto.

## Como usar

1. Conecte-se à rede Betha ou à VPN.
2. Na primeira execução, inicie pelo terminal; nas seguintes, use o atalho disponível.
3. Entre no Studio Extensões e conclua o MFA.
4. Selecione a entidade e o sistema. Entidades nas quais sua conta possui acesso ao Orquestrador são identificadas pela tag **Orquestrador**.
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

Pastas equivalentes, como `Components` e `Componentes`, são reaproveitadas para evitar duplicidade. A renomeação ou consolidação aparece na prévia e na confirmação antes de ser aplicada. Se houver arquivos diferentes no mesmo caminho, a sincronização é bloqueada para evitar sobrescrita.

## Desfazer uma sincronização

Use **Desfazer última sincronização** para restaurar os arquivos atualizados, remover os arquivos criados e recuperar os nomes e a organização anterior das pastas movimentadas.

Por segurança, a restauração é bloqueada quando algum arquivo ou pasta envolvido foi editado depois da sincronização.

## Problemas comuns

- **Entidade, sistema ou tag do Orquestrador não aparece:** use **Atualizar acessos**; se continuar ausente, solicite o acesso pelo Betha Admin e entre novamente na ferramenta.
- **Falha ao autenticar ou consultar:** confira a conexão com a rede corporativa ou VPN.
- **Verificação de versão indisponível:** a ferramenta abrirá a versão local; confira a internet, o Git e se o repositório possui alterações locais.
- **Primeira abertura não conclui:** confirme que o Python 3.10+ está instalado e tente novamente com acesso à internet.
- **Atalho não abre:** abra um terminal na pasta do projeto e execute `python3 iniciar.py` (`py iniciar.py` no Windows).

# Studio Sync

Ferramenta local para comparar e sincronizar scripts, componentes, críticas, fontes dinâmicas e relatórios do Studio Extensões com uma pasta do computador.

## Requisitos

- acesso à rede corporativa ou à VPN da Betha;
- internet na primeira execução;
- Python 3.10 ou mais recente;
- Git, para receber atualizações automáticas.

No Windows, o inicializador tenta instalar o Python pelo `winget` quando necessário.

## Instalação

Clone o [repositório do Studio Sync](https://github.com/MoisesDelfino/sincronizador-studio-extensoes) para que a ferramenta possa se atualizar automaticamente ao abrir.

Também é possível usar **Code → Download ZIP**, mas essa opção não recebe atualizações automáticas. Quando houver uma nova versão, será necessário baixar e extrair o ZIP novamente.

## Como abrir

| Sistema | Arquivo |
| --- | --- |
| Windows | `Abrir Studio Sync.bat` |
| macOS | `Abrir Studio Sync.command` |
| Linux | `Abrir Studio Sync.desktop` |

Na primeira abertura, aguarde a preparação automática do ambiente e do navegador usado na autenticação.

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

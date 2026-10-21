# Sincronizador do Studio Extensões

Aplicação local para comparar e sincronizar scripts, componentes, críticas e fontes dinâmicas do Studio Extensões com uma pasta do computador. A interface abre no navegador e não exige terminal nem configuração técnica.

> **Antes de começar:** conecte o computador à rede corporativa ou à VPN da Betha. A autenticação e a consulta dos scripts dependem desse acesso.

## Baixar e executar

1. Na [página do projeto](https://github.com/MoisesDelfino/sincronizador-studio-extensoes), clique em **Code → Download ZIP** e extraia em uma pasta de sua preferência. Se preferir, clone o repositório com `git clone`.
2. Dê duplo clique no arquivo do seu sistema:

| Sistema | Arquivo |
| --- | --- |
| Windows | `Abrir Studio Sync.bat` |
| macOS | `Abrir Studio Sync.command` |
| Linux | `Abrir Studio Sync.desktop` (ou `Abrir Studio Sync.sh`) |

Na primeira execução o aplicativo prepara o ambiente sozinho (ambiente Python e navegador do login), o que exige internet e leva alguns minutos. Nas próximas, abre em segundos.

**Requisito:** Python 3.10 ou mais recente. No Windows, se não houver Python, o lançador o instala pelo winget.

- **macOS:** na primeira vez, clique com o botão direito no `.command` → **Abrir**. Se necessário, rode `chmod +x "Abrir Studio Sync.command"`.
- **Linux:** se o sistema não permitir, marque **Permitir executar como programa** nas propriedades do arquivo `.desktop`.

O Studio Sync funciona somente enquanto está aberto.

## Acesso a entidades e sistemas

A ferramenta lista apenas as **entidades e sistemas aos quais o seu usuário tem acesso**. Se uma entidade ou sistema de que você precisa não aparecer, solicite a liberação pelo **Betha Admin**. Depois de concedido o acesso, use **Trocar conta** ou entre novamente para atualizar a lista.

## Primeiro uso

1. Conecte-se à rede Betha ou à VPN.
2. Abra o Studio Sync pelo arquivo `Abrir Studio Sync`.
3. Clique em **Entrar no Studio Extensões** e conclua o login e o MFA na página oficial da Betha.
4. Confira a entidade (somente as que você tem acesso são listadas), escolha o sistema e selecione a pasta do repositório local.
5. Clique em **Analisar diferenças**. Apenas a página exibida terá o conteúdo carregado.
6. Pesquise ou filtre os scripts, selecione os desejados e clique em **Sincronizar selecionados**.

Arquivos novos são organizados por tipo: scripts na pasta escolhida, componentes em `Componentes`, críticas em `Criticas` e fontes dinâmicas em `FontesDinamicas`. Se um arquivo com o mesmo nome já existir em outra subpasta, ele é atualizado no local existente.

A análise apenas apresenta uma prévia. Nenhum arquivo é alterado antes da confirmação em **Sincronizar agora**.

## Segurança e restauração

Antes de cada sincronização, o Studio Sync guarda uma cópia dos arquivos que serão alterados. Use **Desfazer última sincronização** para restaurar arquivos atualizados e remover os que foram criados naquela operação.

O aplicativo não desfaz a operação se detectar que algum dos arquivos foi editado posteriormente. Essa proteção evita substituir trabalho novo por uma cópia antiga. Os snapshots ficam na pasta de dados local do Studio Sync, fora do repositório selecionado.

## Privacidade e funcionamento

- usuário, senha e código MFA são informados somente na página oficial da Betha;
- a aplicação preserva uma sessão privada do navegador para evitar logins repetidos enquanto ela for válida;
- use **Trocar conta** para apagar a sessão local;
- conteúdos já consultados ficam em cache por revisão, acelerando as próximas análises;
- arquivos locais que não existem no Studio não são removidos;
- conflitos são apresentados com a causa e não impedem a sincronização dos demais arquivos.

Consulte a [documentação detalhada](tools/studio_sync/README.md) para conhecer todas as regras de comparação e sincronização.

<details>
<summary><strong>Informações para desenvolvimento</strong></summary>

Execução pelo código-fonte (Python 3.10+): `python3 iniciar.py`. Validação completa: `python3 validar.py`.

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) para o fluxo de branches, Pull Request, smoke test, publicação e rollback.

</details>

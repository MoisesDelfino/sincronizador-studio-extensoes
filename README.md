# Sincronizador do Studio Extensões

Aplicação local para comparar e sincronizar scripts `JOB` e componentes do Studio Extensões com uma pasta do computador. A interface abre no navegador e não exige terminal, Python ou configuração técnica.

> **Antes de começar:** conecte o computador à rede corporativa ou à VPN da Betha. A autenticação e a consulta dos scripts dependem desse acesso.

## Baixar o instalador

Escolha o sistema operacional. Os links sempre apontam para a versão mais recente publicada:

| Sistema operacional | Download | Compatibilidade |
| --- | --- | --- |
| Windows | **[Baixar instalador para Windows](https://github.com/MoisesDelfino/sincronizador-studio-extensoes/releases/latest/download/StudioSync-Windows-Setup.exe)** | Windows 10 ou 11, 64 bits |
| Linux | **[Baixar instalador para Linux](https://github.com/MoisesDelfino/sincronizador-studio-extensoes/releases/latest/download/StudioSync-Linux-amd64.deb)** | Ubuntu, Debian e derivados, 64 bits |
| macOS — Apple Silicon | **[Baixar para Mac com chip Apple](https://github.com/MoisesDelfino/sincronizador-studio-extensoes/releases/latest/download/StudioSync-macOS-AppleSilicon.dmg)** | Mac com chip M1, M2, M3 ou mais recente |
| macOS — Intel | **[Baixar para Mac Intel](https://github.com/MoisesDelfino/sincronizador-studio-extensoes/releases/latest/download/StudioSync-macOS-Intel.dmg)** | Mac com processador Intel |

O instalador já inclui a aplicação, o Python e o navegador usado no login. Não é necessário instalar dependências separadamente.

### Instalar no Windows

1. Baixe `StudioSync-Windows-Setup.exe`.
2. Abra o arquivo e avance pelo assistente.
3. Mantenha marcada a opção para criar um atalho, se desejar.
4. Ao final, clique em **Abrir Studio Sync**.

### Instalar no Linux

1. Baixe `StudioSync-Linux-amd64.deb`.
2. Abra o arquivo com a loja de aplicativos do sistema.
3. Clique em **Instalar**.
4. Procure por **Studio Sync** no menu de aplicativos.

### Instalar no macOS

1. Confira em **Menu Apple → Sobre Este Mac** se o processador é Apple ou Intel.
2. Baixe o arquivo `.dmg` correspondente.
3. Abra o arquivo e arraste **Studio Sync** para **Aplicativos**.
4. Abra o aplicativo pelo Launchpad ou pela pasta **Aplicativos**.

> Os instaladores ainda não possuem assinatura digital corporativa. Caso o Windows ou o macOS mostre uma proteção do sistema, confirme a abertura somente se o arquivo tiver sido baixado desta página oficial do projeto.

## Primeiro uso

1. Conecte-se à rede Betha ou à VPN.
2. Abra **Studio Sync** pelo atalho ou menu de aplicativos.
3. Clique em **Entrar no Studio Extensões** e conclua o login e o MFA na página oficial da Betha.
4. Confira a entidade, escolha o sistema e selecione a pasta do repositório local.
5. Clique em **Analisar diferenças**. Apenas a página exibida terá o conteúdo carregado.
6. Pesquise ou filtre os scripts, selecione os desejados e clique em **Sincronizar selecionados**.

A análise apenas apresenta uma prévia. Nenhum arquivo é alterado antes da confirmação em **Sincronizar agora**.

## Privacidade e funcionamento

- usuário, senha e código MFA são informados somente na página oficial da Betha;
- a aplicação preserva uma sessão privada do navegador para evitar logins repetidos enquanto ela for válida;
- use **Trocar conta** para apagar a sessão local;
- conteúdos já consultados ficam em cache por revisão, acelerando as próximas análises;
- arquivos locais que não existem no Studio não são removidos;
- conflitos são apresentados com a causa e não impedem a sincronização dos demais arquivos.

Consulte a [documentação detalhada](tools/studio_sync/README.md) para conhecer todas as regras de comparação e sincronização.

<details>
<summary><strong>Informações para desenvolvimento e publicação</strong></summary>

### Executar pelo código-fonte

Requer Python 3.10 ou mais recente:

```bash
python3 -m pip install --user -r tools/studio_sync/requirements.txt
playwright install chromium
python3 sincronizar_studio.py
```

### Gerar e publicar instaladores

O workflow `.github/workflows/build-installers.yml` executa os testes e constrói cada instalador no sistema operacional correspondente.

- A execução manual disponibiliza os arquivos na página da execução do GitHub Actions.
- Uma tag no formato `v*`, por exemplo `v0.3.0`, cria uma GitHub Release e publica automaticamente os quatro instaladores usados pelos links deste README.

Exemplo de publicação:

```bash
git tag v0.3.0
git push origin v0.3.0
```

</details>

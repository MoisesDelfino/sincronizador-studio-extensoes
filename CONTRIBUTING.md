# Processo seguro de alteração

## Desenvolvimento

1. Atualize a `main` e crie uma branch com prefixo `feat/`, `fix/` ou `chore/`.
2. Faça mudanças pequenas e inclua teste de regressão para toda regra alterada.
3. Execute `python3 validar.py` na raiz do projeto.
4. Faça uma verificação manual usando uma pasta temporária, nunca um repositório de trabalho sem backup.
5. Abra um Pull Request e revise o diff antes do merge.
6. Depois do smoke test e da revisão, adicione o rótulo `merge-seguro`. Quando o check
   `Validate / tests` passar, o GitHub fará squash merge e excluirá a branch remota.

Não faça push direto na `main`. A proteção da branch exige Pull Request, o check
`Validate / tests` e bloqueia force-push e exclusão. A automação ignora PRs em rascunho,
PRs sem o rótulo `merge-seguro` e PRs abertas por usuários externos.

## Smoke test antes do merge

- abrir a aplicação pelos lançadores suportados;
- autenticar e selecionar entidade e sistema;
- analisar os quatro tipos de artefato;
- conferir criação, atualização, inalterado e conflito;
- sincronizar um arquivo novo e um existente em uma pasta temporária;
- desfazer a sincronização e verificar a restauração;
- editar um arquivo depois de sincronizá-lo e confirmar que o desfazer é bloqueado;
- conferir pesquisa e primeira, anterior, próxima e última página.

## Publicação e rollback

- cada entrega estável recebe uma tag semântica, como `v0.4.0`;
- versões estáveis são imutáveis: uma correção gera nova tag, nunca substitui a anterior;
- valide a tag em uma máquina piloto antes de orientar os demais usuários;
- mantenha a versão anterior publicada para rollback imediato;
- não trate um commit sem tag como versão estável para usuários finais.

Se o GitHub Actions estiver indisponível, rode `python3 validar.py` localmente, faça o
smoke test e aguarde sua normalização. Não contorne a proteção da `main`.

## Política de custo zero

- use somente runners padrão em repositório público, atualmente gratuitos no GitHub Actions;
- nunca use larger runners, serviços pagos, cache com cobrança, armazenamento adicional ou marketplace pago;
- jobs devem ter tempo limite e cancelamento de execuções antigas;
- se uma validação deixar de ser gratuita, desative-a e use `python3 validar.py` localmente antes de gerar qualquer custo.

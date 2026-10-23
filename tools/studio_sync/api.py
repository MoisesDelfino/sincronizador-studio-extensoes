from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import replace
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

import requests

from .models import AccessOption, ArtifactKind, RemoteArtifact, SessionCredentials
from .cache import ArtifactCache


AUTH_BASE = "https://plataforma-autorizacoes.betha.cloud/user-accounts/v0.1/api"
EXTENSIONS_BASE = "https://plataforma-extensoes.betha.cloud/api"
SCRIPTS_BASE = "https://plataforma-scripts.betha.cloud/scripts/v1/api"
REPORTS_BASE = "https://plataforma-relatorios.betha.cloud/relatorios/v1/api"
ORIGIN = "https://scripts.plataforma.betha.cloud"
REPORTS_ORIGIN = "https://relatorios.plataforma.betha.cloud"


class StudioApiError(RuntimeError):
    pass


class SessionExpiredError(StudioApiError):
    def __init__(self, message: str, source: object | None = None) -> None:
        super().__init__(message)
        self.source = source


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _first(mapping: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower().replace("_", ""): value for key, value in mapping.items()}
    for name in names:
        value = lowered.get(name.lower().replace("_", ""))
        if value not in (None, ""):
            return value
    return None


def _nested_first(mapping: dict[str, Any], *names: str) -> Any:
    """Localiza um campo também em wrappers como access/context/sourceSystem."""
    for item in _walk_dicts(mapping):
        value = _first(item, *names)
        if value not in (None, ""):
            return value
    return None


def _has_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "false", "nao", "não", "null", "none"}
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _is_flexibilized(summary: dict[str, Any]) -> bool:
    """Identifica relatórios herdados de outra entidade na resposta de extensões."""
    descriptor_names = {
        "campo", "chave", "field", "key", "name", "nome", "property", "propriedade"
    }
    value_names = {"content", "conteudo", "valor", "value"}
    for item in _walk_dicts(summary):
        normalized = {
            re.sub(r"[^a-z0-9]", "", str(key).casefold()): value
            for key, value in item.items()
        }
        for key, value in normalized.items():
            if "flexibiliz" in key and _has_value(value):
                return True

        descriptor = next(
            (
                value
                for key, value in normalized.items()
                if key in descriptor_names and isinstance(value, str) and "flexibiliz" in value.casefold()
            ),
            None,
        )
        if descriptor is not None:
            values = [value for key, value in normalized.items() if key in value_names]
            if not values or any(_has_value(value) for value in values):
                return True
    return False


def _context_ids(value: Any) -> tuple[Any, Any]:
    """Extrai database/entity de contextos textuais simples ou codificados em Base64."""
    candidates: list[str] = []
    if isinstance(value, str):
        candidates.append(value)
        try:
            candidates.append(base64.b64decode(value).decode())
        except Exception:
            pass
    for candidate in candidates:
        match = re.search(r"database:(\d+),entity:(\d+)", candidate, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
    return None, None


def _shape(value: Any, depth: int = 0) -> str:
    """Descreve apenas a estrutura da resposta, sem vazar valores ou credenciais."""
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, dict):
        parts = [f"{key}:{_shape(child, depth + 1)}" for key, child in list(value.items())[:12]]
        return "object{" + ",".join(parts) + "}"
    if isinstance(value, list):
        return f"list[{_shape(value[0], depth + 1)}]" if value else "list[]"
    return type(value).__name__


def _is_id(value: Any) -> bool:
    return isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit())


def _descriptive_text(mapping: dict[str, Any], expected_ids: set[str]) -> str | None:
    """Escolhe um rótulo humano mesmo quando a API muda o nome do campo."""
    preferred = _first(
        mapping,
        "fullName",
        "nomeCompleto",
        "displayName",
        "systemName",
        "nomeSistema",
        "entityName",
        "nomeEntidade",
        "denominacao",
        "name",
        "nome",
        "title",
        "label",
        "description",
        "descricao",
        "razaoSocial",
    )
    if isinstance(preferred, str) and preferred.strip():
        return preferred.strip()

    technical = {
        "id", "value", "key", "code", "codigo", "token", "access", "type", "tipo",
        "url", "uri", "href", "active", "ativo", "status", "database", "entity", "system",
    }
    candidates: list[tuple[int, str]] = []
    for key, value in mapping.items():
        if not isinstance(value, str):
            continue
        text = value.strip()
        normalized_key = re.sub(r"[^a-z]", "", str(key).casefold())
        if (
            not text
            or text in expected_ids
            or normalized_key in technical
            or not re.search(r"[A-Za-zÀ-ÿ]", text)
            or re.match(r"^(?:https?://|[0-9a-f]{8}-[0-9a-f-]{27,})", text, re.IGNORECASE)
        ):
            continue
        score = min(len(text), 80) + (20 if " " in text else 0)
        candidates.append((score, text))
    return max(candidates, default=(0, ""))[1] or None


def _systems(value: Any) -> list[tuple[str, str]]:
    values = value if isinstance(value, list) else [value]
    result: list[tuple[str, str]] = []
    for item in values:
        if isinstance(item, dict):
            item_id = _first(item, "id", "systemId", "idSistema")
            name = _first(item, "name", "nome", "description", "descricao")
        else:
            item_id = item if _is_id(item) else None
            name = item if isinstance(item, str) and not _is_id(item) else None
        if item_id is not None or name:
            result.append((str(item_id or ""), str(name or "")))
    return result


class StudioApi:
    def __init__(
        self,
        credentials: SessionCredentials,
        timeout: float = 30,
        session: requests.Session | None = None,
        cache: ArtifactCache | None = None,
    ) -> None:
        self.credentials = credentials
        self.timeout = timeout
        self.selected_access_id = ""
        self.cache = cache or ArtifactCache()
        self.cache_hits = 0
        self.cache_misses = 0
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {credentials.access_token}",
                "Origin": ORIGIN,
                "Referer": f"{ORIGIN}/",
                "user-access": credentials.user_access,
            }
        )

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        attempts = int(kwargs.pop("_attempts", 4))
        request_timeout = float(kwargs.pop("_timeout", self.timeout))
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.session.get(url, timeout=request_timeout, **kwargs)
                if response.status_code in (401, 403):
                    raise SessionExpiredError("Sessão expirada ou acesso não autorizado.", self)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < attempts - 1:
                        time.sleep(0.5 * (2**attempt))
                        continue
                response.raise_for_status()
                return response
            except StudioApiError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
        raise StudioApiError(f"Falha ao consultar {url}: {last_error}")

    def _json(self, url: str, **kwargs: Any) -> Any:
        response = self._get(url, **kwargs)
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise StudioApiError(f"Resposta JSON inválida recebida de {url}") from exc

    def _post(self, url: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.post(url, timeout=self.timeout, **kwargs)
            if response.status_code in (401, 403):
                raise SessionExpiredError("Sessão expirada ou acesso não autorizado.", self)
            response.raise_for_status()
            return response
        except StudioApiError:
            raise
        except requests.RequestException as exc:
            raise StudioApiError(f"Falha ao consultar {url}: {exc}") from exc

    def current_user(self) -> dict[str, Any]:
        data = self._json(f"{AUTH_BASE}/users/@me")
        if not isinstance(data, dict):
            raise StudioApiError("Resposta inesperada ao consultar o usuário atual.")
        return data

    def list_accesses(self, quick: bool = False) -> list[AccessOption]:
        data = self._json(
            f"{AUTH_BASE}/suite/users/@me/access",
            params={"includeCurrentAsSourceSystem": "true"},
            **({"_attempts": 1, "_timeout": min(self.timeout, 10)} if quick else {}),
        )
        options: dict[tuple[str, str, str], AccessOption] = {}
        for item in _walk_dicts(data):
            entity = _nested_first(item, "entity", "entidade")
            database = _nested_first(item, "database", "base")
            entity_id = _nested_first(item, "entityId", "idEntidade")
            database_id = _nested_first(item, "databaseId", "idDatabase", "idBase")
            system = _nested_first(item, "system", "sistema", "sourceSystem", "sistemaOrigem")
            system_id = _nested_first(
                item, "systemId", "idSystem", "idSistema", "sourceSystemId", "idSistemaOrigem"
            )
            system_list = _nested_first(item, "systems", "sistemas", "sourceSystems", "sistemasOrigem")
            if isinstance(entity, dict):
                entity_id = entity_id or _first(entity, "id")
                entity_name = _first(entity, "name", "nome", "description", "descricao")
            else:
                entity_name = entity if isinstance(entity, str) and not _is_id(entity) else None
                if entity_id is None and _is_id(entity):
                    entity_id = entity
            if isinstance(database, dict):
                database_id = database_id or _first(database, "id")
                database_name = _first(database, "name", "nome", "description", "descricao")
            else:
                database_name = database if isinstance(database, str) and not _is_id(database) else None
                if database_id is None and _is_id(database):
                    database_id = database
            if isinstance(system, dict):
                system_id = system_id or _first(system, "id")
                system_name = _first(system, "name", "nome", "description", "descricao")
            else:
                system_name = system if isinstance(system, str) and not _is_id(system) else None
                if system_id is None and _is_id(system):
                    system_id = system
            if entity_id is None or database_id is None:
                for context_name in ("context", "contexto", "key", "chave", "encodedContext"):
                    context_database, context_entity = _context_ids(_nested_first(item, context_name))
                    database_id = database_id or context_database
                    entity_id = entity_id or context_entity
                    if entity_id is not None and database_id is not None:
                        break
            if entity_id is None or database_id is None:
                continue
            access_id = _first(item, "accessId", "idAcesso", "id") or ""
            # O interceptor oficial UserAccessContext envia licenseId no
            # cabeçalho User-Access para a combinação entidade+sistema.
            user_access = _first(item, "licenseId", "userAccess", "user_access") or ""
            entity_name = entity_name or _nested_first(item, "entityName", "nomeEntidade")
            system_name = system_name or _first(
                item, "systemName", "nomeSistema", "sourceSystemName", "nomeSistemaOrigem"
            )
            label = str(entity_name or f"Entidade {entity_id}")
            candidates = _systems(system_list) or [(str(system_id or ""), str(system_name or ""))]
            for candidate_id, candidate_name in candidates:
                resolved_id = candidate_id or str(system_id or "")
                resolved_name = candidate_name or str(system_name or "Sistema não identificado")
                key = (str(database_id), str(entity_id), resolved_id or resolved_name)
                existing = options.get(key)
                if existing is not None:
                    if label == f"Entidade {entity_id}":
                        label = existing.label
                    if resolved_name.startswith("Sistema ") or resolved_name == "Sistema não identificado":
                        resolved_name = existing.system_name
                options[key] = AccessOption(
                    label=label,
                    entity_id=str(entity_id),
                    database_id=str(database_id),
                    system_id=resolved_id,
                    system_name=resolved_name,
                    access_id=str(access_id or (existing.access_id if existing else "")),
                    user_access=str(user_access or (existing.user_access if existing else "")),
                )
        if not options:
            raise StudioApiError(
                "A API retornou uma estrutura de acessos ainda não reconhecida: " + _shape(data)
            )
        entity_names = {} if quick else self._resource_names(
            "entities",
            [
                option.entity_id
                for option in options.values()
                if option.label == f"Entidade {option.entity_id}"
            ],
        )
        system_names = {} if quick else self._resource_names(
            "systems",
            [option.system_id for option in options.values() if option.system_id and option.system_name.startswith("Sistema ")],
        )
        enriched = [
            replace(
                option,
                label=entity_names.get(option.entity_id, option.label),
                system_name=system_names.get(option.system_id, option.system_name),
            )
            for option in options.values()
        ]
        return sorted(enriched, key=lambda option: option.label.casefold())

    def resolve_entity_names(self, accesses: Iterable[AccessOption]) -> list[AccessOption]:
        """Resolve apenas os rótulos técnicos ainda sem descrição humana."""
        options = list(accesses)
        names = self._resource_names(
            "entities",
            [
                option.entity_id
                for option in options
                if option.label == f"Entidade {option.entity_id}"
            ],
        )
        return [
            replace(option, label=names.get(option.entity_id, option.label))
            for option in options
        ]

    def _resource_names(self, endpoint: str, ids: Iterable[str]) -> dict[str, str]:
        unique_ids = sorted(set(str(value) for value in ids if value))
        if not unique_ids:
            return {}
        try:
            data = self._json(f"{AUTH_BASE}/{endpoint}", params=[("id", value) for value in unique_ids])
        except StudioApiError:
            return {}
        names: dict[str, str] = {}
        if isinstance(data, dict):
            for key, value in data.items():
                resource_id = str(key)
                if resource_id not in unique_ids:
                    continue
                if isinstance(value, str) and value.strip():
                    names[resource_id] = value.strip()
                elif isinstance(value, dict):
                    name = _descriptive_text(value, set(unique_ids))
                    if name:
                        names[resource_id] = name
        for item in _walk_dicts(data):
            id_names = (
                ("id", "systemId", "idSystem", "idSistema", "value", "codigo")
                if endpoint == "systems"
                else ("id", "entityId", "idEntidade", "value", "codigo")
            )
            item_id = _first(item, *id_names)
            name = _first(
                item,
                "fullName",
                "nomeCompleto",
                "displayName",
                "systemName",
                "nomeSistema",
                "entityName",
                "nomeEntidade",
                "denominacao",
                "name",
                "nome",
                "title",
                "label",
                "description",
                "descricao",
                "razaoSocial",
            )
            if item_id is None:
                # Algumas respostas usam chaves não documentadas, como
                # codigoSistema. Correlacionamos qualquer valor escalar ao ID pedido.
                item_id = next(
                    (
                        str(value)
                        for value in item.values()
                        if not isinstance(value, (dict, list)) and str(value) in unique_ids
                    ),
                    None,
                )
            if item_id is not None and str(item_id) in unique_ids:
                resolved_name = name.strip() if isinstance(name, str) and name.strip() else _descriptive_text(item, set(unique_ids))
                if resolved_name:
                    names[str(item_id)] = resolved_name
        return names

    def select_access(self, option: AccessOption) -> str:
        # A lista de acessos traz um user-access diferente para cada sistema.
        # Usá-lo diretamente replica o UserAccessContext do frontend oficial.
        if option.user_access:
            self.credentials = SessionCredentials(
                self.credentials.access_token,
                option.user_access,
                self.credentials.selected_entity_id,
                self.credentials.selected_database_id,
            )
            self.session.headers["user-access"] = option.user_access
            self.selected_access_id = option.access_id
            return option.user_access
        context = base64.b64encode(option.context.encode()).decode()
        response = self._get(f"{AUTH_BASE}/suite/users/@me/access/{quote(context, safe='')}")
        try:
            data = response.json()
        except ValueError:
            data = {}
        access_id = _first(data, "accessId", "idAcesso", "id") if isinstance(data, dict) else None
        if access_id is None:
            for item in _walk_dicts(data):
                access_id = _first(item, "accessId", "idAcesso")
                if access_id:
                    break
        self.selected_access_id = str(access_id or option.access_id or "")
        user_access = response.headers.get("user-access", "")
        if not user_access and isinstance(data, str):
            user_access = data
        if not user_access:
            for item in _walk_dicts(data):
                candidate = _first(item, "userAccess", "user_access", "accessToken", "token")
                if candidate:
                    user_access = str(candidate)
                    break
        if not user_access:
            user_access = option.user_access
        if not user_access:
            # A sessão capturada já corresponde ao acesso atualmente selecionado.
            user_access = self.credentials.user_access
        self.credentials = SessionCredentials(
            self.credentials.access_token,
            user_access,
            self.credentials.selected_entity_id,
            self.credentials.selected_database_id,
        )
        self.session.headers["user-access"] = user_access
        return user_access

    def list_permitted_systems(self, option: AccessOption) -> list[AccessOption]:
        """Usa o mesmo endpoint do Studio para listar os sistemas da entidade."""
        context = base64.b64encode(option.context.encode()).decode()
        data = self._json(
            f"{AUTH_BASE}/suite/users/@me/access/{quote(context, safe='')}/systems",
            params={"includeCurrentAsSourceSystem": "true"},
        )
        systems: dict[str, str] = {}
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                system_id = _first(item, "id", "systemId", "idSistema", "value", "codigo")
                system_name = _first(item, "name", "nome", "systemName", "nomeSistema", "label")
                if system_id is not None:
                    systems[str(system_id)] = str(system_name or "")
        plural_names = ("systems", "sistemas", "sourceSystems", "sistemasOrigem")
        for item in _walk_dicts(data):
            for plural_name in plural_names:
                values = _first(item, plural_name)
                if values is not None:
                    for system_id, system_name in _systems(values):
                        if system_id:
                            systems[system_id] = system_name

            system = _first(item, "system", "sistema", "sourceSystem", "sistemaOrigem")
            system_id = _first(
                item, "systemId", "idSystem", "idSistema", "sourceSystemId", "idSistemaOrigem"
            )
            system_name = _first(
                item, "systemName", "nomeSistema", "sourceSystemName", "nomeSistemaOrigem"
            )
            if isinstance(system, dict):
                system_id = system_id or _first(system, "id", "value", "codigo")
                system_name = system_name or _descriptive_text(system, set())
            elif system_id is None and _is_id(system):
                system_id = system
            elif not system_name and isinstance(system, str) and not _is_id(system):
                system_name = system
            if system_id is not None:
                systems[str(system_id)] = str(system_name or systems.get(str(system_id), ""))

        if not systems:
            raise StudioApiError(
                "Nenhum sistema foi identificado para esta entidade. Formato recebido: "
                + _shape(data)
            )
        result = [
            replace(
                option,
                system_id=system_id,
                system_name=name or f"Sistema {system_id}",
            )
            for system_id, name in systems.items()
        ]
        return sorted(result, key=lambda access: access.system_name.casefold())

    def _list_page(self, kind: ArtifactKind, offset: int, limit: int = 20) -> dict[str, Any]:
        filter_value = (
            "tipo = 'RELATORIO'"
            if kind is ArtifactKind.REPORT
            else "tipo = 'SCRIPT' and propriedades in(new Propriedade"
            f"('tipoScript', '{kind.value}'))"
        )
        data = self._json(
            f"{EXTENSIONS_BASE}/extensao",
            params={"filter": filter_value, "sort": "", "offset": offset, "limit": limit},
        )
        if not isinstance(data, dict) or not isinstance(data.get("content"), list):
            raise StudioApiError("Formato inesperado na listagem de extensões.")
        return data

    def list_artifact_summaries(self, kind: ArtifactKind) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        offset = 0
        seen_offsets: set[int] = set()
        while True:
            if offset in seen_offsets:
                raise StudioApiError("Loop detectado durante a paginação.")
            seen_offsets.add(offset)
            page = self._list_page(kind, offset)
            content = page["content"]
            result.extend(
                item
                for item in content
                if isinstance(item, dict) and not _is_flexibilized(item)
            )
            if not page.get("hasNext"):
                return result
            if not content:
                raise StudioApiError("A API indicou outra página, mas retornou uma página vazia.")
            offset += len(content)

    @staticmethod
    def _reference(summary: dict[str, Any]) -> tuple[str, str]:
        reference = summary.get("referencia") or summary.get("reference") or {}
        if not isinstance(reference, dict):
            reference = {}
        script_id = _first(reference, "id", "scriptId", "idScript")
        revision_id = _first(reference, "revisao", "revision", "revisionId", "idRevisao")
        if script_id is None:
            script_id = _first(summary, "scriptId", "idScript", "referenciaId")
        return str(script_id or ""), str(revision_id or "")

    def fetch_artifact(self, kind: ArtifactKind, summary: dict[str, Any]) -> RemoteArtifact:
        title = _first(summary, "titulo", "title", "nome")
        script_id, revision_id = self._reference(summary)
        if not title:
            raise StudioApiError("Artefato sem título na listagem.")
        if not script_id:
            raise StudioApiError(f"Não foi possível identificar o script de '{title}'.")
        context = self.credentials.user_access
        cached = self.cache.get(context, kind, str(title), script_id, revision_id)
        if cached is not None:
            self.cache_hits += 1
            return cached
        if kind is ArtifactKind.REPORT:
            self.cache_misses += 1
            response = self._post(
                f"{REPORTS_BASE}/relatorios/{quote(script_id, safe='')}/download",
                json=[],
                headers={"Origin": REPORTS_ORIGIN, "Referer": f"{REPORTS_ORIGIN}/"},
            )
            try:
                source_code = response.content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise StudioApiError(f"O JRXML de '{title}' não está codificado em UTF-8.") from exc
            if not source_code.lstrip().startswith("<?xml"):
                raise StudioApiError(f"O download de '{title}' não contém um JRXML válido.")
            artifact = RemoteArtifact(kind, str(title), script_id, revision_id, source_code)
            try:
                self.cache.put(context, artifact)
            except OSError:
                pass
            return artifact
        # O detalhe é a fonte confiável da revisão atual.
        detail = self._json(f"{EXTENSIONS_BASE}/extensao/SCRIPT/{quote(script_id, safe='')}")
        if isinstance(detail, dict):
            detail_script_id, detail_revision_id = self._reference(detail)
            script_id = detail_script_id or script_id
            revision_id = detail_revision_id or revision_id
        if not revision_id:
            raise StudioApiError(f"Não foi possível identificar a revisão de '{title}'.")
        cached = self.cache.get(context, kind, str(title), script_id, revision_id)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.cache_misses += 1
        revision = self._json(
            f"{SCRIPTS_BASE}/scripts/{quote(script_id, safe='')}/revisoes/{quote(revision_id, safe='')}"
        )
        if not isinstance(revision, dict) or not isinstance(revision.get("codigoFonte"), str):
            raise StudioApiError(f"A revisão de '{title}' não contém codigoFonte.")
        artifact = RemoteArtifact(kind, str(title), script_id, revision_id, revision["codigoFonte"])
        try:
            self.cache.put(context, artifact)
        except OSError:
            # Cache é uma otimização; falhas de disco não impedem a sincronização.
            pass
        return artifact


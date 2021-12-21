import json
import logging
import re
from collections import defaultdict
from typing import AsyncGenerator, List, Dict, AsyncIterator, Tuple, Callable

import yaml
from aiohttp.web import Request
from networkx import DiGraph, cytoscape_data, generate_graphml

from core.cli import is_node
from core.constants import plain_text_blacklist
from core.error import QueryTookToLongError
from core.model.resolve_in_graph import NodePath
from core.model.typed_model import to_json
from core.types import Json, JsonElement
from core.util import (
    del_value_in_path,
    value_in_path,
    value_in_path_get,
    count_iterator,
    identity,
)

log = logging.getLogger(__name__)


async def respond_json(gen: AsyncIterator[Json]) -> AsyncGenerator[bytes, None]:
    sep = ",\n".encode("utf-8")
    yield "[\n".encode("utf-8")
    first = True
    async for item in gen:
        js = json.dumps(to_json(item))
        if not first:
            yield sep
        yield js.encode("utf-8")
        first = False
    yield "\n]".encode("utf-8")


async def respond_ndjson(gen: AsyncIterator[Json]) -> AsyncGenerator[bytes, None]:
    sep = "\n"
    async for item in gen:
        js = json.dumps(to_json(item), check_circular=False)
        yield (js + sep).encode("utf-8")


async def respond_yaml(gen: AsyncIterator[Json]) -> AsyncGenerator[bytes, None]:
    flag = False
    sep = "---\n".encode("utf-8")
    async for item in gen:
        yml = yaml.dump(to_json(item), default_flow_style=False, sort_keys=False)
        if flag:
            yield sep
        yield yml.encode("utf-8")
        flag = True


async def respond_dot(gen: AsyncIterator[Json]) -> AsyncGenerator[bytes, None]:
    # We use the paired12 color scheme: https://graphviz.org/doc/info/colors.html with color names as 1-12
    cit = count_iterator()
    colors: Dict[str, int] = defaultdict(lambda: (next(cit) % 12) + 1)
    node = "node [shape=Mrecord colorscheme=paired12]"
    edge = "edge [arrowsize=0.5]"
    yield f"digraph {{\nrankdir=LR\noverlap=false\nsplines=true\n{node}\n{edge}\n".encode("utf-8")
    in_account: Dict[str, List[str]] = defaultdict(list)
    async for item in gen:
        type_name = item.get("type")
        if type_name == "node":
            uid = value_in_path(item, NodePath.node_id)
            if uid:
                name = re.sub("[^a-zA-Z0-9]", "", value_in_path_get(item, NodePath.reported_name, "n/a"))
                kind = value_in_path_get(item, NodePath.reported_kind, "n/a")
                account = value_in_path_get(item, NodePath.ancestor_account_name, "graph_root")
                paired12 = colors[kind]
                in_account[account].append(uid)
                yield f' "{uid}" [label="{name}|{kind}", style=filled fillcolor={paired12}];\n'.encode("utf-8")
        elif type_name == "edge":
            from_node = value_in_path(item, NodePath.from_node)
            to_node = value_in_path(item, NodePath.to_node)
            if from_node and to_node:
                yield f' "{from_node}" -> "{to_node}"\n'.encode("utf-8")
    # All elements in the same account are rendered as dedicated subgraph
    for account, uids in in_account.items():
        yield f' subgraph "{account}" {{\n'.encode("utf-8")
        for uid in uids:
            yield f'    "{uid}"\n'.encode("utf-8")
        yield " }\n".encode("utf-8")

    yield "}".encode("utf-8")


async def respond_text(gen: AsyncIterator[Json]) -> AsyncGenerator[bytes, None]:
    def filter_attrs(js: Json) -> Json:
        result: Json = js
        for path in plain_text_blacklist:
            del_value_in_path(js, path)
        return result

    def to_result(js: JsonElement) -> JsonElement:
        # if js is a node, the resulting content should be filtered
        return filter_attrs(js) if is_node(js) else js  # type: ignore

    try:
        flag = False
        sep = "---\n".encode("utf-8")
        cr = "\n".encode("utf-8")
        async for item in gen:
            js = to_json(item)
            if isinstance(js, (dict, list)):
                if flag:
                    yield sep
                yml = yaml.dump(to_result(js), default_flow_style=False, sort_keys=False)
                yield yml.encode("utf-8")
            else:
                if flag:
                    yield cr
                yield str(js).encode("utf-8")
            flag = True
    except QueryTookToLongError:
        yield (
            "\n\n---------------------------------------------------\n"
            "Query took too long.\n"
            "Try one of the following:\n"
            "- refine your query\n"
            "- add a limit to your query\n"
            "- define a longer timeout via env var query_timeout\n"
            "  e.g. $> query_timeout=60s query all\n"
            "---------------------------------------------------\n\n"
        ).encode("utf-8")


async def result_to_graph(gen: AsyncIterator[Json], render_node: Callable[[Json], Json] = identity) -> DiGraph:
    result = DiGraph()
    async for item in gen:
        type_name = item.get("type")
        if type_name == "node":
            uid = value_in_path(item, NodePath.node_id)
            json_result = render_node(item)
            if uid:
                result.add_node(uid, **json_result)
        elif type_name == "edge":
            from_node = value_in_path(item, NodePath.from_node)
            to_node = value_in_path(item, NodePath.to_node)
            if from_node and to_node:
                result.add_edge(from_node, to_node)
    return result


async def respond_cytoscape(gen: AsyncIterator[Json]) -> AsyncGenerator[bytes, None]:
    # Note: this is a very inefficient way of creating a response, since it creates the graph in memory
    # on the server side, so we can reuse the networkx code.
    # This functionality can be reimplemented is a streaming way.
    graph = await result_to_graph(gen, lambda js: value_in_path_get(js, NodePath.reported, {}))
    yield json.dumps(cytoscape_data(graph)).encode("utf-8")


async def respond_graphml(gen: AsyncIterator[Json]) -> AsyncGenerator[bytes, None]:
    # Note: this is a very inefficient way of creating a response, since it creates the graph in memory
    # on the server side, so we can reuse the networkx code.
    # This functionality can be reimplemented is a streaming way.
    def no_nested_props(js: Json) -> Json:
        reported: Json = value_in_path_get(js, NodePath.reported, {})
        res = {k: v for k, v in reported.items() if v is not None and not isinstance(v, (dict, list))}
        return res

    graph = await result_to_graph(gen, no_nested_props)
    for line in generate_graphml(graph):
        yield line.encode("utf-8")


async def result_binary_gen(request: Request, gen: AsyncIterator[Json]) -> Tuple[str, AsyncIterator[bytes]]:
    accept = request.headers.get("accept", "application/json")
    if accept == "application/x-ndjson":
        return "application/x-ndjson", respond_ndjson(gen)
    elif accept == "application/json":
        return "application/json", respond_json(gen)
    elif accept in ["text/plain"]:
        return "text/plain", respond_text(gen)
    elif accept in ["application/yaml", "text/yaml"]:
        return "text/yaml", respond_yaml(gen)
    elif accept == "application/vnd.cytoscape+json":
        return "application/vnd.cytoscape+json", respond_cytoscape(gen)
    elif accept in ["application/graphml+xml", "application/vnd.graphml+xml"]:
        return "application/graphml+xml", respond_graphml(gen)
    elif accept.startswith("text/vnd.graphviz"):
        return "text/yaml", respond_dot(gen)
    else:
        return "application/json", respond_json(gen)
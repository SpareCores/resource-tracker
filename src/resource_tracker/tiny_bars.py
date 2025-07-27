"""A tiny and partial implementation of the Handlebars template engine."""

from html import escape
from re import compile
from typing import Any, Dict, Tuple

TRIPLE_RE = compile(r"{{{\s*([^{}]*?)\s*}}}")
DOUBLE_RE = compile(r"{{\s*(#each|#if|#else|/each|/if)?\s*([^{}]*?)\s*}}")
EACH_RE = compile(r"([^{}]*?)\s+as\s+([^{}]*?)$")


def _resolve_var(name: str, ctx: Dict[str, Any]) -> Any:
    """Resolve a variable name in the given context.

    Supports nested lookups with dot notation with both dictionary keys and
    object attributes.

    Args:
        name: The variable name to resolve.
        ctx: The context to resolve the variable in.

    Returns:
        The resolved value, or None if not found.

    Example:
        >>> _resolve_var("user", {"user": {"name": "John"}})
        {'name': 'John'}
        >>> _resolve_var("user.name", {"user": {"name": "John"}})
        'John'
        >>> _resolve_var("user.age", {"user": {"name": "John"}})
        Traceback (most recent call last):
        ...
        KeyError: 'age not found in user.age'
    """
    parts = name.strip().split(".")
    val = ctx
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            val = getattr(val, p, None)
        if val is None:
            raise KeyError(f"{p} not found in {name}")
    return val


def render_template(template: str, context: Dict[str, Any]) -> str:
    """Render a Handlebars-like template using a dictionary context.

    Supported features:
    - Conditional flow using "{{#if expr}} ... {{#else}} ... {{/if}}"
    - Iteration using "{{#each expr as item}} ... {{/each}}"
    - Variable interpolation using "{{expr}}" (HTML-escaped) and "{{{expr}}}" (raw)
    - Nested property access using dot notation (e.g. "user.name") for dictionary
      keys and object attributes.

    Args:
        template: The template to render.
        context: The context to render the template with.

    Returns:
        The rendered text.

    Example:
        >>> from resource_tracker.tiny_bars import render_template
        >>> render_template("Hello, {{name}}!", {"name": "World"})
        'Hello, World!'
        >>> render_template("{{#each names as name}}Hello, {{name}}! {{/each}}", {"names": ["Foo", "Bar"]})
        'Hello, Foo! Hello, Bar! '
        >>> render_template("Odd numbers: {{#each numbers as number}}{{ #if number.odd}}{{number.value}} {{/if}}{{/each}}", {"numbers": [{"value": i, "odd": i % 2 == 1} for i in range(10)]})
        'Odd numbers: 1 3 5 7 9 '
        >>> render_template("{{#if present}}Yes{{/if}}", {"present": True})
        'Yes'
        >>> render_template("{{#if present}}Yes{{/if}}", {"present": False})
        ''
        >>> render_template("{{#if present}}Yes{{#else}}No{{/if}}", {"present": False})
        'No'
    """

    def _render_block(tmpl: str, ctx: Dict[str, Any]) -> str:
        pos = 0
        output = []

        while pos < len(tmpl):
            m_triple = TRIPLE_RE.search(tmpl, pos)
            m_double = DOUBLE_RE.search(tmpl, pos)

            if not m_triple and not m_double:
                output.append(tmpl[pos:])
                break

            # triple braces are processed first: outputs raw value
            if m_triple and (not m_double or m_triple.start() < m_double.start()):
                output.append(tmpl[pos : m_triple.start()])
                expr = m_triple.group(1)
                try:
                    val = _resolve_var(expr, ctx)
                    if val is not None:
                        output.append(str(val))
                except Exception as e:
                    output.append(f"[Error: {expr} - {str(e)}]")
                pos = m_triple.end()

            # double braces: control flow, iteration, HTML-escaped output
            else:
                output.append(tmpl[pos : m_double.start()])
                tag, expr = m_double.groups()
                pos = m_double.end()

                if tag == "#if":
                    if_block, else_block, new_pos = _find_if_else_blocks(tmpl, pos)
                    try:
                        try:
                            condition_met = bool(_resolve_var(expr, ctx))
                        except Exception:
                            condition_met = False
                        if condition_met:
                            output.append(_render_block(if_block, ctx))
                        elif else_block is not None:
                            output.append(_render_block(else_block, ctx))
                    except Exception as e:
                        output.append(f"[Error evaluating if: {expr} - {str(e)}]")
                    pos = new_pos

                elif tag == "#each":
                    inner, new_pos = _find_matching_block(tmpl, pos, "#each", "/each")

                    each_match = EACH_RE.match(expr)
                    if each_match:
                        collection_expr, item_var = each_match.groups()
                        collection_expr = collection_expr.strip()
                        item_var = item_var.strip()
                    else:
                        output.append(
                            "[Error: Invalid #each syntax. Use '{#each expr as item}']"
                        )
                        pos = new_pos
                        continue

                    items = _resolve_var(collection_expr, ctx)
                    if isinstance(items, list):
                        for item in items:
                            item_ctx = ctx.copy()
                            item_ctx[item_var] = item
                            output.append(_render_block(inner, item_ctx))
                    else:
                        output.append(f"[Error: {collection_expr} is not a list]")
                    pos = new_pos

                # double braces outputs value after HTML-escaping
                elif tag is None:
                    try:
                        val = _resolve_var(expr, ctx)
                        if val is not None:
                            output.append(escape(str(val), quote=True))
                    except Exception as e:
                        output.append(f"[Error: {expr} - {str(e)}]")

        return "".join(output)

    def _find_matching_block(
        tmpl: str, start_pos: int, open_tag: str, close_tag: str
    ) -> Tuple[str, int]:
        depth = 1
        search_pos = start_pos
        while depth > 0:
            m = DOUBLE_RE.search(tmpl, search_pos)
            if not m:
                raise ValueError(f"Unclosed tag: {open_tag}")
            tag_type, _ = m.groups()
            if tag_type == open_tag:
                depth += 1
            elif tag_type == close_tag:
                depth -= 1
            search_pos = m.end()
        return tmpl[start_pos : m.start()], m.end()

    def _find_if_else_blocks(tmpl: str, start_pos: int) -> Tuple[str, str, int]:
        """Find the if and else blocks in an if statement.

        Returns:
            A tuple of (if_block, else_block, end_position) where else_block may
            be None if there is no else block.
        """
        depth = 1
        search_pos = start_pos
        else_pos = None

        while depth > 0:
            m = DOUBLE_RE.search(tmpl, search_pos)
            if not m:
                raise ValueError("Unclosed #if tag")

            tag_type, _ = m.groups()

            if tag_type == "#if":
                depth += 1
            elif tag_type == "/if":
                depth -= 1
            elif tag_type == "#else" and depth == 1:
                # only consider #else at the same depth as our starting #if
                else_pos = m.start()

            search_pos = m.end()

        end_pos = m.end()

        if else_pos is not None:
            if_block = tmpl[start_pos:else_pos]
            else_start = DOUBLE_RE.search(tmpl, else_pos).end()
            else_block = tmpl[else_start : m.start()]
            return if_block, else_block, end_pos
        else:
            return tmpl[start_pos : m.start()], None, end_pos

    return _render_block(template, context.copy())

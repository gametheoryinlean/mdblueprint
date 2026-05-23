"""Static preflight diagnostics for TeX snippets in node bodies."""
from __future__ import annotations

import re
from collections.abc import Collection

from tools.knowledge.models import Node
from tools.knowledge.validator import Diagnostic


MATH_DELIMITER_RE = re.compile(r"(?<!\\)\$\$|(?<!\\)\$|\\\(|\\\)|\\\[|\\\]")
ENVIRONMENT_RE = re.compile(r"\\(begin|end)\{([^{}]+)\}")
MACRO_RE = re.compile(r"\\([A-Za-z]+)")
KNOWN_MACROS = frozenset({
    # Greek letters (lower)
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta",
    "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi",
    "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi", "varphi",
    "chi", "psi", "omega",
    # Greek letters (upper)
    "Delta", "Gamma", "Lambda", "Omega", "Phi", "Pi", "Psi", "Sigma",
    "Theta", "Upsilon", "Xi",
    # Arrows
    "to", "mapsto", "rightarrow", "leftarrow", "leftrightarrow",
    "longrightarrow", "longleftarrow", "longleftrightarrow",
    "Rightarrow", "Leftarrow", "Leftrightarrow",
    "Longrightarrow", "Longleftarrow", "Longleftrightarrow",
    "hookrightarrow", "hookleftarrow", "rightrightarrows",
    "uparrow", "downarrow", "updownarrow",
    "Uparrow", "Downarrow", "Updownarrow",
    # Logic / set membership / order
    "exists", "forall", "nexists",
    "land", "lor", "lnot", "neg", "implies", "impliedby", "iff",
    "in", "ni", "notin", "subset", "supset", "subseteq", "supseteq",
    "subsetneq", "supsetneq", "cap", "cup",
    "le", "ge", "leq", "geq", "ll", "gg",
    "ne", "neq", "equiv", "sim", "simeq", "approx", "cong", "asymp",
    "prec", "succ", "preceq", "succeq", "mid", "nmid", "parallel",
    # Arithmetic and binary ops
    "pm", "mp", "times", "div", "cdot", "ast", "star", "circ", "bullet",
    "oplus", "ominus", "otimes", "odot", "oslash",
    "setminus", "wedge", "vee", "bigwedge", "bigvee",
    # Big operators
    "sum", "prod", "int", "iint", "iiint", "oint", "bigcap", "bigcup",
    "bigoplus", "bigotimes", "bigsqcup", "biguplus",
    "inf", "sup", "max", "min", "lim", "liminf", "limsup",
    # Sizing delimiters
    "big", "Big", "bigg", "Bigg",
    "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "Biggl", "Biggr",
    "left", "right",
    # Brackets and dots
    "langle", "rangle", "lceil", "rceil", "lfloor", "rfloor",
    "vert", "Vert",
    "ldots", "cdots", "vdots", "ddots", "dots",
    # Named operators
    "arg", "log", "ln", "exp", "det", "dim", "ker", "deg",
    "sin", "cos", "tan", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "cot", "csc", "sec",
    "operatorname",
    # Fonts and styling
    "mathbb", "mathbf", "mathcal", "mathrm", "mathit", "mathsf", "mathtt",
    "boldsymbol", "text", "textbf", "textit", "textsf", "texttt",
    # Accents and decorations
    "bar", "overline", "underline", "widetilde", "widehat",
    "hat", "tilde", "dot", "ddot", "vec",
    "overbrace", "underbrace", "overrightarrow", "overleftarrow",
    # Symbols
    "infty", "emptyset", "varnothing", "nabla", "partial",
    "ell", "hbar", "imath", "jmath", "Re", "Im", "wp",
    "top", "bot", "perp", "angle", "square",
    "aleph", "beth",
    "prime", "dagger", "ddagger",
    "spadesuit", "heartsuit", "diamondsuit", "clubsuit",
    # Numerics and spacing
    "frac", "binom", "tfrac", "dfrac", "tbinom", "dbinom",
    "sqrt", "colon",
    "qquad", "quad",
    # Math environments
    "begin", "end",
})


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def check_node_math(node: Node, *, declared_macros: Collection[str] | None = None) -> list[Diagnostic]:
    """Return syntax-level TeX diagnostics for a parsed knowledge node."""
    diags: list[Diagnostic] = []
    stack: list[tuple[str, int]] = []
    declared = {macro.lstrip("\\") for macro in declared_macros or ()}

    def err(message: str) -> None:
        diags.append(Diagnostic("error", node.id, message, node.file_path))

    def warn(message: str) -> None:
        diags.append(Diagnostic("warning", node.id, message, node.file_path))

    for match in MATH_DELIMITER_RE.finditer(node.body):
        token = match.group(0)
        line = _line_number(node.body, match.start())

        if token in {"$", "$$", r"\(", r"\["}:
            if stack and stack[-1][0] == token and token in {"$", "$$"}:
                stack.pop()
            else:
                stack.append((token, line))
            continue

        expected = {r"\)": r"\(", r"\]": r"\["}[token]
        if stack and stack[-1][0] == expected:
            stack.pop()
        else:
            err(f"line {line}: unmatched closing math delimiter {token!r}")

    for token, line in stack:
        err(f"line {line}: unmatched math delimiter {token!r}")

    env_stack: list[tuple[str, int]] = []
    for match in ENVIRONMENT_RE.finditer(node.body):
        kind = match.group(1)
        env = match.group(2)
        line = _line_number(node.body, match.start())
        if kind == "begin":
            env_stack.append((env, line))
            continue

        if not env_stack:
            err(f"line {line}: unmatched \\end{{{env}}}")
            continue

        open_env, open_line = env_stack.pop()
        if open_env != env:
            err(
                f"line {line}: mismatched environment \\begin{{{open_env}}} "
                f"from line {open_line} closed by \\end{{{env}}}"
            )

    for env, line in env_stack:
        err(f"line {line}: unmatched \\begin{{{env}}}")

    for line_number, line in enumerate(node.body.splitlines(), start=1):
        if "|" in line and (r"\[" in line or "$$" in line or r"\begin{" in line):
            warn(f"line {line_number}: display math inside a Markdown table cell may render poorly")

    for match in MACRO_RE.finditer(node.body):
        name = match.group(1)
        if name in KNOWN_MACROS or name in declared:
            continue
        line = _line_number(node.body, match.start())
        err(f"line {line}: unknown macro \\{name}; declare it in math.macros")

    return diags

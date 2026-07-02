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
    # ---- Greek letters (lower case + variants) ----
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta",
    "theta", "vartheta", "iota", "kappa", "varkappa", "lambda", "mu", "nu",
    "xi", "omicron", "pi", "varpi", "rho", "varrho", "sigma", "varsigma",
    "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega", "digamma",
    # ---- Greek letters (upper case) ----
    "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
    "Iota", "Kappa", "Lambda", "Mu", "Nu", "Xi", "Omicron", "Pi", "Rho",
    "Sigma", "Tau", "Upsilon", "Phi", "Chi", "Psi", "Omega",
    # ---- Hebrew / other letters ----
    "aleph", "beth", "daleth", "gimel",
    "hbar", "hslash", "imath", "jmath", "ell", "wp", "eth", "mho",
    "Re", "Im", "partial", "nabla",
    # ---- Arrows ----
    "to", "gets", "mapsto", "longmapsto",
    "rightarrow", "leftarrow", "leftrightarrow",
    "longrightarrow", "longleftarrow", "longleftrightarrow",
    "Rightarrow", "Leftarrow", "Leftrightarrow",
    "Longrightarrow", "Longleftarrow", "Longleftrightarrow",
    "hookrightarrow", "hookleftarrow",
    "rightleftarrows", "leftrightarrows", "rightrightarrows", "leftleftarrows",
    "rightleftharpoons", "leftrightharpoons",
    "twoheadrightarrow", "twoheadleftarrow",
    "uparrow", "downarrow", "updownarrow",
    "Uparrow", "Downarrow", "Updownarrow",
    "nearrow", "searrow", "swarrow", "nwarrow",
    "rightharpoonup", "rightharpoondown", "leftharpoonup", "leftharpoondown",
    "upharpoonleft", "upharpoonright", "downharpoonleft", "downharpoonright",
    "circlearrowleft", "circlearrowright", "curvearrowleft", "curvearrowright",
    "Lleftarrow", "Rrightarrow",
    # ---- Extensible arrows (AMS/KaTeX) — take an optional [subscript] and
    # a mandatory {superscript} that render above/below the arrow.  These
    # MUST NOT be aliased to the non-extensible variants (\rightarrow etc.)
    # in user macros, because that strips the argument.
    "xleftarrow", "xrightarrow", "xLeftarrow", "xRightarrow",
    "xleftrightarrow", "xLeftrightarrow",
    "xhookleftarrow", "xhookrightarrow",
    "xtwoheadleftarrow", "xtwoheadrightarrow",
    "xleftharpoonup", "xrightharpoonup",
    "xleftharpoondown", "xrightharpoondown",
    "xleftrightharpoons", "xrightleftharpoons",
    "xleftrightarrows", "xrightleftarrows",
    "xmapsto", "xlongequal",
    # ---- Logic / set membership / order ----
    "exists", "forall", "nexists",
    "land", "lor", "lnot", "neg",
    "implies", "impliedby", "iff",
    "in", "ni", "notin", "owns",
    "subset", "supset", "subseteq", "supseteq",
    "sqsubset", "sqsupset", "sqsubseteq", "sqsupseteq",
    "subsetneq", "supsetneq", "subsetneqq", "supsetneqq",
    "varsubsetneq", "varsupsetneq", "varsubsetneqq", "varsupsetneqq",
    "cap", "cup", "sqcup", "sqcap", "uplus",
    "lt", "gt", "le", "ge", "leq", "geq", "ll", "gg", "lll", "ggg",
    "leqq", "geqq", "leqslant", "geqslant", "lessgtr", "gtrless",
    "ne", "neq",
    "equiv", "sim", "simeq", "approx", "cong", "propto",
    "asymp", "doteq", "fallingdotseq", "risingdotseq",
    "prec", "succ", "preceq", "succeq",
    "precsim", "succsim", "precapprox", "succapprox",
    "mid", "nmid", "parallel", "nparallel", "perp",
    "vdash", "dashv", "models", "vDash", "Vdash",
    "bowtie", "frown", "smile", "smallfrown", "smallsmile",
    # ---- Arithmetic and binary ops ----
    "pm", "mp", "times", "div", "cdot", "ast", "star", "circ", "bullet",
    "oplus", "ominus", "otimes", "odot", "oslash", "ocirc",
    "amalg", "wr", "dagger", "ddagger",
    "vee", "wedge", "veebar", "barwedge", "doublebarwedge", "curlyvee", "curlywedge",
    "setminus", "smallsetminus", "backslash", "slash",
    # ---- Triangles, suits, geometric symbols ----
    "triangle", "triangledown", "triangleleft", "triangleright",
    "blacktriangle", "blacktriangledown", "blacktriangleleft", "blacktriangleright",
    "diamond", "Diamond", "lozenge", "blacklozenge",
    "square", "blacksquare",
    "circ", "bigcirc", "circledast", "circledcirc", "circleddash",
    "diamondsuit", "heartsuit", "clubsuit", "spadesuit",
    "flat", "natural", "sharp",
    "checkmark", "maltese",
    "ltimes", "rtimes", "leftthreetimes", "rightthreetimes",
    # ---- Big operators ----
    "sum", "prod", "coprod",
    "int", "iint", "iiint", "iiiint", "oint", "oiint", "oiiint",
    "bigcap", "bigcup", "bigsqcup", "biguplus",
    "bigvee", "bigwedge", "bigodot", "bigoplus", "bigotimes",
    "inf", "sup", "max", "min", "lim", "liminf", "limsup",
    "varinjlim", "varprojlim", "varliminf", "varlimsup",
    "injlim", "projlim",
    # ---- Sizing delimiters ----
    "big", "Big", "bigg", "Bigg",
    "bigl", "bigr", "Bigl", "Bigr",
    "biggl", "biggr", "Biggl", "Biggr",
    "left", "right", "middle",
    # ---- Brackets and dots ----
    "langle", "rangle", "lceil", "rceil", "lfloor", "rfloor",
    "lvert", "rvert", "lVert", "rVert", "vert", "Vert",
    "lbrace", "rbrace", "lbrack", "rbrack",
    "ulcorner", "urcorner", "llcorner", "lrcorner",
    "ldots", "cdots", "vdots", "ddots", "dots", "dotsb", "dotsc", "dotsi", "dotsm", "dotso",
    # ---- Named operators (KaTeX built-ins) ----
    "arg", "log", "ln", "lg", "exp", "det", "dim", "ker", "deg", "hom",
    "gcd", "Pr", "sin", "cos", "tan", "cot", "csc", "sec",
    "arcsin", "arccos", "arctan", "arccot",
    "sinh", "cosh", "tanh", "coth",
    "operatorname", "operatornamewithlimits",
    # ---- Fonts, styles, sizes ----
    "mathbb", "mathbf", "mathcal", "mathfrak", "mathit", "mathnormal",
    "mathrm", "mathsf", "mathtt", "mathscr",
    "bold", "boldsymbol", "pmb",
    "rm", "bf", "it", "sf", "tt", "cal",
    "text", "textbf", "textit", "textmd", "textnormal", "textrm",
    "textsf", "textsl", "textsc", "texttt", "textup", "emph",
    "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle",
    "tiny", "scriptsize", "footnotesize", "small", "normalsize",
    "large", "Large", "LARGE", "huge", "Huge",
    "color", "textcolor", "colorbox", "fcolorbox",
    # ---- Accents and decorations ----
    "hat", "widehat", "tilde", "widetilde", "bar", "overline", "underline",
    "vec", "overrightarrow", "overleftarrow", "overleftrightarrow",
    "underrightarrow", "underleftarrow", "underleftrightarrow",
    "check", "breve", "acute", "grave", "dot", "ddot", "dddot", "ddddot",
    "mathring", "overarc",
    "overbrace", "underbrace", "overgroup", "undergroup",
    "overlinesegment", "underlinesegment",
    "boxed", "fbox", "framebox",
    # ---- Symbols ----
    "infty", "emptyset", "varnothing",
    "top", "bot", "angle", "measuredangle", "sphericalangle",
    "prime", "backprime",
    "surd", "S",
    "complement", "smallint", "Bumpeq", "bumpeq",
    "between", "pitchfork",
    "Finv", "Game", "Bbbk",
    "yen", "pounds", "$",
    # ---- Fractions, roots, binomials ----
    "frac", "dfrac", "tfrac", "cfrac",
    "binom", "dbinom", "tbinom",
    "choose", "brace", "brack", "atop", "above", "abovewithdelims",
    "sqrt",
    # ---- Spacing ----
    "qquad", "quad", "enspace", "thinspace", "medspace", "thickspace",
    "negthinspace", "negmedspace", "negthickspace",
    "allowbreak", "nobreakspace", "space",
    "phantom", "hphantom", "vphantom", "smash",
    # ---- Modular / number theory ----
    "pmod", "mod", "bmod", "pod",
    # ---- Punctuation / misc ----
    "colon", "vcentcolon", "ratio",
    # ---- LaTeX environments / macros allowed in body ----
    "begin", "end",
    # ---- Math layout / matrix helpers ----
    "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix",
    "smallmatrix", "array",
    "cases", "rcases", "drcases",
    "aligned", "alignedat", "gathered", "split",
    "stackrel", "overset", "underset", "raisebox",
    # ---- Equation tagging / labeling (silently allowed) ----
    "label", "ref", "eqref", "tag", "notag", "nonumber",
    # ---- Misc helpers in KaTeX ----
    "limits", "nolimits", "substack", "genfrac",
    "char", "not",
    # ---- Backslash-style line break inside math (rare but supported) ----
    # Note: "\\" itself is a row break in environments; not a name macro.
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

    # Detect display math inside actual Markdown table cells (rows like
    # `| ... $$ ... $$ ... |`). Previous check was over-eager: any line with
    # `|` anywhere (e.g. `\phi_E|_{K_{x,+}}`) plus a `$$` anywhere would
    # trigger, even when both were in body prose outside any table.
    body_lines = node.body.splitlines()
    for line_number, line in enumerate(body_lines, start=1):
        stripped = line.lstrip()
        # A markdown table row starts with `|` (after optional indentation)
        # and ends with `|`. We require both to consider it an actual table row.
        if not (stripped.startswith("|") and stripped.rstrip().endswith("|")):
            continue
        # Inside such a row, display math `$$...$$` or `\[...\]` or
        # `\begin{...}` does render poorly.
        if r"\[" in line or "$$" in line or r"\begin{" in line:
            warn(f"line {line_number}: display math inside a Markdown table cell may render poorly")

    for match in MACRO_RE.finditer(node.body):
        name = match.group(1)
        if name in KNOWN_MACROS or name in declared:
            continue
        line = _line_number(node.body, match.start())
        err(f"line {line}: unknown macro \\{name}; declare it in math.macros")

    return diags

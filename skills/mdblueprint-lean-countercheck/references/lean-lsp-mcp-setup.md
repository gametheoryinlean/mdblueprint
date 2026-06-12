# lean-lsp-mcp Setup

Use this before attempting `lean-lsp-mcp` experiments.

1. Install `uv` on the machine.
2. Run `lake build` in the Lean project root so the language server starts from a warm build.
3. Start the server with `uvx lean-lsp-mcp`.
4. For Claude Code, register it from the Lean project root with:
   `claude mcp add lean-lsp uvx lean-lsp-mcp`
5. If you prefer Nix, install or run the package from the upstream repo instead.
6. Install `ripgrep` (`rg`) if local search support is needed.

Treat the server as optional and verify that it is actually available before the
experiment.

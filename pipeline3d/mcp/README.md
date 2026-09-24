# MCP configs

* `claude_desktop_config.json`: Claude Desktop (Settings → Developer → Edit Config). Merge the
  `mcpServers` entries into your existing file.
* `mcp.json`: Claude Code. Save it as `.mcp.json` in your game project root.

Until the blender-mcp pipeline branch is merged, pin it:
`"args": ["--from", "git+https://github.com/sphilius/blender-mcp@claude/blender-godot-3d-pipeline-jwrf86", "blender-mcp"]`.

Leave unused API keys empty; the tools report a clear error if a key is missing.
Run only one Blender MCP client at a time (Desktop or Code, not both).
On macOS/Linux use forward-slash paths like `/Users/<you>/...`.
Setup steps and prompts are in [`../docs/mcp-playbook.md`](../docs/mcp-playbook.md).

# Portable Agent Plugins migration

This repository currently uses the supported Codex compatibility manifest at `.codex-plugin/plugin.json`, matching the established plugin baseline used across this organisation.

The portable root `plugin.json` and `mcp.json` remain intentionally inactive. Add them only when the implementation can keep portable and compatibility metadata synchronized and can declare every transport, authentication, Skill, asset, and lifecycle behavior truthfully.

This decision matters more than usual here. Agent Plugins 1.0 does not expand environment variables inside a remote MCP URL or header, and it defines no portable credential-reference field. This plugin also has no MCP server: image generation is performed by Codex through its own tool, so there is no transport, endpoint, or server-side credential to declare in a portable manifest.

Migration acceptance requires schema validation, parity tests between both manifests, a fresh local installation, and confirmation that plugin identity remains `codex-image-factory`.

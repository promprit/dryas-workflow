# Ruflo tool names (consumed by the orchestrate skill)

Source: ruflo-core 0.2.6 plugin MCP (`ruflo-core/.mcp.json`, server key `ruflo`), Ruflo CLI 3.51.0.
In a session the tools are `mcp__plugin_ruflo-core_ruflo__<tool>` (use `ToolSearch("memory_search")` to load). The upstream docs call the server `claude-flow`; with the plugin install the prefix is the one above.

memory_search: memory_search (MCP server claude-flow, from ruflo-core; full name mcp__plugin_ruflo-core_ruflo__memory_search)
memory_store: memory_store (full name mcp__plugin_ruflo-core_ruflo__memory_store)
swarm_init: swarm_init (full name mcp__plugin_ruflo-core_ruflo__swarm_init; ALWAYS pass topology: "hierarchical", the tool default is hierarchical-mesh and nothing in env/config overrides it)
cost_report: (disabled — ruflo-cost-tracker plugin is off; use Claude usage /cost and `tune.py report` jev_spend_usd)
namespace rule: project folder name (basename of the project root, for example `my-app`; pass as the `namespace` argument of memory_store and memory_search)

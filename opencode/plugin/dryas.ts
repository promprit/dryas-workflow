// Dryas Workflow for OpenCode: maps OpenCode plugin hooks onto the Dryas hook chain (dryas/jev/chain.py).
// The chain decides; this file only translates. Spec: docs/specs/2026-10-15-opencode-edition-design.md section 5.
import { spawn } from "node:child_process"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "dryas")
const PRETOOL_MS = 20000
const PROMPT_MS = 15000
const RULES_MS = 5000
const GATED_KEYS = ["edit", "bash"] // permission keys Dryas turns from "allow" into "ask" and answers itself

function installRecord(): Record<string, any> {
  try {
    return JSON.parse(readFileSync(join(ROOT, "install.json"), "utf8"))
  } catch {
    return {}
  }
}

const PY: string = process.env.DRYAS_PY || installRecord().py || (process.platform === "win32" ? "python" : "python3")

// Runs one Dryas script with `input` as JSON on stdin; resolves to its stdout, or "" on any failure or timeout.
function runScript(script: string, args: string[], input: unknown, timeoutMs: number): Promise<string> {
  return new Promise((resolve) => {
    let out = ""
    let settled = false
    const finish = (v: string) => {
      if (!settled) {
        settled = true
        clearTimeout(timer)
        resolve(v)
      }
    }
    const child = spawn(PY, ["-X", "utf8", join(ROOT, "jev", script), ...args], { stdio: ["pipe", "pipe", "ignore"] })
    const timer = setTimeout(() => {
      child.kill()
      finish("")
    }, timeoutMs)
    child.stdout.on("data", (d) => (out += d))
    child.on("error", () => finish(""))
    child.on("close", () => finish(out))
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(input))
  })
}

function parse(out: string): any {
  try {
    return JSON.parse(out)
  } catch {
    return null
  }
}

// OpenCode tool call -> Claude-shaped tool_name and tool_input; null for tools the chain does not judge.
function toolEvent(tool: string, args: any): { tool_name: string; tool_input: Record<string, unknown> } | null {
  const a = args ?? {}
  switch (tool) {
    case "bash":
      return { tool_name: "Bash", tool_input: { command: String(a.command ?? ""), description: a.description } }
    case "write":
      return { tool_name: "Write", tool_input: { file_path: a.filePath, content: String(a.content ?? "") } }
    case "edit":
      return { tool_name: "Edit", tool_input: { file_path: a.filePath, old_string: String(a.oldString ?? ""), new_string: String(a.newString ?? "") } }
    case "multiedit":
      return {
        tool_name: "MultiEdit",
        tool_input: {
          file_path: a.filePath,
          edits: (Array.isArray(a.edits) ? a.edits : []).map((e: any) => ({ old_string: String(e?.oldString ?? ""), new_string: String(e?.newString ?? "") })),
        },
      }
    case "patch":
    case "apply_patch":
      return { tool_name: "apply_patch", tool_input: { command: String(a.patchText ?? a.patch ?? "") } }
  }
  return null
}

function hasAsk(v: unknown): boolean {
  if (v === "ask") return true
  return !!v && typeof v === "object" && Object.values(v as object).some((x) => x === "ask")
}

function toAsk(v: unknown): unknown {
  if (v === undefined || v === "allow") return "ask"
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v as object).map(([k, x]) => [k, x === "allow" ? "ask" : x]))
  return v
}

// Mutates `perm`; returns the keys whose prompts the shim may answer (the user set no "ask" there).
function gatePermissions(perm: Record<string, unknown>): string[] {
  const answerable: string[] = []
  for (const k of GATED_KEYS) {
    if (!hasAsk(perm[k])) answerable.push(k)
    perm[k] = toAsk(perm[k])
  }
  return answerable
}

type Session = { agent?: string; parentID?: string }

export const DryasPlugin = async (ctx: any) => {
  const sessions = new Map<string, Session>()
  const decisions = new Map<string, "allow" | "ask">() // tool callID -> the chain's answer
  const answerable = new Map<string, Set<string>>() // agent name ("" = global config) -> keys the shim may answer
  let rules: string | null = null

  const session = (id: string): Session => {
    let s = sessions.get(id)
    if (!s) sessions.set(id, (s = {}))
    return s
  }
  const base = (sessionID: string) => {
    const s = session(sessionID)
    const ev: Record<string, unknown> = { session_id: sessionID, cwd: ctx.directory }
    if (s.parentID) {
      ev.agent_id = sessionID
      ev.agent_type = s.agent ?? ""
    }
    return ev
  }

  return {
    config: async (cfg: any) => {
      cfg.mcp = cfg.mcp ?? {}
      cfg.mcp.jev = {
        type: "local",
        command: [PY, "-X", "utf8", join(ROOT, "jev", "jev_mcp.py")],
        enabled: true,
        environment: Object.fromEntries(
          ["OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "DRYAS_DATA_ROOT"].filter((k) => process.env[k]).map((k) => [k, process.env[k] as string]),
        ),
      }
      if (typeof cfg.permission !== "string") {
        cfg.permission = cfg.permission ?? {}
        answerable.set("", new Set(gatePermissions(cfg.permission)))
      }
      for (const [name, agent] of Object.entries<any>(cfg.agent ?? {})) {
        if (agent && typeof agent.permission === "object") answerable.set(name, new Set(gatePermissions(agent.permission)))
      }
    },

    event: async ({ event }: any) => {
      const p = event?.properties ?? {}
      if (event?.type === "session.created" && p.info?.id) {
        session(p.info.id).parentID = p.info.parentID
      } else if (event?.type === "permission.asked") {
        const callID = p.tool?.callID ?? p.callID
        const keys = answerable.get(session(p.sessionID).agent ?? "") ?? answerable.get("")
        if (callID && decisions.get(callID) === "allow" && keys?.has(p.permission)) {
          await ctx.client
            .postSessionIdPermissionsPermissionId({ path: { id: p.sessionID, permissionID: p.id }, body: { response: "once" } })
            .catch(() => {})
        }
      }
    },

    "chat.params": async (input: any) => {
      if (input?.sessionID && input.agent && input.agent !== "title") session(input.sessionID).agent = input.agent
    },

    "tool.execute.before": async (input: any, output: any) => {
      const te = toolEvent(input.tool, output.args)
      if (!te) return
      const ev = { ...base(input.sessionID), hook_event_name: "PreToolUse", ...te }
      const out = parse(await runScript("chain.py", ["pretool", "--harness", "opencode"], ev, PRETOOL_MS))
      const hso = out?.hookSpecificOutput ?? {}
      if (hso.permissionDecision === "deny") throw new Error(String(hso.permissionDecisionReason || "denied by Dryas"))
      decisions.set(input.callID, hso.permissionDecision === "ask" ? "ask" : "allow")
    },

    "chat.message": async (input: any, output: any) => {
      const parts: any[] = output?.parts ?? []
      const prompt = parts.filter((p) => p?.type === "text" && !p.synthetic).map((p) => p.text).join("\n")
      const ev = { ...base(input.sessionID), hook_event_name: "UserPromptSubmit", prompt }
      const out = parse(await runScript("chain.py", ["prompt", "--harness", "opencode"], ev, PROMPT_MS))
      if (out?.decision === "block") {
        const text = `Dryas blocked this prompt: ${out.reason}. Tell the user this reason and do nothing else.`
        for (const p of parts) if (p?.type === "text") p.text = text
        return
      }
      const add = out?.hookSpecificOutput?.additionalContext
      if (add) parts.push({ id: `prt_dryas${Date.now()}`, sessionID: input.sessionID, messageID: output.message?.id, type: "text", text: String(add), synthetic: true })
    },

    "experimental.chat.system.transform": async (_input: any, output: any) => {
      if (rules === null) {
        const out = parse(await runScript("rules_inject.py", ["--harness", "opencode"], {}, RULES_MS))
        rules = String(out?.hookSpecificOutput?.additionalContext ?? "")
      }
      if (rules) output.system.push(rules)
    },
  }
}

import { spawn } from "node:child_process"
import { createHash } from "node:crypto"
import { existsSync, readFileSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "dryas")
const PRETOOL_MS = 20000
const PROMPT_MS = 15000
const RULES_MS = 5000
let partSeq = 0
const APPROVE = /\bdryas allow ([0-9a-f]{4})\b/gi

function installRecord(): Record<string, any> {
  try {
    return JSON.parse(readFileSync(join(ROOT, "install.json"), "utf8"))
  } catch {
    return {}
  }
}

const PY: string = process.env.DRYAS_PY || installRecord().py || (process.platform === "win32" ? "python" : "python3")

function runScript(script: string, args: string[], input: unknown, timeoutMs: number): Promise<string | null> {
  return new Promise((resolve) => {
    let out = ""
    let settled = false
    const finish = (v: string | null) => {
      if (!settled) {
        settled = true
        clearTimeout(timer)
        resolve(v)
      }
    }
    const child = spawn(PY, ["-B", "-X", "utf8", join(ROOT, "jev", script), ...args], { stdio: ["pipe", "pipe", "ignore"] })
    const timer = setTimeout(() => {
      child.kill()
      finish(null)
    }, timeoutMs)
    child.stdout.setEncoding("utf8")
    child.stdout.on("data", (d) => (out += d))
    child.on("error", () => finish(null))
    child.on("close", (code) => finish(code === 0 ? out : null))
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(input))
  })
}

function parse(out: string | null): any {
  try {
    return JSON.parse(out ?? "")
  } catch {
    return null
  }
}

function toolEvent(tool: string, args: any): { tool_name: string; tool_input: Record<string, unknown> } | null {
  const a = args ?? {}
  switch (tool) {
    case "bash":
      return { tool_name: "Bash", tool_input: { command: String(a.command ?? ""), description: a.description } }
    case "write":
      return { tool_name: "Write", tool_input: { file_path: a.filePath, content: String(a.content ?? "") } }
    case "edit":
      return { tool_name: "Edit", tool_input: { file_path: a.filePath, old_string: String(a.oldString ?? ""), new_string: String(a.newString ?? "") } }
    case "apply_patch":
      return { tool_name: "apply_patch", tool_input: { command: String(a.patchText ?? a.patch ?? "") } }
  }
  return null
}

function approvalCode(tool: string, args: unknown): string {
  return createHash("sha1").update(tool + "\n" + JSON.stringify(args)).digest("hex").slice(0, 4)
}

// Mirrors scope_lock.find_root / task_active.
function taskActive(dir: string): boolean {
  for (let d = resolve(dir); ; d = dirname(d)) {
    if (existsSync(join(d, ".orchestrate", "active.json"))) return true
    if (dirname(d) === d) return false
  }
}

type Session = { agent?: string; parentID?: string; known?: boolean }

export const DryasPlugin = async (ctx: any) => {
  const sessions = new Map<string, Session>()
  const approved = new Set<string>()
  let rules: string | null = null

  const session = (id: string): Session => {
    let s = sessions.get(id)
    if (!s) sessions.set(id, (s = {}))
    return s
  }
  const resolveSession = async (id: string): Promise<Session> => {
    const s = session(id)
    if (!s.known) {
      try {
        s.parentID = (await ctx.client.session.get({ path: { id } }))?.data?.parentID
        s.known = true
      } catch {}
    }
    return s
  }
  const base = (sessionID: string, cwd: string = ctx.directory) => {
    const s = session(sessionID)
    const ev: Record<string, unknown> = { session_id: sessionID, cwd }
    if (s.parentID) {
      ev.agent_id = sessionID
      ev.agent_type = s.agent ?? ""
    }
    return ev
  }

  return {
    config: async (cfg: any) => {
      cfg.mcp = cfg.mcp ?? {}
      if (cfg.mcp.jev) return
      cfg.mcp.jev = {
        type: "local",
        command: [PY, "-B", "-X", "utf8", join(ROOT, "jev", "jev_mcp.py")],
        enabled: true,
        environment: Object.fromEntries(
          ["OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "DRYAS_DATA_ROOT"].filter((k) => process.env[k]).map((k) => [k, process.env[k] as string]),
        ),
      }
    },

    event: async ({ event }: any) => {
      const p = event?.properties ?? {}
      if (event?.type === "session.created" && p.info?.id) {
        const s = session(p.info.id)
        s.parentID = p.info.parentID
        s.known = true
      } else if (event?.type === "session.deleted" && p.info?.id) {
        sessions.delete(p.info.id)
      }
    },

    "chat.params": async (input: any) => {
      if (input?.sessionID && input.agent && input.agent !== "title") session(input.sessionID).agent = input.agent
    },

    "tool.execute.before": async (input: any, output: any) => {
      const te = toolEvent(input.tool, output.args)
      if (!te) return
      const wd = output.args?.workdir
      const cwd = input.tool === "bash" && typeof wd === "string" && wd ? resolve(ctx.directory, wd) : ctx.directory
      if (!(await resolveSession(input.sessionID)).known && taskActive(cwd)) {
        throw new Error("Dryas could not tell whether this session is a subagent while a task is active; retry")
      }
      const ev = { ...base(input.sessionID, cwd), hook_event_name: "PreToolUse", ...te }
      const raw = await runScript("chain.py", ["pretool", "--harness", "opencode"], ev, PRETOOL_MS)
      const out = parse(raw)
      if ((raw === null || (raw.trim() && out === null)) && taskActive(cwd)) {
        throw new Error(`Dryas could not run its checks (python: ${PY}) while a task is active; fix Python or re-run install.sh --harness opencode`)
      }
      const hso = out?.hookSpecificOutput ?? {}
      const reason = String(hso.permissionDecisionReason || "flagged by Dryas")
      if (hso.permissionDecision === "deny") throw new Error(reason)
      if (hso.permissionDecision === "ask") {
        const code = approvalCode(input.tool, output.args)
        if (approved.delete(code)) return
        throw new Error(
          `Dryas needs the user's approval: ${reason}. Tell the user this reason and stop. To allow this exact call once, the user replies: dryas allow ${code}`,
        )
      }
    },

    "chat.message": async (input: any, output: any) => {
      const parts: any[] = output?.parts ?? []
      const prompt = parts.filter((p) => p?.type === "text" && !p.synthetic).map((p) => p.text).join("\n")
      if (!(await resolveSession(input.sessionID)).parentID) {
        const codes = [...prompt.matchAll(APPROVE)]
        if (codes.length) for (const m of codes) approved.add(m[1].toLowerCase())
        else approved.clear()
      }
      const ev = { ...base(input.sessionID), hook_event_name: "UserPromptSubmit", prompt }
      const out = parse(await runScript("chain.py", ["prompt", "--harness", "opencode"], ev, PROMPT_MS))
      if (out?.decision === "block") {
        const text = `Dryas blocked this prompt: ${out.reason}. Tell the user this reason and do nothing else.`
        for (const p of parts) if (p?.type === "text") p.text = text
        return
      }
      const add = out?.hookSpecificOutput?.additionalContext
      if (add) parts.push({ id: `prt_dryas${Date.now()}_${++partSeq}`, sessionID: input.sessionID, messageID: output.message?.id, type: "text", text: String(add), synthetic: true })
    },

    "experimental.chat.system.transform": async (_input: any, output: any) => {
      if (rules === null) {
        const out = parse(await runScript("rules_inject.py", ["--harness", "opencode"], {}, RULES_MS))
        const text = String(out?.hookSpecificOutput?.additionalContext ?? "")
        if (text) rules = text
      }
      if (rules) output.system.push(rules)
    },
  }
}

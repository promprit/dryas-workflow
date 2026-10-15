import { spawn } from "node:child_process"
import { createHash } from "node:crypto"
import { existsSync, readFileSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "dryas")
const PRETOOL_MS = 20000
const PROMPT_MS = 15000
const RULES_MS = 5000
const OBSERVE_MS = 10000
const END_MS = 3000
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

type Usage = { input_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }
type Session = { agent?: string; parentID?: string; known?: boolean; contextLimit?: number; usage?: Usage; model?: string; ended?: boolean }

function toolCwd(dir: string, tool: string, args: any): string {
  const wd = args?.workdir
  return tool === "bash" && typeof wd === "string" && wd ? resolve(dir, wd) : dir
}

export const DryasPlugin = async (ctx: any) => {
  const sessions = new Map<string, Session>()
  const approved = new Set<string>()
  const blocked = new Set<string>() // call IDs the shim blocked
  const seen = new Set<string>() // failure events already sent
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

  // Observe-only chain call: started, never awaited by a hook, never blocks or changes the session.
  const observe = (kind: string, ev: Record<string, unknown>, ms: number = OBSERVE_MS) =>
    runScript("chain.py", [kind, "--harness", "opencode"], ev, ms)
  const sessionMessages = async (id: string): Promise<any[]> => {
    try {
      return (await ctx.client.session.messages({ path: { id } }))?.data ?? []
    } catch {
      return []
    }
  }
  const end = (id: string, reason: string, ms?: number) => {
    const s = sessions.get(id)
    if (!s?.known || s.parentID || s.ended) return Promise.resolve(null)
    s.ended = true
    return observe("session-end", { ...base(id), hook_event_name: "SessionEnd", reason }, ms)
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
      const type = event?.type
      if (type === "session.created" && p.info?.id) {
        const s = session(p.info.id)
        s.parentID = p.info.parentID
        s.known = true
        if (!s.parentID) void observe("session-start", { ...base(p.info.id), hook_event_name: "SessionStart", source: "startup" })
      } else if (type === "session.deleted" && p.info?.id) {
        await end(p.info.id, "deleted")
        sessions.delete(p.info.id)
      } else if (type === "session.idle" && p.sessionID) {
        const s = await resolveSession(p.sessionID)
        const sub = !!s.parentID
        void observe(sub ? "subagent-stop" : "stop", { ...base(p.sessionID), hook_event_name: sub ? "SubagentStop" : "Stop" })
      } else if (type === "message.updated" && p.info?.role === "assistant" && p.info.tokens) {
        const t = p.info.tokens
        const u = { input_tokens: t.input ?? 0, cache_read_input_tokens: t.cache?.read ?? 0, cache_creation_input_tokens: t.cache?.write ?? 0 }
        if (u.input_tokens + u.cache_read_input_tokens + u.cache_creation_input_tokens > 0) {
          const s = session(p.info.sessionID)
          s.usage = u
          s.model = String(p.info.modelID ?? "")
        }
      } else if (type === "message.part.updated" && p.part?.type === "tool" && p.part.state?.status === "error") {
        const part = p.part
        if (seen.has(part.callID)) return
        if (seen.size > 5000) seen.clear()
        seen.add(part.callID)
        if (blocked.delete(part.callID)) return // the shim blocked it: Claude Code sends no failure event for a hook deny
        const te = toolEvent(part.tool, part.state.input)
        if (te)
          void observe("post", {
            ...base(part.sessionID, toolCwd(ctx.directory, part.tool, part.state.input)),
            hook_event_name: "PostToolUseFailure", ...te, tool_use_id: part.callID, error: String(part.state.error ?? ""),
          })
      }
    },

    "chat.params": async (input: any) => {
      if (input?.sessionID && input.agent && input.agent !== "title") session(input.sessionID).agent = input.agent
      const lim = input?.model?.limit?.context
      if (input?.sessionID && typeof lim === "number" && lim > 0) session(input.sessionID).contextLimit = lim
    },

    "tool.execute.before": async (input: any, output: any) => {
      const te = toolEvent(input.tool, output.args)
      if (!te) return
      const cwd = toolCwd(ctx.directory, input.tool, output.args)
      if (blocked.size > 5000) blocked.clear()
      if (!(await resolveSession(input.sessionID)).known && taskActive(cwd)) {
        blocked.add(input.callID)
        throw new Error("Dryas could not tell whether this session is a subagent while a task is active; retry")
      }
      const ev = { ...base(input.sessionID, cwd), hook_event_name: "PreToolUse", ...te, tool_use_id: input.callID }
      const raw = await runScript("chain.py", ["pretool", "--harness", "opencode"], ev, PRETOOL_MS)
      const out = parse(raw)
      if ((raw === null || (raw.trim() && out === null)) && taskActive(cwd)) {
        blocked.add(input.callID)
        throw new Error(`Dryas could not run its checks (python: ${PY}) while a task is active; fix Python or re-run install.sh --harness opencode`)
      }
      const hso = out?.hookSpecificOutput ?? {}
      const reason = String(hso.permissionDecisionReason || "flagged by Dryas")
      if (hso.permissionDecision === "deny") {
        blocked.add(input.callID)
        throw new Error(reason)
      }
      if (hso.permissionDecision === "ask") {
        const code = approvalCode(input.tool, output.args)
        if (approved.delete(code)) return
        blocked.add(input.callID)
        throw new Error(
          `Dryas needs the user's approval: ${reason}. Tell the user this reason and stop. To allow this exact call once, the user replies: dryas allow ${code}`,
        )
      }
    },

    "tool.execute.after": async (input: any, output: any) => {
      const te = toolEvent(input.tool, input.args)
      if (!te) return
      void observe("post", {
        ...base(input.sessionID, toolCwd(ctx.directory, input.tool, input.args)), hook_event_name: "PostToolUse", ...te,
        tool_use_id: input.callID, tool_response: { output: String(output?.output ?? "").slice(0, 2000) },
      })
    },

    "chat.message": async (input: any, output: any) => {
      const parts: any[] = output?.parts ?? []
      const prompt = parts.filter((p) => p?.type === "text" && !p.synthetic).map((p) => p.text).join("\n")
      if (!(await resolveSession(input.sessionID)).parentID) {
        const codes = [...prompt.matchAll(APPROVE)]
        if (codes.length) for (const m of codes) approved.add(m[1].toLowerCase())
        else approved.clear()
      }
      const s = session(input.sessionID)
      const ev = {
        ...base(input.sessionID), hook_event_name: "UserPromptSubmit", prompt,
        ...(s.usage ? { usage: s.usage, context_limit: s.contextLimit ?? 0, model: s.model ?? "" } : {}),
      }
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

    dispose: async () => {
      await Promise.all([...sessions.keys()].map((id) => end(id, "exit", END_MS)))
    },
  }
}

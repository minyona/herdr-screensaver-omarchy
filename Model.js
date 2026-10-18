// Herdr Screensaver: every decision and every exact argv Service.qml uses, kept here so that
// `node --test tests/model.test.mjs` checks the same strings the shell runs.
// No QML imports; the module.exports guard at the end follows Omarchy's IdleModel.js.

var MARKER = "org.omarchy.screensaver"
var DEFAULT_SCREENSAVER = 150   // Omarchy's idle defaults (shell/plugins/services/idle/Service.qml)
var DEFAULT_LOCK = 300
var LEAD_SECONDS = 2            // herdr starts this long before Omarchy's own screensaver would

var DEFAULTS = { enabled: "on", takeover: "off", takeover_since: "", lock_on_wake: "on", font_size: "auto" }

// Omarchy's IdleModel.secondsFromConfig, unchanged
function secondsFromConfig(value, fallback) {
  var n = Number(value)
  if (!isFinite(n) || n < 0) return fallback
  return Math.floor(n)
}

// The takeover IdleMonitor's timeout: idle.screensaver - 2 s (at least 1). 0 = do not arm: no screensaver
// timeout, or the lock comes first or together (then Omarchy shows no screensaver either).
function leadTimeout(screensaver, lock) {
  var ss = Number(screensaver), lk = Number(lock)
  if (!isFinite(ss) || ss <= 0) return 0
  if (isFinite(lk) && lk <= ss) return 0
  return Math.max(1, Math.floor(ss) - LEAD_SECONDS)
}

// Arm only when the plugin is enabled, takeover is on, and stay-awake is known to be off.
function shouldArm(s) {
  return !!(s && s.enabled && s.takeover && s.stayAwakeLoaded && !s.stayAwake)
}

function validFontSize(v) {
  var s = String(v)
  if (s === "auto") return true
  var m = /^([0-9]+)(\.5)?$/.exec(s)
  if (!m) return false
  var n = parseInt(m[1], 10)
  return n >= 6 && (n < 36 || s === "36")
}

function validValue(key, value) {
  if (key === "enabled" || key === "takeover" || key === "lock_on_wake") return value === "on" || value === "off"
  if (key === "font_size") return validFontSize(value)
  if (key === "takeover_since") return true
  return false
}

// $DATA/state (key=value lines) -> every key, defaults for missing or invalid values (first line wins, as ctl)
function parseState(text) {
  var out = {}, seen = {}
  for (var k in DEFAULTS) out[k] = DEFAULTS[k]
  var lines = String(text || "").split("\n")
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i]
    var eq = line.indexOf("=")
    if (eq <= 0) continue
    var key = line.slice(0, eq), value = line.slice(eq + 1)
    if (!(key in DEFAULTS) || seen[key]) continue
    seen[key] = true
    if (value !== "" && validValue(key, value)) out[key] = value
  }
  return out
}

// "file:///a/b/" (Qt.resolvedUrl(".")) -> "/a/b/" (percent-decoded, trailing slash)
function dirFromUrl(url) {
  var s = String(url || "")
  if (s.indexOf("file://") === 0) s = s.slice(7)
  try { s = decodeURIComponent(s) } catch (e) {}
  if (s.length && s.charAt(s.length - 1) !== "/") s += "/"
  return s
}

// Paths go in as arguments ($0, $@), never into the script text, so any HOME works.
// idle: skipped while Omarchy's lock is up (like Omarchy's own idle launch); force: always (test).
// The marker is in argv from the first instant, so Omarchy's launcher sees a screensaver as running.
function launchArgv(dir, mode) {
  var m = mode === "force" ? "force" : "idle"
  var script = m === "idle"
    ? "[[ $(omarchy-shell lock isLocked 2>/dev/null) == \"true\" ]] || exec bash \"$0\" \"$@\""
    : "exec bash \"$0\" \"$@\""
  return ["bash", "-lc", script, dirFromUrl(dir) + "bin/herdr-screensaver-launch", m, MARKER]
}

function ctlArgv(dir) {
  var argv = ["bash", "-lc", "exec bash \"$0\" \"$@\"", dirFromUrl(dir) + "bin/herdr-screensaver-ctl"]
  for (var i = 1; i < arguments.length; i++) argv.push(String(arguments[i]))
  return argv
}

function onOff(b) { return b ? "ON" : "OFF" }

// The status() text: the state and the monitor from the service, then the offline probes from
// `herdr-screensaver-ctl status` (showing, python3, terminal, old curl install).
function statusText(o) {
  o = o || {}
  var st = o.state || parseState("")
  var lines = [
    "enabled: " + st.enabled.toUpperCase(),
    "takeover: " + st.takeover.toUpperCase() + (st.takeover === "on" && st.takeover_since ? " (since " + st.takeover_since + ")" : ""),
    "lock on wake: " + st.lock_on_wake.toUpperCase(),
    "font size: " + st.font_size,
    "idle monitor: " + (o.armed ? "ARMED (" + o.timeout + " s, " + LEAD_SECONDS + " s before Omarchy's screensaver at " + o.screensaver + " s)" : "OFF"),
    "stay-awake: " + (o.stayAwakeLoaded ? onOff(o.stayAwake) : "unknown")
  ]
  if (o.running) lines.push("launcher: running")
  var probes = String(o.probes || "").split("\n")
  var keep = /^(showing|python3|terminal|old curl install): /
  var any = false
  for (var i = 0; i < probes.length; i++) {
    if (keep.test(probes[i])) { lines.push(probes[i]); any = true }
  }
  if (!any) lines.push("probes: not run yet (try again in a second)")
  return lines.join("\n")
}

if (typeof module !== "undefined") {
  module.exports = {
    MARKER: MARKER,
    DEFAULT_SCREENSAVER: DEFAULT_SCREENSAVER,
    DEFAULT_LOCK: DEFAULT_LOCK,
    LEAD_SECONDS: LEAD_SECONDS,
    secondsFromConfig: secondsFromConfig,
    leadTimeout: leadTimeout,
    shouldArm: shouldArm,
    validFontSize: validFontSize,
    validValue: validValue,
    parseState: parseState,
    dirFromUrl: dirFromUrl,
    launchArgv: launchArgv,
    ctlArgv: ctlArgv,
    statusText: statusText
  }
}

// Herdr Screensaver: an Omarchy shell service plugin (kinds: service, keepLoaded).
// Runs inside the Omarchy shell; it starts no other shell process. It never writes a file of Omarchy's:
// its only state is ${HERDR_SS_DATA:-~/.local/share/herdr-screensaver-plugin}/state, written by
// bin/herdr-screensaver-ctl. Takeover (opt-in, `omarchy-shell herdr-screensaver takeover on`) arms an
// IdleMonitor 2 s before Omarchy's screensaver timeout and opens herdr instead; the launcher's argv
// carries org.omarchy.screensaver, so Omarchy's own launcher then sees a screensaver and starts none.
// Disabling or removing the plugin unloads this file and its IdleMonitor: Omarchy is back to stock.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "Model.js" as Model

Item {
  id: root

  // Injected by omarchy-shell
  property var shell: null

  readonly property string pluginDir: Model.dirFromUrl(Qt.resolvedUrl("."))
  readonly property string home: Quickshell.env("HOME")
  readonly property string dataDir: {
    var d = Quickshell.env("HERDR_SS_DATA")
    return d ? String(d) : root.home + "/.local/share/herdr-screensaver-plugin"
  }
  readonly property string statePath: dataDir + "/state"
  // the same path Omarchy's idle service uses (read only here)
  readonly property string stayAwakeDir: root.home + "/.local/state/omarchy/indicators"
  readonly property string stayAwakePath: stayAwakeDir + "/stay-awake"

  readonly property var idleConfig: shell && shell.shellConfig && shell.shellConfig.idle ? shell.shellConfig.idle : ({})
  readonly property int screensaverSeconds: Model.secondsFromConfig(idleConfig.screensaver, Model.DEFAULT_SCREENSAVER)
  readonly property int lockSeconds: Model.secondsFromConfig(idleConfig.lock, Model.DEFAULT_LOCK)
  readonly property int leadTimeout: Model.leadTimeout(screensaverSeconds, lockSeconds)

  property var state: Model.parseState("")
  property bool stayAwake: false
  property bool stayAwakeLoaded: false
  property string probes: ""
  property string lastEvent: "starting"

  readonly property bool armWanted: leadTimeout > 0 && Model.shouldArm({
    enabled: state.enabled === "on",
    takeover: state.takeover === "on",
    stayAwake: stayAwake,
    stayAwakeLoaded: stayAwakeLoaded
  })

  function logEvent(what) {
    root.lastEvent = what
    console.log("herdr-screensaver " + new Date().toISOString() + " " + what)
  }

  // ---- state ----
  function readState() {
    stateFile.reload()
  }

  function applyStateText(text) {
    root.state = Model.parseState(text)
  }

  function ctl() {
    var argv = Model.ctlArgv.apply(null, [root.pluginDir].concat(Array.prototype.slice.call(arguments)))
    ctlQueue.push(argv)
    runCtlQueue()
  }

  property var ctlQueue: []
  function runCtlQueue() {
    if (ctlProcess.running || root.ctlQueue.length === 0) return
    ctlProcess.command = root.ctlQueue.shift()
    ctlProcess.running = true
  }

  function refreshProbes() {
    if (probeProcess.running) return
    probeProcess.command = Model.ctlArgv(root.pluginDir, "status")
    probeProcess.running = true
  }

  function setKey(key, value) {
    if (!Model.validValue(key, value) || key === "takeover_since") return "error: bad value for " + key + ": '" + value + "'"
    ctl("set", key, value)
    return key + "=" + value
  }

  function onOffArg(key, mode) {
    var m = String(mode || "status").trim()
    if (m === "status") return root.state[key]
    if (m !== "on" && m !== "off") return "error: use on, off or status"
    return setKey(key, m)
  }

  // ---- launching ----
  function launch(mode, why) {
    if (launchProcess.running) {
      logEvent("launch skipped (" + why + "): the launcher is still running")
      return "already running"
    }
    launchProcess.command = Model.launchArgv(root.pluginDir, mode)
    launchProcess.running = true
    logEvent("launch " + mode + " (" + why + ")")
    return "launching"
  }

  // ---- stay-awake (read only; Omarchy owns the file) ----
  function refreshStayAwake() {
    if (stayAwakeProbe.running) return
    stayAwakeProbe.command = ["test", "-f", root.stayAwakePath]
    stayAwakeProbe.running = true
  }

  // ---- the takeover monitor: recreated (not updated) when its timeout changes ----
  onArmWantedChanged: rearm()
  onLeadTimeoutChanged: rearm()
  function rearm() {
    idleLoader.active = false
    armTimer.restart()
  }

  Timer {
    id: armTimer
    interval: 80
    repeat: false
    onTriggered: {
      idleLoader.active = root.armWanted
      root.logEvent(root.armWanted ? "idle monitor armed at " + root.leadTimeout + " s" : "idle monitor off")
    }
  }

  Loader {
    id: idleLoader
    active: false
    sourceComponent: Component {
      IdleMonitor {
        enabled: true
        timeout: root.leadTimeout
        respectInhibitors: true
        onIsIdleChanged: if (isIdle && root.armWanted) root.launch("idle", "idle " + root.leadTimeout + " s")
      }
    }
  }

  FileView {
    id: stateFile
    path: root.statePath
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyStateText(text())
    onLoadFailed: root.applyStateText("")
  }

  FileView {
    id: stayAwakeDirWatcher
    path: root.stayAwakeDir
    watchChanges: true
    printErrors: false
    onFileChanged: root.refreshStayAwake()
  }

  Timer {
    // stay-awake can be created before its directory exists; look again now and then (read only)
    interval: 5000
    running: true
    repeat: true
    onTriggered: root.refreshStayAwake()
  }

  Process {
    id: stayAwakeProbe
    onExited: function(exitCode) {
      root.stayAwake = exitCode === 0
      root.stayAwakeLoaded = true
    }
  }

  Process {
    id: ctlProcess
    stdout: StdioCollector { onStreamFinished: if (text.length) root.logEvent("ctl: " + text.trim()) }
    stderr: StdioCollector { onStreamFinished: if (text.length) root.logEvent("ctl error: " + text.trim()) }
    onExited: {
      root.readState()
      root.runCtlQueue()
    }
  }

  Process {
    id: probeProcess
    stdout: StdioCollector { onStreamFinished: root.probes = text }
  }

  Process {
    id: launchProcess
    onExited: function(exitCode) { root.logEvent("launcher exited " + exitCode) }
  }

  Component.onCompleted: {
    logEvent("service ready, plugin dir " + root.pluginDir)
    readState()
    refreshStayAwake()
    refreshProbes()
  }

  IpcHandler {
    target: "herdr-screensaver"

    function status(): string {
      root.readState()
      root.refreshProbes()
      return Model.statusText({
        state: root.state,
        armed: idleLoader.active && root.armWanted,
        timeout: root.leadTimeout,
        screensaver: root.screensaverSeconds,
        stayAwake: root.stayAwake,
        stayAwakeLoaded: root.stayAwakeLoaded,
        running: launchProcess.running,
        probes: root.probes
      })
    }

    function enable(): string {
      return root.setKey("enabled", "on")
    }

    function disable(): string {
      return root.setKey("enabled", "off")
    }

    function takeover(mode: string): string {
      return root.onOffArg("takeover", mode)
    }

    function test(): string {
      return root.launch("force", "test")
    }

    function reload(): string {
      root.readState()
      root.refreshStayAwake()
      root.refreshProbes()
      root.rearm()
      return "reloaded"
    }

    function lockOnWake(mode: string): string {
      return root.onOffArg("lock_on_wake", mode)
    }

    function fontSize(value: string): string {
      var v = String(value || "").trim()
      if (v === "" || v === "status") return root.state.font_size
      return root.setKey("font_size", v)
    }
  }
}

// PSA10Bar: the 👻 menu bar icon for Ghost Bid's price checks (the app was called PSA10 Tracker until 2026-10-18).
//
// Icon: 👻 idle · 👻⏳ a check is running · 👻❗ the running check needs you (permission, sign-in…).
// Click the icon: a small bubble drops from it with Quick / Full and the status.
// At the prompt times (widget/lib.sh) the same bubble opens by itself with "Start a new price check?"
// and Skip; it closes on its own after 15 minutes or when you click elsewhere.
//
// All logic stays in the shell scripts next to it (status.sh, start.sh, lib.sh); this app only draws.
// Built on the Mac by widget/install.sh:  swiftc -O -o PSA10Bar PSA10Bar.swift
import AppKit
import SwiftUI

let widgetDir = FileManager.default.homeDirectoryForCurrentUser.path + "/.psa10/widget"
let trackerURL = URL(string: "https://sprdl.github.io/psa10-tracker/")!

func runScript(_ name: String, _ args: [String] = [], wait: Bool = true) -> String {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/bash")
    p.arguments = [widgetDir + "/" + name] + args
    p.standardError = FileHandle.nullDevice
    if !wait {
        p.standardOutput = FileHandle.nullDevice
        try? p.run()
        return ""
    }
    let out = Pipe()
    p.standardOutput = out
    do { try p.run() } catch { return "" }
    let data = out.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return String(decoding: data, as: UTF8.self)
}

struct Status {
    var running = false
    var runningMode = ""
    var suggested = "full"
    var latest = ""
    var ago = ""
    var lastFull = ""
    var next = ""
    var due = false
    var attention = false
    var lastRun = ""
    var canResume = false

    init() {}
    init(_ text: String) {
        var d: [String: String] = [:]
        for line in text.split(separator: "\n") {
            if let i = line.firstIndex(of: "=") {
                d[String(line[..<i])] = String(line[line.index(after: i)...])
            }
        }
        running = d["running"] == "1"
        runningMode = d["running_mode"] ?? ""
        suggested = d["suggested"] ?? "full"
        latest = d["latest"] ?? ""
        ago = d["ago"] ?? ""
        lastFull = d["last_full"] ?? ""
        next = d["next"] ?? ""
        due = d["due"] == "1"
        attention = d["attention"] == "1"
        lastRun = d["last_run"] ?? ""
        canResume = d["can_resume"] == "1"
    }
}

final class Model: ObservableObject {
    @Published var st = Status()
    @Published var prompting = false
}

struct Panel: View {
    @ObservedObject var m: Model
    let act: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(m.prompting ? "Start a new price check?" : "Ghost Bid price check")
                .font(.headline)

            if m.st.running {
                HStack {
                    if m.st.attention {
                        Text("⚠️ The run needs you").font(.callout)
                    } else {
                        Text("⏳ \(m.st.runningMode.isEmpty ? "A" : m.st.runningMode.capitalized) check is running…")
                            .font(.callout)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Button("Show window") { act("show") }.buttonStyle(.link).font(.caption)
                }
            }

            HStack(spacing: 8) {
                modeButton("Quick · Haiku", "quick")
                modeButton("Full · Sonnet", "full")
                if m.prompting {
                    Button("Skip") { act("skip") }
                }
            }
            .disabled(m.st.running)

            Divider()

            VStack(alignment: .leading, spacing: 3) {
                if !m.st.latest.isEmpty {
                    Text("Last snapshot: \(m.st.latest)\(m.st.ago.isEmpty ? "" : " · \(m.st.ago)")")
                }
                if !m.st.lastFull.isEmpty { Text("Last full check: \(m.st.lastFull)") }
                if !m.st.lastRun.isEmpty { Text("Last run: \(m.st.lastRun)") }
                Text("Suggested: \(m.st.suggested) · next prompt \(m.st.next)")
            }
            .font(.caption)
            .foregroundColor(.secondary)

            Divider()

            HStack(spacing: 12) {
                Button("Tracker site") { act("site") }
                Button("Run history") { act("history") }
                if m.st.canResume && !m.st.running {
                    Button("Open last run") { act("resume") }
                }
                Spacer()
                Button("Quit") { act("quit") }
            }
            .buttonStyle(.link)
            .font(.caption)
        }
        .padding(14)
        .frame(width: 300)
    }

    @ViewBuilder
    func modeButton(_ title: String, _ mode: String) -> some View {
        if m.st.suggested == mode {
            Button(title) { act(mode) }.buttonStyle(.borderedProminent)
        } else {
            Button(title) { act(mode) }.buttonStyle(.bordered)
        }
    }
}

// The app is never frontmost, so the bubble's buttons must react to the first click.
final class FirstClickHostingView<V: View>: NSHostingView<V> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSPopoverDelegate {
    var item: NSStatusItem!
    let popover = NSPopover()
    let model = Model()
    var host: FirstClickHostingView<Panel>!
    var refreshTimer: Timer?
    var closeTimer: Timer?
    var clickMonitor: Any?

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "👻"
        item.button?.target = self
        item.button?.action = #selector(iconClicked)

        host = FirstClickHostingView(rootView: Panel(m: model) { [weak self] a in self?.act(a) })
        let vc = NSViewController()
        vc.view = host
        popover.contentViewController = vc
        popover.behavior = .transient
        popover.animates = true
        popover.delegate = self

        refresh()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            DispatchQueue.main.async { self?.refresh() }
        }
    }

    func refresh() {
        DispatchQueue.global(qos: .utility).async {
            let st = Status(runScript("status.sh"))
            DispatchQueue.main.async {
                self.model.st = st
                self.item.button?.title = st.running ? (st.attention ? "👻❗" : "👻⏳") : "👻"
                if st.due && !self.popover.isShown {
                    self.showPrompt()
                } else if self.popover.isShown {
                    self.host.layoutSubtreeIfNeeded()
                    self.popover.contentSize = self.host.fittingSize
                }
            }
        }
    }

    func show() {
        guard let button = item.button else { return }
        host.layoutSubtreeIfNeeded()
        popover.contentSize = host.fittingSize
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        // The app is never active, so .transient alone doesn't see clicks in other apps:
        // close the bubble on any click outside it (mouse monitors need no extra permission).
        if clickMonitor == nil {
            clickMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
                DispatchQueue.main.async { self?.popover.performClose(nil) }
            }
        }
    }

    func showPrompt() {
        model.prompting = true
        show()
        closeTimer?.invalidate()
        closeTimer = Timer.scheduledTimer(withTimeInterval: 900, repeats: false) { [weak self] _ in
            DispatchQueue.main.async { self?.popover.performClose(nil) }
        }
    }

    @objc func iconClicked() {
        if popover.isShown {
            popover.performClose(nil)
        } else {
            model.prompting = false
            show()
            refresh()
        }
    }

    func popoverDidClose(_ notification: Notification) {
        model.prompting = false
        closeTimer?.invalidate()
        if let m = clickMonitor { NSEvent.removeMonitor(m); clickMonitor = nil }
    }

    func act(_ a: String) {
        switch a {
        case "quick", "full":
            popover.performClose(nil)
            model.st.running = true
            model.st.runningMode = a
            item.button?.title = "👻⏳"
            // The run window opens minimized; if Terminal still grabbed the focus, hand it back.
            let previous = NSWorkspace.shared.frontmostApplication
            _ = runScript("start.sh", [a], wait: false)
            for delay in [1.0, 2.5] {
                DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                    if NSWorkspace.shared.frontmostApplication?.bundleIdentifier == "com.apple.Terminal",
                       let previous = previous, previous.bundleIdentifier != "com.apple.Terminal" {
                        previous.activate(options: [])
                    }
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { self.refresh() }
        case "show", "resume":
            popover.performClose(nil)
            _ = runScript("start.sh", [a], wait: false)
        case "history":
            popover.performClose(nil)
            _ = runScript("start.sh", ["history"], wait: false)
        case "site":
            popover.performClose(nil)
            NSWorkspace.shared.open(trackerURL)
        case "quit":
            NSApp.terminate(nil)
        default:
            popover.performClose(nil)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()

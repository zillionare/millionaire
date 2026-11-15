import Cocoa

struct MenuProfile: Codable {
    let launcher: String
    let label: String
    let domain: String
    let logs: String
    let system: Bool
    let portFile: String?
}

final class MenuController: NSObject, NSApplicationDelegate {
    let profile: MenuProfile
    let menu = NSMenu()
    let status = NSMenuItem(title: "正在检查服务…", action: nil, keyEquivalent: "")
    var statusItem: NSStatusItem?
    var timer: Timer?
    private(set) var busy = false
    private(set) var running = false
    var openURL: (URL) -> Bool = { NSWorkspace.shared.open($0) }
    var quitApplication: () -> Void = { NSApp.terminate(nil) }
    var showError: (String) -> Void = { message in
        let alert = NSAlert()
        alert.messageText = "Millionaire"
        alert.informativeText = message
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    init(profile: MenuProfile) {
        self.profile = profile
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "M"
        item.button?.toolTip = "Millionaire"
        statusItem = item
        menu.autoenablesItems = false
        status.isEnabled = false
        menu.addItem(status)
        menu.addItem(.separator())
        addItem("打开网页界面", #selector(openWebsite), "o")
        menu.addItem(.separator())
        addItem("启动服务", #selector(startService))
        addItem("停止服务", #selector(stopService))
        addItem("刷新状态", #selector(refreshStatus))
        addItem("打开日志目录", #selector(openLogs))
        menu.addItem(.separator())
        addItem("退出菜单栏控件", #selector(quit), "q")
        item.menu = menu
        refreshStatus()
        timer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            self?.refreshStatus()
        }
    }

    private func addItem(_ title: String, _ action: Selector, _ key: String = "") {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.target = self
        menu.addItem(item)
    }

    @objc func openWebsite() {
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: profile.launcher)
        process.arguments = ["web-url"]
        var environment = ["QUANTIDE_CONFIG_HOME": URL(fileURLWithPath: profile.logs).deletingLastPathComponent().path]
        if let file = profile.portFile { environment["QUANTIDE_PUBLIC_WEB_PORT"] = file }
        process.environment = ProcessInfo.processInfo.environment.merging(environment,
            uniquingKeysWith: { _, new in new })
        process.standardOutput = output
        process.standardError = Pipe()
        do {
            try process.run()
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let text = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            guard process.terminationStatus == 0, let url = URL(string: text),
                  url.scheme == "http", url.host == "127.0.0.1" else {
                throw NSError(domain: "Millionaire", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "无法读取网页地址，请检查服务配置。"])
            }
            _ = openURL(url)
        } catch { showError(error.localizedDescription) }
    }

    @objc func openLogs() {
        _ = openURL(URL(fileURLWithPath: profile.logs, isDirectory: true))
    }

    @objc func startService() { perform("start") }
    @objc func stopService() { perform("stop") }
    @objc func refreshStatus() { perform("status") }

    @objc func quit() {
        timer?.invalidate()
        quitApplication()
    }

    private func updateControls() {
        menu.item(withTitle: "启动服务")?.isEnabled = !busy && !running
        menu.item(withTitle: "停止服务")?.isEnabled = !busy && running
        menu.item(withTitle: "刷新状态")?.isEnabled = !busy
    }

    private func perform(_ action: String) {
        guard !busy else { return }
        busy = true
        updateControls()
        if action != "status" {
            status.title = action == "start" ? "正在启动…" : "正在停止…"
        }
        DispatchQueue.global(qos: .utility).async { [self] in
            do {
                let result = try execute(action)
                let state = action == "status" ? result : try execute("status")
                DispatchQueue.main.async { [self] in
                    busy = false
                    running = state.0 == 0 && state.1.contains("state = running")
                    status.title = running ? "服务正在运行" : "服务已停止或等待重启"
                    statusItem?.button?.toolTip = "Millionaire：\(status.title)"
                    updateControls()
                    if action != "status" && result.0 != 0 { showError(result.1) }
                }
            } catch {
                DispatchQueue.main.async { [self] in
                    busy = false
                    status.title = "无法读取服务状态"
                    updateControls()
                    showError(error.localizedDescription)
                }
            }
        }
    }

    private func execute(_ action: String) throws -> (Int32, String) {
        let process = Process()
        if action == "status" {
            process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
            process.arguments = ["print", "\(profile.domain)/\(profile.label)"]
        } else {
            let arguments = [profile.launcher, "service", action]
                + (profile.system ? ["--system"] : [])
            configureProcess(process, arguments)
        }
        let output = Pipe()
        process.standardOutput = output
        process.standardError = output
        try process.run()
        let timeout = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 45, execute: timeout)
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        timeout.cancel()
        return (process.terminationStatus, String(decoding: data.suffix(4000), as: UTF8.self))
    }

    private func configureProcess(_ process: Process, _ arguments: [String]) {
        let serviceName = String(profile.label.dropFirst("ai.quantide.".count))
        if profile.system {
            let command = (["/usr/bin/env", "MILLIONAIRE_SERVICE_NAME=\(serviceName)"]
                + arguments).map {
                "'" + $0.replacingOccurrences(of: "'", with: "'\\''") + "'"
            }.joined(separator: " ")
            process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            let script = """
                on run argv
                    do shell script (item 1 of argv) with administrator privileges
                end run
                """
            process.arguments = ["-e", script, command]
        } else {
            process.executableURL = URL(fileURLWithPath: arguments[0])
            process.arguments = Array(arguments.dropFirst())
            process.environment = ProcessInfo.processInfo.environment.merging(
                ["MILLIONAIRE_SERVICE_NAME": serviceName], uniquingKeysWith: { _, new in new })
        }
    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Windows.Forms;
using Millionaire;

class TraySmoke {
    [STAThread]
    static int Main(string[] args) {
        Application.EnableVisualStyles();
        var profile = new TrayProfile(args[0]);
        var context = new TrayContext(profile);
        var targets = new List<string>();
        context.OpenTarget = targets.Add;
        string phase = "initial";
        Exception failure = null;
        var deadline = DateTime.UtcNow.AddSeconds(75);
        var timer = new Timer { Interval = 100 };
        timer.Tick += delegate {
            try {
                if (DateTime.UtcNow > deadline) throw new TimeoutException(phase);
                if (context.Busy) return;
                if (phase == "initial") {
                    Require(context.Icon.Visible, "Tray icon was not created");
                    Require(context.Running, "Service was not initially running");
                    string oldPort = File.ReadAllText(profile.PortFile);
                    try {
                        File.WriteAllText(profile.PortFile, "9231");
                        context.Items["open"].PerformClick();
                        Require(targets.Count == 1 && targets[0] == "http://127.0.0.1:9231",
                            "Tray ignored the published service port");
                        targets.Clear();
                    } finally { File.WriteAllText(profile.PortFile, oldPort); }
                    context.Items["stop"].PerformClick();
                    phase = "stopped";
                } else if (phase == "stopped") {
                    Require(!context.Running, "Stop menu did not stop service");
                    context.Items["open"].PerformClick();
                    context.Items["start"].PerformClick();
                    phase = "started";
                } else {
                    context.RefreshStatus();
                    if (!context.Running) return;
                    context.Items["status"].PerformClick();
                    context.Items["logs"].PerformClick();
                    Require(targets.Count == 2, "Open menu actions were not invoked");
                    Require(targets[0] == "http://127.0.0.1:8130", "Wrong browser URL");
                    Require(targets[1] == profile.Logs, "Wrong log path");
                    timer.Stop();
                    context.Items["quit"].PerformClick();
                }
            } catch (Exception error) {
                failure = error;
                timer.Stop();
                context.ExitThread();
            }
        };
        timer.Start();
        Application.Run(context);
        timer.Dispose();
        if (failure != null) {
            File.WriteAllText(args[1], failure.ToString());
            return 1;
        }
        File.WriteAllText(args[1], "{\"native_tray_widgets\":true,"
            + "\"stop_start_widgets\":true,\"quit_action\":true,"
            + "\"browser_url\":\"http://127.0.0.1:8130\"}");
        return 0;
    }

    static void Require(bool condition, string message) {
        if (!condition) throw new InvalidOperationException(message);
    }
}

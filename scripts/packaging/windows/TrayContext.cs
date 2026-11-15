using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.ServiceProcess;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Millionaire {
    public sealed class TrayContext : ApplicationContext {
        readonly TrayProfile profile;
        readonly Control dispatcher = new Control();
        readonly Timer timer = new Timer();
        public readonly NotifyIcon Icon = new NotifyIcon();
        public readonly Dictionary<string, ToolStripMenuItem> Items =
            new Dictionary<string, ToolStripMenuItem>();
        public bool Busy { get; private set; }
        public bool Running { get; private set; }
        public Action<string> OpenTarget = delegate(string target) {
            Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
        };

        public TrayContext(TrayProfile profile) {
            this.profile = profile;
            dispatcher.Handle.ToInt64();
            var menu = new ContextMenuStrip();
            Add(menu, "state", "正在检查服务…", null);
            Items["state"].Enabled = false;
            menu.Items.Add(new ToolStripSeparator());
            Add(menu, "open", "打开网页界面", delegate { OpenWebsite(); });
            menu.Items.Add(new ToolStripSeparator());
            Add(menu, "start", "启动服务", delegate { Act("start"); });
            Add(menu, "stop", "停止服务", delegate { Act("stop"); });
            Add(menu, "status", "刷新状态", delegate { RefreshStatus(); });
            Add(menu, "logs", "打开日志目录", delegate { Open(profile.Logs); });
            menu.Items.Add(new ToolStripSeparator());
            Add(menu, "quit", "退出托盘控件", delegate { ExitThread(); });
            Icon.Icon = SystemIcons.Application;
            Icon.Text = "Millionaire";
            Icon.ContextMenuStrip = menu;
            Icon.DoubleClick += delegate { OpenWebsite(); };
            Icon.Visible = true;
            timer.Interval = 10000;
            timer.Tick += delegate { RefreshStatus(); };
            timer.Start();
            RefreshStatus();
        }

        void Add(ContextMenuStrip menu, string name, string text, EventHandler action) {
            var item = new ToolStripMenuItem(text);
            if (action != null) item.Click += action;
            Items[name] = item;
            menu.Items.Add(item);
        }

        void Open(string target) {
            try { OpenTarget(target); }
            catch (Exception error) { Report(error.Message); }
        }

        void OpenWebsite() {
            try { Open(profile.WebUrl()); }
            catch (Exception error) { Report(error.Message); }
        }

        public void RefreshStatus() {
            if (Busy) return;
            try {
                using (var service = new ServiceController(profile.ServiceName)) {
                    Running = service.Status == ServiceControllerStatus.Running;
                    Items["state"].Text = Running
                        ? "服务正在运行" : "服务已停止或正在切换";
                }
            } catch (InvalidOperationException) {
                Running = false;
                Items["state"].Text = "服务未安装或状态不可用";
            }
            Icon.Text = "Millionaire：" + Items["state"].Text;
            UpdateControls();
        }

        void UpdateControls() {
            Items["start"].Enabled = !Busy && !Running;
            Items["stop"].Enabled = !Busy && Running;
            Items["status"].Enabled = !Busy;
        }

        void Act(string action) {
            if (Busy) return;
            Busy = true;
            Items["state"].Text = action == "start" ? "正在启动…" : "正在停止…";
            UpdateControls();
            Task.Run(delegate {
                string error = null;
                try {
                    var start = new ProcessStartInfo(typeof(TrayContext).Assembly.Location,
                        "--service-action " + action + " --root \"" + profile.Root + "\"");
                    start.UseShellExecute = true;
                    if (!TrayProfile.IsAdministrator()) start.Verb = "runas";
                    using (var process = Process.Start(start)) {
                        if (!process.WaitForExit(50000))
                            throw new System.TimeoutException(
                                "服务操作超时，请检查日志");
                        if (process.ExitCode != 0)
                            error = "服务操作未完成，请检查日志（退出码 "
                                + process.ExitCode + "）";
                    }
                } catch (Exception failure) { error = failure.Message; }
                FinishAction(error);
            });
        }

        void FinishAction(string error) {
            try {
                dispatcher.BeginInvoke((Action)delegate {
                    Busy = false;
                    RefreshStatus();
                    if (error != null) Report(error);
                });
            } catch (InvalidOperationException) {
                // The user may quit the tray while a service action finishes.
            }
        }

        void Report(string message) {
            Icon.ShowBalloonTip(5000, "Millionaire", message, ToolTipIcon.Error);
        }

        public void RequestExit() {
            try { dispatcher.BeginInvoke((Action)delegate { ExitThread(); }); }
            catch (InvalidOperationException) { }
        }

        protected override void ExitThreadCore() {
            timer.Stop();
            timer.Dispose();
            Icon.Visible = false;
            Icon.ContextMenuStrip.Dispose();
            Icon.Dispose();
            dispatcher.Dispose();
            base.ExitThreadCore();
        }
    }
}

using System;
using System.IO;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Threading;
using System.Windows.Forms;

namespace Millionaire {
    static class Program {
        [STAThread]
        static int Main(string[] arguments) {
            try { return Run(arguments); }
            catch (Exception error) {
                if (Array.IndexOf(arguments, "--service-action") < 0)
                    MessageBox.Show(error.Message, "Millionaire");
                return 1;
            }
        }

        static int Run(string[] arguments) {
            int rootIndex = Array.IndexOf(arguments, "--root");
            string root = rootIndex < 0 ? AppDomain.CurrentDomain.BaseDirectory
                : arguments[rootIndex + 1];
            var profile = new TrayProfile(root);
            int actionIndex = Array.IndexOf(arguments, "--service-action");
            if (actionIndex >= 0) return profile.ServiceAction(arguments[actionIndex + 1]);
            string identity = "Millionaire." + profile.ServiceName;
            using (var signal = QuitSignal(identity)) {
                if (Array.IndexOf(arguments, "--quit") >= 0) {
                    signal.Set();
                    Thread.Sleep(500);
                    return 0;
                }
                bool created;
                using (var mutex = new Mutex(true, "Local\\" + identity, out created)) {
                    if (!created) return 0;
                    signal.Reset();
                    Application.EnableVisualStyles();
                    using (var context = new TrayContext(profile)) {
                        var wait = ThreadPool.RegisterWaitForSingleObject(signal,
                            delegate { context.RequestExit(); }, null, Timeout.Infinite, true);
                        try { Application.Run(context); }
                        finally { wait.Unregister(null); }
                    }
                }
            }
            return 0;
        }

        static EventWaitHandle QuitSignal(string identity) {
            var security = new EventWaitHandleSecurity();
            security.AddAccessRule(new EventWaitHandleAccessRule(
                new SecurityIdentifier(WellKnownSidType.AuthenticatedUserSid, null),
                EventWaitHandleRights.FullControl, AccessControlType.Allow));
            bool created;
            return new EventWaitHandle(false, EventResetMode.ManualReset,
                "Global\\" + identity + ".quit", out created, security);
        }
    }
}

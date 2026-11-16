using System;
using System.Diagnostics;
using System.IO;
using System.Security.Principal;
using System.Xml.Linq;

namespace Millionaire {
    public sealed class TrayProfile {
        public readonly string Root;
        public readonly string ServiceName;
        public readonly string Logs;
        public readonly string Config;
        public readonly string PortFile;

        public TrayProfile(string root) {
            Root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
            var service = XDocument.Load(Path.Combine(Root, "millionaire-service.xml")).Root;
            ServiceName = (string)service.Element("id");
            Logs = (string)service.Element("logpath");
            foreach (var item in service.Elements("env")) {
                if ((string)item.Attribute("name") == "QUANTIDE_CONFIG_HOME")
                    Config = (string)item.Attribute("value");
                if ((string)item.Attribute("name") == "QUANTIDE_PUBLIC_WEB_PORT")
                    PortFile = (string)item.Attribute("value");
            }
            if (String.IsNullOrWhiteSpace(ServiceName) || String.IsNullOrWhiteSpace(Logs))
                throw new InvalidDataException("Missing service ID or log directory");
        }

        public string WebUrl() {
            var start = new ProcessStartInfo(Path.Combine(Root, "runtime", "python.exe"),
                "-m quantide.cli web-url");
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            if (!String.IsNullOrWhiteSpace(Config))
                start.EnvironmentVariables["QUANTIDE_CONFIG_HOME"] = Config;
            if (!String.IsNullOrWhiteSpace(PortFile))
                start.EnvironmentVariables["QUANTIDE_PUBLIC_WEB_PORT"] = PortFile;
            using (var process = Process.Start(start)) {
                string text = process.StandardOutput.ReadToEnd().Trim();
                if (!process.WaitForExit(10000) || process.ExitCode != 0)
                    throw new InvalidOperationException("无法读取网页地址，请检查服务配置。");
                Uri uri;
                if (!Uri.TryCreate(text, UriKind.Absolute, out uri) || uri.Scheme != "http"
                    || uri.Host != "127.0.0.1")
                    throw new InvalidOperationException("网页地址无效，请检查服务配置。");
                return text;
            }
        }

        public static bool IsAdministrator() {
            using (var identity = WindowsIdentity.GetCurrent())
                return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
        }

        public int ServiceAction(string action) {
            if (action != "start" && action != "stop")
                throw new ArgumentException("Unsupported service action");
            var start = new ProcessStartInfo(Path.Combine(Root, "runtime", "python.exe"),
                "-m quantide.cli service " + action);
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.EnvironmentVariables["MILLIONAIRE_SERVICE_NAME"] = ServiceName;
            using (var process = Process.Start(start)) {
                if (!process.WaitForExit(45000)) {
                    process.Kill();
                    throw new TimeoutException("Service operation timed out");
                }
                return process.ExitCode;
            }
        }
    }
}

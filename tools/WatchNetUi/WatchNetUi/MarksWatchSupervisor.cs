using System.Diagnostics;
using System.Management;
using System.Text;

namespace WatchNetUi;

/// <summary>
/// One <c>python -m analyzer --watch</c> process for setup marks (all instruments),
/// plus one-shot <c>--marks --sec</c> for selected tickers.
/// </summary>
public sealed class MarksWatchSupervisor : IDisposable
{
    private readonly string _repoRoot;
    private readonly string _python;
    private Process? _watch;
    private bool _stopping;
    private bool _disposed;
    private CancellationTokenSource? _oneshotCts;

    public MarksWatchSupervisor(string repoRoot, string pythonExe)
    {
        _repoRoot = repoRoot;
        _python = pythonExe;
    }

    public event Action<string>? Log;

    public bool IsRunning => _watch is { HasExited: false };
    public int? Pid => IsRunning ? _watch!.Id : null;

    public bool StartWatch(double poll = 11.0)
    {
        if (IsRunning) return false;

        var foreign = FindForeignMarksWatchPids();
        if (foreign.Count > 0)
        {
            Emit($"уже крутится чужой --watch pid={string.Join(",", foreign)}; стопните его или нажмите «Метки: стоп»");
            // Adopt by killing foreigners then start ours — user asked to control from UI.
            foreach (var pid in foreign)
                KillPid(pid);
        }

        var psi = BasePsi();
        psi.ArgumentList.Add("--watch");
        psi.ArgumentList.Add("--poll");
        psi.ArgumentList.Add(poll.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture));

        _stopping = false;
        var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data))
                Emit(e.Data);
        };
        proc.ErrorDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data))
                Emit("ERR " + e.Data);
        };
        proc.Exited += (_, _) =>
        {
            Emit($"marks watch exit={proc.ExitCode}");
            if (_disposed || _stopping) return;
            _ = Task.Run(async () =>
            {
                await Task.Delay(2000).ConfigureAwait(false);
                if (_disposed || _stopping) return;
                try
                {
                    StartWatch(poll);
                    Emit("marks watch restarted");
                }
                catch (Exception ex)
                {
                    Emit("marks restart failed: " + ex.Message);
                }
            });
        };

        if (!proc.Start())
            throw new InvalidOperationException("Не удалось запустить --watch");
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        _watch = proc;
        Emit($"marks watch started pid={proc.Id}");
        return true;
    }

    public void StopWatch()
    {
        _stopping = true;
        foreach (var pid in FindForeignMarksWatchPids())
            KillPid(pid);
        if (_watch != null)
        {
            KillTree(_watch);
            _watch = null;
        }
        Emit("marks watch stopped");
    }

    public async Task ExportSelectedAsync(
        IReadOnlyList<(string Sec, string ClassCode)> instruments,
        CancellationToken cancel = default)
    {
        if (instruments.Count == 0) return;
        _oneshotCts?.Cancel();
        _oneshotCts = CancellationTokenSource.CreateLinkedTokenSource(cancel);
        var ct = _oneshotCts.Token;
        Emit($"marks разово: {instruments.Count} тикеров…");
        var ok = 0;
        foreach (var (sec, cls) in instruments)
        {
            ct.ThrowIfCancellationRequested();
            var psi = BasePsi();
            psi.ArgumentList.Add("--marks");
            psi.ArgumentList.Add("--sec");
            psi.ArgumentList.Add(sec);
            psi.ArgumentList.Add("--class-code");
            psi.ArgumentList.Add(cls);
            Emit($"marks export {sec}:{cls} …");
            using var proc = new Process { StartInfo = psi };
            proc.Start();
            var stdout = await proc.StandardOutput.ReadToEndAsync(ct).ConfigureAwait(false);
            var stderr = await proc.StandardError.ReadToEndAsync(ct).ConfigureAwait(false);
            await proc.WaitForExitAsync(ct).ConfigureAwait(false);
            if (!string.IsNullOrWhiteSpace(stdout))
                Emit(stdout.TrimEnd());
            if (!string.IsNullOrWhiteSpace(stderr))
                Emit("ERR " + stderr.TrimEnd());
            if (proc.ExitCode == 0) ok++;
            else Emit($"marks export {sec} exit={proc.ExitCode}");
        }
        Emit($"marks разово готово: {ok}/{instruments.Count}");
    }

    public void CancelOneShot() => _oneshotCts?.Cancel();

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        CancelOneShot();
        StopWatch();
    }

    private ProcessStartInfo BasePsi()
    {
        var psi = new ProcessStartInfo
        {
            FileName = _python,
            WorkingDirectory = _repoRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        psi.ArgumentList.Add("-u");
        psi.ArgumentList.Add("-m");
        psi.ArgumentList.Add("analyzer");
        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        return psi;
    }

    private void Emit(string msg) => Log?.Invoke(msg);

    /// <summary>
    /// Foreign <c>--watch</c> but not net/odds/waves/pool.
    /// </summary>
    public static List<int> FindForeignMarksWatchPids()
    {
        var found = new List<int>();
        try
        {
            using var searcher = new ManagementObjectSearcher(
                "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'python.exe' OR Name = 'pythonw.exe'");
            foreach (ManagementObject obj in searcher.Get())
            {
                var cmd = obj["CommandLine"]?.ToString() ?? "";
                if (cmd.IndexOf("--watch", StringComparison.OrdinalIgnoreCase) < 0)
                    continue;
                if (cmd.Contains("--watch-net", StringComparison.OrdinalIgnoreCase)
                    || cmd.Contains("--watch-odds", StringComparison.OrdinalIgnoreCase)
                    || cmd.Contains("--watch-waves", StringComparison.OrdinalIgnoreCase)
                    || cmd.Contains("--watch-net-pool", StringComparison.OrdinalIgnoreCase)
                    || cmd.Contains("--watch-only", StringComparison.OrdinalIgnoreCase))
                    continue;
                // bare --watch (marks)
                if (int.TryParse(obj["ProcessId"]?.ToString(), out var pid))
                    found.Add(pid);
            }
        }
        catch
        {
            // WMI may be restricted; ignore — UI still starts its own process.
        }
        return found;
    }

    private static void KillPid(int pid)
    {
        try
        {
            using var killer = Process.Start(new ProcessStartInfo
            {
                FileName = "taskkill",
                Arguments = $"/PID {pid} /T /F",
                CreateNoWindow = true,
                UseShellExecute = false,
            });
            killer?.WaitForExit(5000);
        }
        catch
        {
            try
            {
                using var p = Process.GetProcessById(pid);
                p.Kill(entireProcessTree: true);
            }
            catch { /* ignore */ }
        }
    }

    private static void KillTree(Process? proc)
    {
        if (proc == null) return;
        try
        {
            if (!proc.HasExited)
                KillPid(proc.Id);
        }
        catch { /* ignore */ }
        try { proc.Dispose(); } catch { /* ignore */ }
    }
}

using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace WatchNetUi;

/// <summary>
/// Pool of <c>python -m analyzer --watch-net</c> processes.
/// Max N workers cover all instruments via <c>--watch-only</c> shards (round-robin).
/// Separate OS processes — not threads (GIL / numpy).
/// </summary>
public sealed class WatchNetSupervisor : IDisposable
{
    /// <summary>Match analyzer.watch_pool.JOBS_CAP — more concurrent export_net thrash and look stuck.</summary>
    public const int JobsCap = 8;

    private readonly ConcurrentDictionary<string, Worker> _workers = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, string> _instrumentToWorker = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, string> _busySecByWorker = new(StringComparer.OrdinalIgnoreCase);
    private readonly string _repoRoot;
    private readonly string _python;
    private bool _disposed;

    public WatchNetSupervisor(string? repoRoot = null, string? pythonExe = null)
    {
        _repoRoot = repoRoot ?? Paths.FindRepoRoot();
        _python = pythonExe ?? ResolvePython();
    }

    public string RepoRoot => _repoRoot;
    public string PythonExe => _python;
    public int WorkerCount => _workers.Count(kv => kv.Value.Process is { HasExited: false });

    public string? BusySecForWorker(string workerId) =>
        _busySecByWorker.TryGetValue(workerId, out var sec) ? sec : null;

    public static int ClampJobs(int jobs) =>
        jobs <= 0 ? JobsCap : Math.Max(1, Math.Min(jobs, JobsCap));

    public event Action<string, string>? Log;

    public bool IsInstrumentCovered(string instrumentKey) =>
        _instrumentToWorker.TryGetValue(instrumentKey, out var wid)
        && _workers.TryGetValue(wid, out var w)
        && w.Process is { HasExited: false };

    public int? PidForInstrument(string instrumentKey) =>
        _instrumentToWorker.TryGetValue(instrumentKey, out var wid)
        && _workers.TryGetValue(wid, out var w)
        && w.Process is { HasExited: false } p
            ? p.Id
            : null;

    public string? WorkerIdForInstrument(string instrumentKey) =>
        _instrumentToWorker.TryGetValue(instrumentKey, out var wid) ? wid : null;

    public IReadOnlyList<string> InstrumentsInWorker(string workerId) =>
        _workers.TryGetValue(workerId, out var w) ? w.Instruments : Array.Empty<string>();

    /// <summary>Stop everything and start <paramref name="jobs"/> shard workers covering all instruments.</summary>
    public int StartPool(IReadOnlyList<(string Sec, string ClassCode)> instruments, int jobs)
    {
        if (instruments.Count == 0) return 0;
        StopAll();
        _busySecByWorker.Clear();

        var nJobs = Math.Max(1, Math.Min(ClampJobs(jobs), instruments.Count));
        var shards = SplitRoundRobin(instruments, nJobs);
        for (var i = 0; i < shards.Count; i++)
        {
            var id = $"w{i + 1}";
            StartShard(id, shards[i]);
        }
        return shards.Count;
    }

    /// <summary>Dedicated one-instrument workers for the given list, capped by <paramref name="maxWorkers"/> total slots.</summary>
    public int StartDedicated(IReadOnlyList<(string Sec, string ClassCode)> instruments, int maxWorkers)
    {
        if (instruments.Count == 0) return 0;
        var room = Math.Max(0, ClampJobs(maxWorkers) - WorkerCount);
        if (room == 0) return 0;

        var started = 0;
        foreach (var (sec, cls) in instruments)
        {
            if (started >= room) break;
            var key = $"{sec}:{cls}";
            if (IsInstrumentCovered(key)) continue;
            var id = $"solo:{key}";
            StartShard(id, [(sec, cls)]);
            started++;
        }
        return started;
    }

    public void StopWorker(string workerId)
    {
        if (!_workers.TryRemove(workerId, out var worker))
            return;
        worker.Stopping = true;
        _busySecByWorker.TryRemove(workerId, out _);
        foreach (var inst in worker.Instruments)
            _instrumentToWorker.TryRemove(inst, out _);
        KillTree(worker.Process);
    }

    public void StopInstrument(string instrumentKey)
    {
        if (!_instrumentToWorker.TryGetValue(instrumentKey, out var wid))
            return;
        // Stopping one instrument in a multi shard would leave others orphaned — stop whole shard.
        StopWorker(wid);
    }

    public void StopAll()
    {
        foreach (var id in _workers.Keys.ToArray())
            StopWorker(id);
        _instrumentToWorker.Clear();
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        StopAll();
    }

    public static List<List<(string Sec, string ClassCode)>> SplitRoundRobin(
        IReadOnlyList<(string Sec, string ClassCode)> universe,
        int jobs)
    {
        if (universe.Count == 0) return [];
        var nJobs = Math.Max(1, Math.Min(jobs, universe.Count));
        var shards = Enumerable.Range(0, nJobs).Select(_ => new List<(string, string)>()).ToList();
        for (var i = 0; i < universe.Count; i++)
            shards[i % nJobs].Add(universe[i]);
        return shards.Where(s => s.Count > 0).ToList();
    }

    private void StartShard(string workerId, IReadOnlyList<(string Sec, string ClassCode)> shard)
    {
        if (shard.Count == 0) return;
        StopWorker(workerId);

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
        psi.ArgumentList.Add("--watch-net");
        psi.ArgumentList.Add("--poll");
        psi.ArgumentList.Add("11");
        if (shard.Count == 1)
        {
            psi.ArgumentList.Add("--sec");
            psi.ArgumentList.Add(shard[0].Sec);
            psi.ArgumentList.Add("--class-code");
            psi.ArgumentList.Add(shard[0].ClassCode);
        }
        else
        {
            var packed = string.Join(",", shard.Select(s => $"{s.Sec}:{s.ClassCode}"));
            psi.ArgumentList.Add("--watch-only");
            psi.ArgumentList.Add(packed);
        }

        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        psi.Environment["OPENBLAS_NUM_THREADS"] = "1";
        psi.Environment["OMP_NUM_THREADS"] = "1";
        psi.Environment["MKL_NUM_THREADS"] = "1";
        psi.Environment["NUMEXPR_NUM_THREADS"] = "1";

        var keys = shard.Select(s => $"{s.Sec}:{s.ClassCode}").ToArray();
        var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var worker = new Worker(workerId, keys, proc, shard.ToArray());
        _workers[workerId] = worker;
        foreach (var key in keys)
            _instrumentToWorker[key] = workerId;

        proc.OutputDataReceived += (_, e) =>
        {
            if (string.IsNullOrWhiteSpace(e.Data)) return;
            NoteBusyFromLog(workerId, e.Data);
            Log?.Invoke(workerId, e.Data);
        };
        proc.ErrorDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data))
                Log?.Invoke(workerId, "ERR " + e.Data);
        };
        proc.Exited += (_, _) =>
        {
            Log?.Invoke(workerId, $"exit={proc.ExitCode}");
            if (_disposed || worker.Stopping) return;
            _ = Task.Run(async () =>
            {
                await Task.Delay(2000).ConfigureAwait(false);
                if (_disposed || worker.Stopping) return;
                try
                {
                    StartShard(workerId, worker.Shard);
                    Log?.Invoke(workerId, "restarted");
                }
                catch (Exception ex)
                {
                    Log?.Invoke(workerId, "restart failed: " + ex.Message);
                }
            });
        };

        if (!proc.Start())
            throw new InvalidOperationException($"Не удалось запустить {workerId}");
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        Log?.Invoke(workerId, $"started pid={proc.Id} n={shard.Count} [{string.Join(",", shard.Select(s => s.Sec))}]");
    }

    private void NoteBusyFromLog(string workerId, string line)
    {
        // "22:40:01  compute GAZP  M1+M10+M30+H4+D1 ..."
        const string marker = " compute ";
        var idx = line.IndexOf(marker, StringComparison.Ordinal);
        if (idx < 0) return;
        var rest = line[(idx + marker.Length)..].TrimStart();
        var sp = rest.IndexOf(' ');
        var sec = sp < 0 ? rest : rest[..sp];
        if (!string.IsNullOrWhiteSpace(sec))
            _busySecByWorker[workerId] = sec.Trim();
    }

    private static void KillTree(Process? proc)
    {
        if (proc == null) return;
        try
        {
            if (!proc.HasExited)
            {
                using var killer = Process.Start(new ProcessStartInfo
                {
                    FileName = "taskkill",
                    Arguments = $"/PID {proc.Id} /T /F",
                    CreateNoWindow = true,
                    UseShellExecute = false,
                });
                killer?.WaitForExit(5000);
            }
        }
        catch
        {
            try { if (!proc.HasExited) proc.Kill(entireProcessTree: true); } catch { /* ignore */ }
        }
        try { proc.Dispose(); } catch { /* ignore */ }
    }

    private static string ResolvePython()
    {
        var candidates = new[]
        {
            Environment.GetEnvironmentVariable("WATCHNET_PYTHON"),
            @"C:\Users\koaln\AppData\Local\Programs\Python\Python314\python.exe",
            "python",
            "py",
        };
        foreach (var c in candidates)
        {
            if (string.IsNullOrWhiteSpace(c)) continue;
            if (c is "python" or "py") return c;
            if (File.Exists(c)) return c;
        }
        return "python";
    }

    private sealed class Worker(
        string id,
        string[] instruments,
        Process process,
        (string Sec, string ClassCode)[] shard)
    {
        public string Id { get; } = id;
        public string[] Instruments { get; } = instruments;
        public (string Sec, string ClassCode)[] Shard { get; } = shard;
        public Process Process { get; } = process;
        public bool Stopping { get; set; }
    }
}
